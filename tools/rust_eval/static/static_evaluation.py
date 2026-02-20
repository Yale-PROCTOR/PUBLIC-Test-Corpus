#!/usr/bin/env python3

# © 2026 Massachusetts Institute of Technology
# MIT License

import argparse

import subprocess
import os
import re
import sys
import json
from pathlib import Path
from collections import Counter

def check_lints(target_manifest: Path):
  # Separates out lints for each category.
  # Clippy lints from the correctness, suspicious, complexity, perf, and style
  # groups are counted by group.
  # rustc errors and warnings are also included.

  # rustc compiler errors + warnings will have (among other fields)
    # {"reason": "compiler-message",
    #   "message": {
    #     "code": { # if code is null, not warning/error
    #       "code": "unused_variables" # or other reason
    #     },
    #     "level": "warning" # or other level
    #   }
    # }
    # if the message is from Clippy, the "code" name will start with "clippy::"

  rustc_msgs = {
    "error": Counter(),
    "warning": Counter(),
  }
  done_with_compiler = False # only count compiler errors once

  # each category of lints to separate out
  clippy_lint_args = (
    ("-D", "correctness"),
    ("-W", "suspicious"),
    ("-W", "complexity"),
    ("-W", "perf"),
    ("-W", "style"),
    )
  clippy_msgs = {
    kind[1]: Counter() for kind in clippy_lint_args
  }

  for clippy_lint_pair in clippy_lint_args:
    args = ["cargo", "clippy", # note `cargo check` does not catch everything
      "--message-format", "json",
      "--manifest-path", str(target_manifest.resolve()),
      "--",
      "-A", "clippy::all",
      clippy_lint_pair[0], f"clippy::{clippy_lint_pair[1]}"]

    try:
      # compiler messages with warnings/errors go to stdout
      res = subprocess.run(args, text=True, check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred when running clippy lint {e}")
        print(f"Stdout: {e.output}")
        print(f"Stderr: {e.stderr}")
        raise

    for line in res.stdout.split("\n"):
      if line == "" or line[0] != "{":
        continue # not a json message
      message = json.loads(line)
      if message["reason"] != "compiler-message":
        continue # not a compiler message we care about

      code_dict = message["message"]["code"]
      level = message["message"]["level"]

      if code_dict:
        kind = code_dict["code"]
        if kind.startswith("clippy::"):
          clippy_msgs[clippy_lint_pair[1]][kind] += 1
        elif not done_with_compiler:
          rustc_msgs[level][kind] += 1

    done_with_compiler = True # only count c2rust errors once, not for every bucket

  lint_counts = {
    "rustc": {
      level: (rustc_msgs[level].total(), {
          kind: count for kind, count in rustc_msgs[level].items()
        }) for level in rustc_msgs
    },
    "clippy": {
      category: (clippy_msgs[category].total(), {
          kind: count for kind, count in clippy_msgs[category].items()
        }) for category in clippy_msgs if clippy_msgs[category].total()
    }
  }

  return lint_counts


cog_comp_pattern = re.compile(r"^the function has a cognitive complexity of \((\d+)/0\)$")
def cog_complexity_counts(target_manifest: Path):
  # check cyclomatic complexity as computed by clippy for everything
  args = ["cargo", "clippy",
    "--message-format", "json",
    "--manifest-path", str(target_manifest.resolve()),
    "--",
    "-A", "clippy::all", # silence everything
    "-W", "clippy::cognitive_complexity"] # except cognitive complexity

  my_env = os.environ.copy()
  clippy_conf_path = Path(__file__).resolve().parent / "clippy.toml"

  # point to config that tells Clippy to report all cognitive complexity numbers
  my_env["CLIPPY_CONF_DIR"] = str(clippy_conf_path.resolve())

  try: 
    res = subprocess.run(args, env=my_env, text=True, capture_output=True)
  except subprocess.CalledProcessError as e:
    print(f"Error occurred when running clippy lint {e}")
    print(f"Stdout: {e.output}")
    print(f"Stderr: {e.stderr}")
    raise

  all_counts = Counter()

  for line in res.stdout.split("\n"):
    if line == "" or line[0] != "{":
      continue # not a json message
    message = json.loads(line)
    if message["reason"] != "compiler-message":
      continue # not a compiler message we care about

    code_dict = message["message"]["code"]

    if code_dict:
      kind = code_dict["code"]
      if kind == "clippy::cognitive_complexity":
        cog_printed = message["message"]["message"]
        cog_value = int(cog_comp_pattern.match(cog_printed).group(1))
        all_counts[cog_value] += 1

  return dict(all_counts)

def all_idiomaticity_measures(source: Path):
  results = {}

  target_manifest = source.joinpath("Cargo.toml")

  results["cyclomatic_complexity_counts"] = cog_complexity_counts(target_manifest)
  results["lints"] = check_lints(target_manifest)

  return results

def run_unsafeops(source: Path):
    """
    Runs the TRACTOR/unsafe_ops_checker fork of rustc and returns the results
    """
    my_env = os.environ.copy()
    my_env["RUSTFLAGS"] = "-C codegen-units=1"
    my_env["TRACTOR_UNSAFE_OPS"] = "1"
    try:
      subprocess.run(
        ["cargo", "+TractorUnsafeOpsFork", "clean"],
        check=True,
        cwd=source
      )
      result = subprocess.run(
        # See TRACTOR/unsafe_ops_checker repo for setup instructions
        ["cargo", "+TractorUnsafeOpsFork", "-vv", "check"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
        cwd=source,
        env=my_env
      )
      result = result.stdout
      # The unsafe_ops_checker prints to stdout, which might be mixed in
      # with other random verbose output, so we need to extract diagnostics.
      discovered = re.findall(r'TRACTOR_UNSAFE_OPS ({.*})', result)
      loaded = [json.loads(e) for e in discovered]
      # We only want to count unsafe ops for code in the translated crate,
      # not in any third-party dependencies.
      # The analysis is somewhat shaky and could be more rigorous.
      filtered = []
      for e in loaded:
        span = e["span"]

        # unsafe function calls within stdlib macros
        if span.startswith("library/"):
          continue

        # unsafe ops within third-party crates in the Cargo cache
        if ".cargo" in span:
          continue

        filtered.append(e)

      return filtered
    except subprocess.CalledProcessError as e:
      print(f"Error occurred when running measure_unsafeops {e}")
      print(f"Stdout: {e.output}")
      print(f"Stderr: {e.stderr}")
      raise

def run_unsafety(source: Path, measure_unsafety_dir: Path):
    """
    Runs the measure_unsafety Rust project and returns the results
    """
    try:
      result = subprocess.run(
        ["cargo", "run", "--", source],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
          cwd=measure_unsafety_dir
      )
      unsafety_results = json.loads(result.stdout)
      return unsafety_results 
    except subprocess.CalledProcessError as e:
      print(f"Error occurred when running measure_unsafety {e}")
      print(f"Stdout: {e.output}")
      print(f"Stderr: {e.stderr}")
      raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser("Perform static evaluation of Rust project, including unsafety usage and idiomaticity.")
    
    parser.add_argument("source", type=Path,
                       help="The Rust project to evaluate")
    parser.add_argument("--output", type=Path,
                      help="Where to output results. Defaults to stdout",
                      nargs="?", default=None)
    parser.add_argument("--measure-unsafety-dir", type=Path,
                       help="The directory with the measure_unsafety project",
                       nargs="?", default="measure_unsafety")

    args = parser.parse_args()
    source = args.source.resolve()

    # Run static evaluation
    idiomaticity_results = all_idiomaticity_measures(source)
    unsafety_results = run_unsafety(source, args.measure_unsafety_dir)

    # Combine the results of unsafety + idiomaticity
    unsafety_results = {"unsafety": unsafety_results}
    combined_results = {**unsafety_results, **idiomaticity_results}

    if args.output:
        with open(args.output, "w") as f:
            json.dump(combined_results, f, indent=2)
    else: 
        json.dump(combined_results, sys.stdout, indent=2)
