#!/usr/bin/env python3

# © 2026 Massachusetts Institute of Technology
# MIT License

import argparse
import json
import subprocess
from pathlib import Path
import os

def run_test(executable: Path, test_path: Path):
    with test_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    # JSON argv is argv[1:] only
    argv = data.get("argv", [])
    stdin_data = data.get("stdin", "")

    if not isinstance(argv, list):
        raise ValueError(f"{test_path}: 'argv' must be a list")

    # Build full command: argv[0] = executable, argv[1:] from JSON
    cmd = [str(executable)] + argv

    result = subprocess.run(
        cmd,
        input=stdin_data,
        text=True,
        capture_output=True,
    )

    # Update JSON fields
    data.setdefault("stdout", {})
    data.setdefault("stderr", {})
    data["stdout"]["pattern"] = result.stdout
    data["stderr"]["pattern"] = result.stderr
    data["rc"] = result.returncode

    with test_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")  # end with newline


def rename_tests(test_dir: Path):
    json_files = sorted(test_dir.glob("*.json"))

    # Rename to temporary unique names to avoid collisions
    tmp_mapping = {}
    for i, path in enumerate(json_files):
        tmp_name = test_dir / f"__tmp_{i}__.json"
        path.replace(tmp_name)
        tmp_mapping[tmp_name] = path

    # Determine final order by original filename
    tmp_files = sorted(tmp_mapping.keys(), key=lambda p: tmp_mapping[p].name)

    for idx, tmp_path in enumerate(tmp_files, start=1):
        new_name = test_dir / f"test{idx:03d}.json"
        tmp_path.replace(new_name)


def main():
    parser = argparse.ArgumentParser(
        description="Update JSON test vectors using a given executable and rename them"
    )
    parser.add_argument("executable", type=Path, help="Path to the executable")
    parser.add_argument("test_dir", type=Path, help="Directory containing JSON tests")
    args = parser.parse_args()

    exe = args.executable
    test_dir = args.test_dir

    if not exe.is_file():
        raise SystemExit(f"Executable not found: {exe}")
    if not os.access(exe, os.X_OK):
        raise SystemExit(f"Executable is not marked executable: {exe}")
    if not test_dir.is_dir():
        raise SystemExit(f"Test directory not found: {test_dir}")

    json_files = sorted(test_dir.glob("*.json"))
    if not json_files:
        raise SystemExit(f"No .json files found in {test_dir}")

    # Update each test file contents
    for path in json_files:
        run_test(exe, path)

    # Rename files
    rename_tests(test_dir)


if __name__ == "__main__":
    main()
