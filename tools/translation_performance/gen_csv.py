# © 2026 Massachusetts Institute of Technology
# MIT License

import os
import json
import csv
from argparse import ArgumentParser
from pathlib import Path
from typing import List, NamedTuple, Optional, TypedDict, cast
from common import PERFORMERS

from count_lines import get_line_counts, LineCounts, TestCaseCounts
from translation_stats import parse_all_junit, PerformersStats
from runtime import get_all_runtimes, PerformersRuntimes


OUT_CSV_FILE = Path("translation_runtimes.csv")


class AllDataNullable(TypedDict):
    """
    Stores all of the necessary raw data for graphs
    Optional fields to decide what raw data needs to be regenerated
    """

    line_counts: Optional[LineCounts]
    runtimes: Optional[PerformersRuntimes]
    stats: Optional[PerformersStats]


class AllDataValidated(TypedDict):
    """Same as `AllDataNullable` but all of the data has been gathered"""

    line_counts: LineCounts
    runtimes: PerformersRuntimes
    stats: PerformersStats


class LocRuntime(NamedTuple):
    """
    Representation of kloc and runtime information for plotting.
    Parallel lists where each index has corresponding kloc/runtime
    """

    name: List[str]  # name of test case
    kloc: List[float]
    runtime_hrs: List[Optional[float]]


class TransformedData(TypedDict):
    """
    Representation of transformed data (from `AllDataValidated`).
    Used for plotting
    """

    translate_failed: LocRuntime
    build_failed: LocRuntime
    run_failed: LocRuntime
    compare_failed: LocRuntime
    compare_ok: LocRuntime


def get_line_count(line_count: TestCaseCounts) -> float:
    """
    Helper function to transform number of blank, comment, and
    actual code lines into a single number so we can change
    to fit our use case. This currently just adds all of them
    and divides by 1000 to get kLoC.
    """
    return (line_count["blank"] + line_count["comment"] + line_count["code"]) / 1000


def transform(all_data: AllDataValidated, performer: str) -> TransformedData:
    """Transform `all_data` into better format for plotting"""
    transform: TransformedData = {
        "translate_failed": LocRuntime([], [], []),
        "build_failed": LocRuntime([], [], []),
        "run_failed": LocRuntime([], [], []),
        "compare_failed": LocRuntime([], [], []),
        "compare_ok": LocRuntime([], [], []),
    }

    for step_reached, test_cases in all_data["stats"][performer].items():
        # Need to do this explicity for some reason
        test_cases = cast(List[str], test_cases)
        for test_case in test_cases:
            # Cast because line_counts value can be a str (but this won't happen)
            kloc = get_line_count(
                cast(TestCaseCounts, all_data["line_counts"][test_case])
            )

            # Now get the runtime of that test case
            job_info = all_data["runtimes"][performer][test_case]

            if not job_info["job_success"]:
                # NOTE: Here we're assuming that the AWS job failed because of a timeout
                # and recording that as a `translate_failed`
                print(f"[!] AWS job failed for: {test_case}, marking as translate_failed with no runtime information")
                step_reached = "translate_failed"
                runtime = None
            elif job_info["runtime_ms"] is None:
                print(f"[!] Test case: {test_case} didn't have any runtime information")
                runtime = None
            else:
                runtime = job_info["runtime_ms"] / 3_600_000 # convert to hrs

            transform[step_reached].name.append(test_case)
            transform[step_reached].kloc.append(kloc)
            transform[step_reached].runtime_hrs.append(runtime)

    return transform


def gen_csv(all_data: AllDataValidated, out_dir: Path) -> None:
    """Converts `all_data` into csv format"""
    with open(out_dir.joinpath(OUT_CSV_FILE), "w") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["performer", "test_case", "step_reached", "kloc", "runtime_hrs"]
        )

        for performer in PERFORMERS:
            transformed = transform(all_data, performer)

            for step_reached, loc_runtime in transformed.items():
                loc_runtime = cast(LocRuntime, loc_runtime)
                for test_case, kloc, runtime_hrs in zip(
                    loc_runtime.name, loc_runtime.kloc, loc_runtime.runtime_hrs
                ):
                    writer.writerow(
                        [performer, test_case, step_reached, kloc, runtime_hrs]
                    )


