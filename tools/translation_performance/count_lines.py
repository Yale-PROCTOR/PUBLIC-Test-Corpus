# © 2026 Massachusetts Institute of Technology
# MIT License

from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess
from typing import List, Optional, TypedDict, Dict, Union
from common import REQUIRED_DIRS


class TestCaseCounts(TypedDict):
    """Line count information from `cloc`"""

    nFiles: int
    blank: int
    comment: int
    code: int


"""
Information about the line counts for each test case of the form:
    {
        "cloc_version": <version of cloc used to generate this info>,
        <test_case_name>: TestCaseCounts,
        ...
    }
"""
LineCounts = Dict[str, Union[str, TestCaseCounts]]


def cloc_version() -> str:
    command = ["cloc", "--version"]
    results = subprocess.run(command, capture_output=True, check=True, text=True)
    print(f"Using cloc version: {results.stdout}")
    return results.stdout


def invoke_cloc(_dir: Path) -> TestCaseCounts:
    """
    Invokes `cloc` on given directory and returns line count information
    """
    command = ["cloc", "--include-lang=C", "--exclude-dir=build", "--json", "."]

    results = subprocess.run(
        command, capture_output=True, check=True, text=True, cwd=_dir
    )

    json_results = json.loads(results.stdout)
    return json_results["C"]


def get_test_case_dirs(test_corpus_dir: Path) -> List[Path]:
    """
    Walks `test_corpus_dir` returning a list of all test cases
    """
    dirs = []
    for base_dir in REQUIRED_DIRS:
        test_dir = test_corpus_dir.joinpath(base_dir)
        if test_dir.exists() and test_dir.is_dir():
            for proj_batt_dir in test_dir.iterdir():
                if proj_batt_dir.is_dir():
                    for test_case_dir in proj_batt_dir.iterdir():
                        dirs.append(test_case_dir)
    return dirs


def get_line_counts(test_corpus_dir: Path, corpus: Optional[str] = None) -> LineCounts:
    """
    Goes through test cases `test_corpus_dir` and invokes `cloc` to
    get line count information on test cases that are in
    `corpus` (e.g., B01, P01, ...).
    """
    # Get the cloc version just in case we need it
    # counts = {"cloc_version": cloc_version()}
    counts: LineCounts = {"cloc_version": cloc_version()}

    test_case_dirs = get_test_case_dirs(test_corpus_dir)
    for test_case_dir in test_case_dirs:
        # Only care about last three parts (e.g., Public-Tests/B01_synthetic/001_helloworld)
        test_case_name = Path(*test_case_dir.parts[-3:])
        if corpus is None or test_case_name.parts[-2].startswith(corpus):
            print(test_case_name)
            test_case = test_case_dir.joinpath("test_case")
            if test_case.exists() and test_case.is_dir():
                counts[str(test_case_name)] = invoke_cloc(test_case)
            else:
                print(f"Skipping {test_case_name}: Couldn't find `test_case` directory")
    return counts


def main():
    parser = ArgumentParser(description="Runs cloc on Test-Corpus to get LoC count")

    parser.add_argument(
        "-d",
        default=Path("../../").resolve(),
        help=f"base directory to look for test corpus",
        type=Path,
        required=False,
        dest="test_corpus_dir",
    )
    parser.add_argument(
        "-c",
        help="battery or project to get results for (e.g, B01, P01, ...) (default ALL)",
        default=None,
        required=False,
        dest="corpus",
    )
    parser.add_argument(
        "-o",
        help="file to output genereated JSON to (default loc.json)",
        default=Path("loc.json"),
        type=Path,
        dest="out_file",
    )

    args = parser.parse_args()

    counts: LineCounts = get_line_counts(args.test_corpus_dir, args.corpus)
    with open(args.out_file, "w") as f:
        json.dump(counts, f, indent=2)


if __name__ == "__main__":
    main()
