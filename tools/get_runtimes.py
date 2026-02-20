# © 2026 Massachusetts Institute of Technology
# MIT License

import os
import subprocess
import random
from pathlib import Path
from argparse import ArgumentParser

# Adding c here for the baseline
PERFORMERS = ["aarno", "galois", "harvest", "intel", "uwisc", "yale", "c", "c2rust", "llm"]

def run_perf(ci_path: Path, analyze_path: Path, corpus: str, performer: str, out: Path):
    """
    Calls the CI/Rust runner scripts to calculate runtime information 
    Args:
        ci_path: directory with CI/Rust runner scripts
        analyze_path: performer directory to get results for
        corpus: corpus to analyze (e.g., B01, P01, ...)
        out: file to output results to 
    """
    cmd = [
        "python3",
        "-m",
        "runtests.rust" if performer != "c" else "runtests.ci",
        "--keep-going",
        "--verbose",
        "--root", analyze_path,
        "-m", corpus,
        "--perf-metrics", out,
    ]

    subprocess.run(cmd, cwd=ci_path)


def run_all(ci_path: Path, c_dir: Path, root: Path, corpus: str, out: Path):
    """Runs all performers + C baseline runtime metrics in a random order"""
    random.shuffle(PERFORMERS) # make them random

    for performer in PERFORMERS:
        print(f"Getting runtime metrics for {performer}")
        if performer == "c":
            analyze_path = c_dir
        else:
            analyze_path = root.joinpath(f"{performer}.{corpus}").joinpath(performer)

        run_perf(ci_path, analyze_path, corpus, performer, out)


def main():
    parser = ArgumentParser(description="Runs runtime performance calculations for all performers and C")

    parser.add_argument(
        "--ci", 
        type=Path,
        help="directory with CI/Rust runner scripts",
        required=False,
        default=Path("../deployment/scripts/github-actions/")
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="directory with all of the performer results to analyze",
        required=True
    )
    parser.add_argument(
        "--c-dir",
        type=Path,
        help="directory with the baseline C results (Test-Corpus)",
        required=True
    )
    parser.add_argument(
        "--corpus",
        help="corpus to analyze results for (e.g., B01, P01, ...)",
        default="B01"
    )
    parser.add_argument(
        "--out",
        type=lambda p: Path(p).resolve(),
        help="path to output file",
        default=Path("./perf_metrics.csv").resolve()
    )

    args = parser.parse_args()

    # Run all of the runtime metrics once to warm the system/caches up
    run_all(args.ci, args.c_dir, args.root, args.corpus, args.out)

    # Remove the last output file to run them for real
    os.remove(args.out)
    run_all(args.ci, args.c_dir, args.root, args.corpus, args.out)

if __name__ == "__main__":
    main()