def save_data(all_data: AllDataValidated, out_dir: Path) -> None:
    """Writes `all_data` to disk in `out_dir`"""
    for file in all_data.keys():
        with open(out_dir.joinpath(file), "w") as f:
            json.dump(all_data[Path(file).stem], f, indent=2)


def get_generated(out_dir: Path) -> AllDataNullable:
    """
    Gets the raw JSON data from disk that has already been generated in `dir`
    Sets member of `all_data` to None if it hasn't already been generated
    """
    all_data: AllDataNullable = {"line_counts": None, "runtimes": None, "stats": None}

    for file in all_data.keys():
        try:
            with open(out_dir.joinpath(file), "r") as f:
                all_data[Path(file).stem] = json.load(f)
        except FileNotFoundError:
            # We couldn't find the data on disk
            pass
    return all_data


def gen_data(
    all_data: AllDataNullable,
    test_corpus_dir: Path,
    corpus: str,
    results_dir: Path,
    junit_dir: Path,
) -> AllDataValidated:
    # all_data_validated: AllDataValidated = {}
    for key, value in all_data.items():
        if value is not None:
            print(f"[*] Found {key} NOT regenerting")
        else:
            print(f"[*] Generating {key}")

            if key == "line_counts":
                all_data[key] = get_line_counts(test_corpus_dir, corpus)
            elif key == "runtimes":
                all_data[key] = get_all_runtimes(results_dir, corpus)
            elif key == "stats":
                all_data[key] = parse_all_junit(junit_dir)
            else:
                raise RuntimeError(f"Found invalid evaluation: {key}")
            print()

    for key, value in all_data.items():
        if value is None:
            raise RuntimeError(f"Missing value for key {key}")

    return AllDataValidated(
        line_counts=cast(LineCounts, all_data["line_counts"]),
        runtimes=cast(PerformersRuntimes, all_data["runtimes"]),
        stats=cast(PerformersStats, all_data["stats"]),
    )


def main():
    parser = ArgumentParser(description="Generate plots for translation runtime")

    parser.add_argument(
        "-d",
        help=f"base directory to look for performers results - results are in LLFS)",
        type=Path,
        required=True,
        dest="results_dir",
    )
    parser.add_argument(
        "-t",
        default=Path("../../").resolve(),
        help=f"base directory to look for test corpus",
        type=Path,
        required=False,
        dest="test_corpus_dir",
    )
    parser.add_argument(
        "-c",
        help="battery or project to get results for (e.g, B01, P01, ...) (default B01)",
        default="B01",
        required=False,
        dest="corpus",
    )
    parser.add_argument(
        "-j",
        help="directory with raw junit xml results of translations",
        type=Path,
        required=True,
        dest="junit_dir",
    )
    parser.add_argument(
        "-o",
        help=f"output directory for intermediate files and final CSV (called {OUT_CSV_FILE})",
        type=Path,
        default="translation_runtimes",
        required=False,
        dest="out_dir",
    )
    parser.add_argument(
        "--regen",
        help="regenerate raw JSON data (default False)",
        action="store_true",
        required=False,
        default=False,
    )
    parser.add_argument(
        "--save",
        help="save the raw JSON data that was generated (default True)",
        type=bool,
        required=False,
        default=True,
    )

    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    if not args.regen:
        # See if we can load data from disk (if specified by user)
        all_data_nullable: AllDataNullable = get_generated(args.out_dir)
    else:
        # Regen everything
        all_data_nullable: AllDataNullable = {
            "line_counts": None,
            "runtimes": None,
            "stats": None,
        }

    # Regenerate what's necessary
    all_data_validated: AllDataValidated = gen_data(
        all_data_nullable,
        args.test_corpus_dir,
        args.corpus,
        args.results_dir,
        args.junit_dir,
    )

    if args.save:
        save_data(all_data_validated, args.out_dir)

    gen_csv(all_data_validated, args.out_dir)


if __name__ == "__main__":
    main()
