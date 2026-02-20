# © 2026 Massachusetts Institute of Technology
# MIT License

import argparse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, TypedDict
import json
from pathlib import Path
from common import PERFORMERS


@dataclass
class CaseStatus:
    failure: bool = False
    error: bool = False
    skipped: bool = False

    @property
    def label(self) -> str:
        if self.error:
            return "error"
        if self.failure:
            return "failure"
        if self.skipped:
            return "skipped"
        return "pass"


"""The first key is the test case name, the second is the test vector (or build/configure)"""
SuiteCases = Dict[str, Dict[str, CaseStatus]]


class CaseVectorPair(TypedDict):
    """Stores pair of test case and vector name"""
    case_name: str
    vector_name: str


class TranslationStats(TypedDict):
    """Stores information about the success of each test case"""

    # Translate and build can only fail at the test case granularity
    translate_failed: List[str]
    build_failed: List[str]
    run_failed: List[str] # looks like we only capture run failed at the test case granularity as well

    # These can be either at the test case or test vector granularity
    compare_failed: List[str | CaseVectorPair]
    compare_ok: List[str | CaseVectorPair]


"""Stores translation stats per performer"""
PerformersStats = Dict[str, TranslationStats]


def parse_junit(path: Path) -> SuiteCases:
    tree = ET.parse(path)
    root = tree.getroot()

    if root.tag == "testsuites":
        suite_elems = root.findall("testsuite")
    elif root.tag == "testsuite":
        suite_elems = [root]
    else:
        raise ValueError(f"Unexpected root tag {root.tag} in {path}")

    suites: SuiteCases = {}
    for suite in suite_elems:
        sname = suite.attrib.get("name", "")
        cases: Dict[str, CaseStatus] = {}
        for tc in suite.findall("testcase"):
            name = tc.attrib.get("name", "")
            status = CaseStatus(
                failure=tc.find("failure") is not None,
                error=tc.find("error") is not None,
                skipped=tc.find("skipped") is not None,
            )
            cases[name] = status
        suites[sname] = cases

    return suites


def check_monotone(perfect_path: Path, run_paths: List[Path]):
    """Raises AssertionError if monotonicity is violated"""
    perfect = parse_junit(perfect_path)
    runs = [parse_junit(p) for p in run_paths]

    combined_so_far: List[SuiteCases] = []
    prev_pass = -1

    for i in range(len(runs)):
        combined_so_far.append(runs[i])
        combined = combine_runs(combined_so_far)
        stats = analyze(perfect, combined, False)
        passes = len(stats["compare_ok"])
        print(f"Up to run {i+1}: {passes} fully passing suites")

        if passes < prev_pass:
            raise AssertionError(
                f"Monotonicity violated: {passes} < {prev_pass} "
                f"when adding file {run_paths[i]}"
            )
        prev_pass = passes


def get_status(cases: Dict[str, CaseStatus], name: str) -> str:
    c = cases.get(name)
    return "missing" if c is None else c.label


def make_case_from_label(label: str) -> CaseStatus:
    if label == "pass":
        return CaseStatus(False, False, False)
    if label == "skipped":
        return CaseStatus(False, False, True)
    if label == "failure":
        return CaseStatus(True, False, False)
    if label == "error":
        return CaseStatus(False, True, False)
    raise ValueError(f"unknown label {label!r}")


def combine_runs(runs: List[SuiteCases]) -> SuiteCases:
    # Order of desirability (monotone):
    # pass > skipped > failure > error > missing
    priority = {"missing": 0, "error": 1, "failure": 2, "skipped": 3, "pass": 4}
    combined: SuiteCases = {}

    for run in runs:
        for sname, cases in run.items():
            ccases = combined.setdefault(sname, {})
            for tname, status in cases.items():
                new_label = status.label
                old_status = ccases.get(tname)
                old_label = None
                if tname == "execution":
                    # Execution is only present if there's a failure, so missing is fine
                    # This is actually a bug in the runner, so TODO
                    old_label = old_status.label if old_status is not None else "pass"
                else:
                    old_label = (
                        old_status.label if old_status is not None else "missing"
                    )
                if priority[new_label] > priority[old_label]:
                    ccases[tname] = make_case_from_label(new_label)

    return combined


