# © 2026 Massachusetts Institute of Technology
# MIT License

import json
from pathlib import Path
from argparse import ArgumentParser
import re
from typing import Optional, Dict, TypedDict

from common import PERFORMERS


ALL_JOBS_FILE = Path("tmp/all_jobs.json")
TEST_CASE_NAME_REGEX = r"^([^-]+)-translate-[^-]+-[^-]+-([^_]+)_([^_]+_[^_]+)_(.+)(?=_tar_gz)"



class JobInfo(TypedDict):
    """Runtime / sucess information from AWS all_jobs.json"""

    runtime_ms: Optional[float] # in milliseconds
    job_success: bool


"""Stores the test case name along with it's assocaited JobInfo"""
JobInfoPerTestCase = Dict[str, JobInfo]

"""Stores JobInfoPerTestCase per performer"""
PerformersRuntimes = Dict[str, JobInfoPerTestCase]


def get_runtime(performer_dir: Path, corpus: str, performer: str) -> JobInfoPerTestCase:
    """
    Get's performer translation runtime results per test case from AWS job timing
    This is subject to variation due to downloading / uploading things from S3,
    and is a proxy for runtime, not absolute runtime

    Args: 
        performer_dir: directory to look for performer results
        corpus: corpus to look for (e.g., B01, P01, ...)

    Returns:
        Dictionary with key as the test case, and JobInfo (runtime and job success) as values

    Exceptions:
        FileNotFoundError if `tmp/all_jobs.json` doesn't exist in `base_dir`
    to get this information
    """
    all_jobs = performer_dir / ALL_JOBS_FILE
    if not all_jobs.exists():
        raise FileNotFoundError(f"Couldn't find {all_jobs} in {performer_dir}")

    with open(all_jobs, "r") as f:
        test_cases = json.load(f)

    out: JobInfoPerTestCase = {}
    for test_case in test_cases:
        # Extract the name from the test case
        job_name = test_case["jobName"]
        match = re.match(TEST_CASE_NAME_REGEX, job_name)
        if match:
            got_performer = match.group(1)
            public_hidden = match.group(2)
            corpus = match.group(3)
            test_case_name = match.group(4)
            test_case_full_name = f"{public_hidden}/{corpus}/{test_case_name}"
        else:
            raise ValueError(f"Couldn't match job name: {job_name}")

        # Just as a sanity check make sure the performer names match
        if got_performer != performer:
            raise RuntimeError(f"Job {job_name} had incorrect performer name. Got {got_performer}, expected {performer}")

        print(f"[*] Calculating translation time for {test_case_full_name}")

        # Now calculate runtime
        start_time = int(test_case["startedAt"])
        end_time = int(test_case["stoppedAt"])
        runtime = end_time - start_time

        job_success = True if test_case["status"] == "SUCCEEDED" else False
        out[test_case_full_name] = {
            "job_success": job_success, 
            "runtime_ms": runtime if job_success else None
        }

    return out


def get_all_runtimes(base_dir: Path, corpus: str) -> PerformersRuntimes:
    """
    Gets translation runtime information for all performers

    Args:
        base_dir: directory with all performer results
                  should be structured have subdirs like {performer}.{corpus}/{performer} (e.g., galois.B01/galois)
        corpus: corpus to look for (e.g., B01, P01, ...)

    Returns:
        Dictionary with all test case JobInfo per performer

    Exceptions:
        FileNotFoundError: if we couldn't find `tmp/all_jobs.json`
        FileNotFoundError: if the given `bae_dir` isn't structure properly (see above)
    """
    all_runtimes: PerformersRuntimes = {}

    for performer in PERFORMERS:
        print(f"[*] Processing {performer}")
        performer_dir = base_dir / f"{performer}.{corpus}" / performer
        if not performer_dir.exists():
            raise FileNotFoundError(f"Couldn't find {corpus} results for {performer} in {performer_dir}")

        all_runtimes[performer] = get_runtime(performer_dir, corpus, performer)

    return all_runtimes


def main():
    parser = ArgumentParser(
        description="Parses AWS translation directory to extract translation runtime"
    )

    parser.add_argument(
        "-d",
        default=Path.cwd(),
        help="base directory to look for performers results (default cwd - results are in LLFS)",
        type=Path,
        required=False,
        dest="base_dir",
    )
    parser.add_argument(
        "-c",
        help="battery or project to get results for (e.g, B01, P01, ...) (default B01)",
        default="B01",
        required=False,
        dest="corpus",
    )
    parser.add_argument(
        "-o",
        help="file to output generated JSON (default {CORPUS}_translation_runtime.json)",
        type=Path,
        required=False,
        dest="out_file",
    )

    args = parser.parse_args()

    if args.out_file is None:
        args.out_file = Path(f"{args.corpus}_translation_runtime.json")

    results = get_all_runtimes(args.base_dir, args.corpus)

    with open(args.out_file, "w") as f:
        json.dump(results, f, indent=2)


if __name__ == "__main__":
    main()