def analyze(perfect: SuiteCases, current: SuiteCases, test_vectors: bool) -> TranslationStats:
    stats: TranslationStats = {
        "translate_failed": [],
        "build_failed": [],
        "run_failed": [],
        "compare_ok": [],
        "compare_failed": [],
    }

    for case_name, perfect_vectors in perfect.items():
        print(case_name)
        current_vectors = current.get(case_name)

        # translate
        if current_vectors is None:
            stats["translate_failed"].append(case_name)
            continue

        # build
        current_build = get_status(current_vectors, "build")
        if current_build != "pass":
            stats["build_failed"].append(case_name)
            continue

        # run (execution)
        current_exec = get_status(current_vectors, "execution")
        perfect_exec = get_status(perfect_vectors, "execution")

        if current_exec in ("failure", "error"):
            stats["run_failed"].append(case_name)
            continue
        if perfect_exec != "missing" and current_exec == "missing":
            stats["run_failed"].append(case_name)
            continue

        # compare (non-build, non-exec, non-configure)
        has_nonbuild_failure = False
        for vector_name, p_case in perfect_vectors.items():
            if vector_name in ("configure", "build", "execution"):
                continue

            p_status = p_case.label
            c_case = current_vectors.get(vector_name)
            c_status = c_case.label if c_case is not None else "missing"

            if p_status in ("failure", "error"):
                continue  # already bad in perfect run

            if c_status in ("failure", "error", "missing") or (c_status == "skipped" and p_status != "skipped"):
                has_nonbuild_failure = True
                if test_vectors:
                    stats["compare_failed"].append(CaseVectorPair(case_name=case_name, vector_name=vector_name))
            elif test_vectors:
                stats["compare_ok"].append(CaseVectorPair(case_name=case_name, vector_name=vector_name))

        if not test_vectors:
            if has_nonbuild_failure:
                stats["compare_failed"].append(case_name)
            else:
                stats["compare_ok"].append(case_name)

    return stats


def parse_all_junit(junit_dir: Path, test_vectors: bool) -> PerformersStats:
    """
    Looks in `junit_dir` for the appropriate junit xml files.
    The "clean" junit should be named `junit.xml` with each
    of the performers junit results named `<performer>-junit.xml`.
    Get's the results at the test vector granularity if `test_vectors` is true
    """
    clean_junit = junit_dir.joinpath("junit.xml")
    if not clean_junit.exists():
        raise RuntimeError(f"Couldn't find clean junit: `{clean_junit}`")
    clean_junit_res = parse_junit(clean_junit)

    all_results = {}
    for performer in PERFORMERS:
        print(f"[*] Processing {performer}")
        # FIXME: Should get rid of the hardcoding here eventually and combine across multiple runs
        if performer == "harvest":
            performer_junit = junit_dir.joinpath(f"harvest-sed-junit.xml")
        elif performer == "galois":
            performer_junit = junit_dir.joinpath("galois-jan-manual-patch-junit.xml")
        else:
            performer_junit = junit_dir.joinpath(f"{performer}-junit.xml")

        if not performer_junit.exists():
            raise RuntimeError(
                f"Couldn't find `{performer}` junit at `{performer_junit}`"
            )

        performer_results = analyze(clean_junit_res, parse_junit(performer_junit), test_vectors)
        all_results[performer] = performer_results
        print()
    return all_results


def main():
    parser = argparse.ArgumentParser(
        description="Analyze imperfect JUnit results against a perfect baseline."
    )
    parser.add_argument(
        "junit_dir",
        help="Path to directory with all junit xml results",
        type=Path,
    )
    parser.add_argument(
        "--output",
        help="Output file for JSON results",
        default=Path("stats.json"), 
        type=Path,
    )
    parser.add_argument(
        "--test-vectors",
        action="store_true",
        help="Get success/failure at the test vector granularity",
        default=False,
    )

    # TODO: Leaving this here for now but should find some way to support this
    # parser.add_argument(
    #     "--combine-runs",
    #     action="store_true",
    #     help="Combine multiple current runs by taking the best result per testcase.",
    # )
    # parser.add_argument(
    #     "--check-monotonicity",
    #     action="store_true",
    #     help="Only check monotonicity of joint runs, but don't output anything else",
    # )

    args = parser.parse_args()

    stats = parse_all_junit(args.junit_dir, args.test_vectors)

    with open(args.output, "w") as f:
        json.dump(stats, f, indent=2)


if __name__ == "__main__":
    main()
