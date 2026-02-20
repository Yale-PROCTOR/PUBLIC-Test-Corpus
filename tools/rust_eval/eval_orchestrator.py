# © 2026 Massachusetts Institute of Technology
# MIT License

"""
Test runner for analysis of code units.

Architecture:
- Generator: Callable for transforming a directory+context into JSON
- Analysis Combinators:
    - Generators, chains, identity
    - parallel, sequential operators

Python 3.13+ required.
"""

from __future__ import annotations

import io
import json
import logging
import shutil
import tempfile
import xmltodict
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from functools import reduce
from pathlib import Path
from typing import Generic, TypeVar, Callable, Iterator, Any

# import our various evaluation tools
from static.static_evaluation import all_idiomaticity_measures
from static.static_evaluation import run_unsafety, run_unsafeops


# ============================================================================
# Result ADT
# ============================================================================

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True, slots=True)
class Ok(Generic[T]):
    """Success variant."""
    value: T

    def map(self, f: Callable[[T], T]) -> Ok[T]:
        return Ok(f(self.value))
    
    def flat_map(self, f: Callable[[T], Result[T, E]]) -> Result[T, E]:
        return f(self.value)
    
    def map_err(self, f: Callable[[E], E]) -> Ok[T]:
        return self
    
    def unwrap_or(self, default: T) -> T:
        return self.value
    
    def or_else(self, f: Callable[[E], Result[T, E]]) -> Ok[T]:
        return self

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False


@dataclass(frozen=True, slots=True)
class Err(Generic[E]):
    """Failure variant."""
    error: E

    def map(self, f: Callable[[T], T]) -> Err[E]:
        return self
    
    def flat_map(self, f: Callable[[T], Result[T, E]]) -> Err[E]:
        return self
    
    def map_err(self, f: Callable[[E], E]) -> Err[E]:
        return Err(f(self.error))
    
    def unwrap_or(self, default: T) -> T:
        return default
    
    def or_else(self, f: Callable[[E], Result[T, E]]) -> Result[T, E]:
        return f(self.error)

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True


type Result[T, E] = Ok[T] | Err[E]


@dataclass(frozen=True, slots=True)
class ProcessingError:
    """Captures error context during unit processing."""
    unit_path: Path
    exception: Exception
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __str__(self) -> str:
        return f"[{self.timestamp.isoformat()}] {self.unit_path}: {self.exception}"

type ReportResult = Result[dict[str, Any], ProcessingError]


# ============================================================================
# Generator Output and Context
# ============================================================================

@dataclass(frozen=True, slots=True)
class GeneratorOutput:
    """
    Separates two concerns:
    - result: What gets folded into final JSON report
    - contributions: What gets threaded to subsequent generators in a chain
    
    For simple generators: contributions = (result,)
    For parallel: contributions = all branch results
    """
    result: ReportResult
    contributions: tuple[ReportResult, ...]

    @staticmethod
    def single(result: ReportResult) -> GeneratorOutput:
        """Convenience: result contributes itself."""
        return GeneratorOutput(result, (result,))

    @staticmethod
    def branched(
        results: tuple[ReportResult, ...],
        merged: ReportResult,
    ) -> GeneratorOutput:
        """Parallel execution: merged result, all branches threaded."""
        return GeneratorOutput(merged, results)


@dataclass(frozen=True, slots=True)
class GeneratorContext:
    """
    Immutable context threaded through generator chains.
    
    prior_results contains contributions from all previous generators,
    including expanded parallel branches.
    """
    directory: Path
    logger: logging.Logger
    prior_results: tuple[ReportResult, ...] = ()

    def with_contributions(self, contributions: tuple[ReportResult, ...]) -> GeneratorContext:
        """Return new context with contributions appended."""
        return GeneratorContext(
            self.directory,
            self.logger,
            self.prior_results + contributions,
        )


type Generator = Callable[[GeneratorContext], GeneratorOutput]
type SimpleGenerator = Callable[[Path, logging.Logger], dict[str, Any]]


# ============================================================================
# Resource Management
# ============================================================================

@contextmanager
def isolated_copy(source: Path, prefix: str = "") -> Iterator[Path]:
    """
    Copy source directory to a temp location, yield the copy, cleanup on exit.
    """
    with tempfile.TemporaryDirectory(prefix=prefix) as tmp:
        copied = Path(tmp) / source.name
        shutil.copytree(source, copied)
        yield copied


@contextmanager
def branch_context(
    parent_ctx: GeneratorContext,
    prefix: str = "",
) -> Iterator[GeneratorContext]:
    """
    Create an isolated branch context with its own directory copy.
    
    Inherits logger and prior_results from parent, but operates on
    an isolated copy of the directory. Cleanup is automatic.
    """
    with isolated_copy(parent_ctx.directory, prefix) as branch_path:
        yield GeneratorContext(
            branch_path,
            parent_ctx.logger,
            parent_ctx.prior_results,
        )


# ============================================================================
# Report JSON Monoid
# ============================================================================

def report_identity() -> dict[str, Any]:
    """Monoid identity: empty report"""
    return {"suites": []}


def report_merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """
    Monoid binary operation: merge two reports.
    
    Associative: merge(merge(a, b), c) == merge(a, merge(b, c))
    Identity: merge(identity(), x) == merge(x, identity()) == x
    """
    left_suites = left.get("suites", [left] if "name" in left else [])
    right_suites = right.get("suites", [right] if "name" in right else [])
    
    return {"suites": left_suites + right_suites}


def error_to_report(error: ProcessingError) -> dict[str, Any]:
    """Lift a ProcessingError into the report domain."""
    return {
        "name": str(error.unit_path),
        "timestamp": error.timestamp.isoformat(),
        "error": {
            "type": type(error.exception).__name__,
            "message": str(error.exception),
        }
    }

def result_to_report(result: ReportResult) -> dict[str, Any]:
    """Unwrap Result, lifting errors."""
    match result:
        case Ok(report):
            return report
        case Err(err):
            return error_to_report(err)


def report_fold(results: list[ReportResult]) -> dict[str, Any]:
    """
    Fold results into unified report.
    
    Errors are lifted via error_to_report before folding.
    """
    return reduce(report_merge, map(result_to_report, results), report_identity())

# ============================================================================
# Rejoin Strategies
# ============================================================================

type Rejoin = Callable[[tuple[ReportResult, ...]], ReportResult]

class RejoinStrategy(Enum):
    """Sum type for rejoin strategies."""
    MERGE_ALL = auto()
    FIRST_OK = auto()
    ALL_MUST_SUCCEED = auto()
    ANY_MUST_SUCCEED = auto()
    
    def to_function(self) -> Rejoin:
        """Convert enum variant to its implementation."""
        match self:
            case RejoinStrategy.MERGE_ALL:
                return merge_all
            case RejoinStrategy.FIRST_OK:
                return first_ok
            case RejoinStrategy.ALL_MUST_SUCCEED:
                return all_must_succeed
            case RejoinStrategy.ANY_MUST_SUCCEED:
                return any_must_succeed


class ComposeMode(Enum):
    """Sum type for generator composition modes."""
    CHAIN = auto()
    PARALLEL = auto()
    INDEPENDENT = auto()

def merge_all(results: tuple[ReportResult, ...]) -> ReportResult:
    """Merge all branch results into one (default)."""
    return Ok(report_fold(list(results)))


def first_ok(results: tuple[ReportResult, ...]) -> ReportResult:
    """Return first successful result, or first error if all failed."""
    for result in results:
        if result.is_ok():
            return result
    return results[0] if results else Ok(report_identity())


def all_must_succeed(results: tuple[ReportResult, ...]) -> ReportResult:
    """Return merged result only if all branches succeeded."""
    if all(result.is_ok() for result in results):
        return Ok(report_fold(list(results)))
    errors = [result.error for result in results if result.is_err()]
    return Err(errors[0]) if errors else Ok(report_identity())


def any_must_succeed(results: tuple[ReportResult, ...]) -> ReportResult:
    """Return merged successes if any succeeded, else first error."""
    successes = [result for result in results if result.is_ok()]
    if successes:
        return Ok(report_fold(successes))
    return results[0] if results else Ok(report_identity())


# ============================================================================
# Generator Combinators
# ============================================================================

def identity() -> Generator:
    """Monoid identity: produces empty testsuites."""
    def gen(ctx: GeneratorContext) -> GeneratorOutput:
        return GeneratorOutput(Ok(report_identity()), ())
    return gen


def lift(f: SimpleGenerator) -> Generator:
    """
    Lift (Path, Logger) -> dict -> Generator.
    """
    def gen(ctx: GeneratorContext) -> GeneratorOutput:
        try:
            result: ReportResult = Ok(f(ctx.directory, ctx.logger))
        except Exception as e:
            result = Err(ProcessingError(ctx.directory, e))
        return GeneratorOutput.single(result)
    return gen


def chain(*generators: Generator) -> Generator:
    """
    Sequential composition with result threading.
    
    Each generator sees prior contributions in ctx.prior_results.
    
    Monoid laws hold:
    - chain(identity(), g) == chain(g, identity()) == g
    - chain(chain(a, b), c) == chain(a, chain(b, c))
    """
    def composed(ctx: GeneratorContext) -> GeneratorOutput:
        if not generators:
            return GeneratorOutput(Ok(report_identity()), ())

        all_results: list[ReportResult] = []
        all_contributions: list[ReportResult] = []
        current_ctx = ctx

        for gen in generators:
            output = gen(current_ctx)
            all_results.append(output.result)
            all_contributions.extend(output.contributions)
            current_ctx = current_ctx.with_contributions(output.contributions)

        merged = Ok(report_fold(all_results))
        return GeneratorOutput(merged, tuple(all_contributions))

    return composed


def parallel(
    *generators: Generator,
    rejoin: Rejoin = merge_all,
) -> Generator:
    """
    Parallel composition with isolated directories.
    
    Structure:
    - Unfold context into isolated branches (one temp dir per generator)
    - Run branches in parallel
    - Apply rejoin strategy to produce output
        + Default strategy is to merge all
    - All branch results are contributed
    
    This preserves information for subsequent chain steps.
    """
    def composed(ctx: GeneratorContext) -> GeneratorOutput:
        if not generators:
            return GeneratorOutput(Ok(report_identity()), ())

        def run_branch(idx: int, gen: Generator) -> ReportResult:
            """Run one branch in an isolated temp directory."""
            try:
                with branch_context(ctx, prefix=f"branch_{idx}_") as branch_ctx:
                    return gen(branch_ctx).result
            except Exception as e:
                return Err(ProcessingError(ctx.directory, e))

        # Parallel execution of branches
        with ThreadPoolExecutor(max_workers=len(generators)) as executor:
            futures = {
                executor.submit(run_branch, idx, gen): idx
                for idx, gen in enumerate(generators)
            }
            indexed_results: dict[int, ReportResult] = {}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    indexed_results[idx] = future.result()
                except Exception as e:
                    indexed_results[idx] = Err(ProcessingError(ctx.directory, e))

        # Preserve order when merging
        branch_results = tuple(indexed_results[i] for i in range(len(generators)))
        merged = rejoin(branch_results)
        return GeneratorOutput.branched(branch_results, merged)

    return composed


def guard(predicate: Callable[[GeneratorContext], bool], generator: Generator) -> Generator:
    """Conditional execution: only runs if predicate(ctx) is True."""
    def guarded(ctx: GeneratorContext) -> GeneratorOutput:
        if predicate(ctx):
            return generator(ctx)
        return GeneratorOutput(Ok(report_identity()), ())
    return guarded


def recover(
    generator: Generator,
    handler: Callable[[ProcessingError, GeneratorContext], GeneratorOutput],
) -> Generator:
    """Error recovery: if generator produces Err, invoke handler."""
    def recovered(ctx: GeneratorContext) -> GeneratorOutput:
        output = generator(ctx)
        match output.result:
            case Err(err):
                return handler(err, ctx)
            case _:
                return output
    return recovered


# ============================================================================
# Predicates for guard
# ============================================================================

def all_ok(ctx: GeneratorContext) -> bool:
    """True if all prior results are Ok."""
    return all(result.is_ok() for result in ctx.prior_results)


def any_ok(ctx: GeneratorContext) -> bool:
    """True if any prior result is Ok."""
    return any(result.is_ok() for result in ctx.prior_results)


def latest_ok(ctx: GeneratorContext) -> bool:
    """True if the most recent prior result is Ok."""
    return ctx.prior_results[-1].is_ok() if ctx.prior_results else True


# ============================================================================
# Registry
# ============================================================================

_REGISTRY: dict[str, Generator] = {}


def register(name: str) -> Callable[[SimpleGenerator], Generator]:
    """Decorator: lift and register a simple generator."""
    def decorator(f: SimpleGenerator) -> Generator:
        gen = lift(f)
        _REGISTRY[name] = gen
        return gen
    return decorator


def register_generator(name: str, gen: Generator) -> None:
    """Register a pre-built Generator."""
    _REGISTRY[name] = gen


def get_generator(name: str) -> Generator:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown generator: {name}. Available: {list(_REGISTRY.keys())}")
    return _REGISTRY[name]


def list_generators() -> list[str]:
    return list(_REGISTRY.keys())


def compose_by_names(
    names: list[str],
    mode: ComposeMode = ComposeMode.CHAIN,
    rejoin: Rejoin = merge_all,
) -> Generator:
    """Compose registered generators by name."""
    gens = [get_generator(n) for n in names]
    match mode:
        case ComposeMode.CHAIN:
            return chain(*gens)
        case ComposeMode.PARALLEL:
            return parallel(*gens, rejoin=rejoin)
        case ComposeMode.INDEPENDENT:
            raise ValueError("Independent mode should use run_independent directly")


# ============================================================================
# Buffered Logging
# ============================================================================

@dataclass
class LogBuffer:
    """Accumulates log messages with timestamps."""
    _buffer: io.StringIO = field(default_factory=io.StringIO)

    def create_logger(self, name: str) -> logging.Logger:
        """Create a logger that writes to this buffer."""
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()

        handler = logging.StreamHandler(self._buffer)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"
        ))
        logger.addHandler(handler)

        return logger

    @property
    def contents(self) -> str:
        return self._buffer.getvalue()


# ============================================================================
# Unit Discovery and Processing
# ============================================================================

def discover_units(root: Path, marker_dir: str = "translated_rust") -> list[Path]:
    """
    Discover all code units under a root directory.
    
    A unit is any directory that contains `marker_dir` as a direct child.
    Results are returned in sorted order for deterministic processing.
    
    Args:
        root: The root directory to search.
        marker_dir: The marker directory name that identifies a unit.
        
    Returns:
        Sorted list of unit directory paths.
    """
    if not root.is_dir():
        raise ValueError(f"Root path is not a directory: {root}")

    units: list[Path] = []

    for path in root.rglob("*"):
        if path.is_dir() and (path / marker_dir).is_dir():
            units.append(path)

    return sorted(units, key=lambda p: p.parts)

def process_unit(
    unit_path: Path,
    generator: Generator,
    logger: logging.Logger,
) -> ReportResult:
    """
    Process a single unit: copy to temp directory, run analysis, cleanup.
    
    Args:
        unit_path: Path to the unit directory.
        generator: How to handle each unit directory.
        logger: Optional logger for this operation.
        
    Returns:
        Result containing either Ok(json_report) or Err(processing_error).
    """
    log = logger or logging.getLogger(__name__)
    log.info(f"Processing unit: {unit_path}")

    try:
        with isolated_copy(unit_path) as copied:
            ctx = GeneratorContext(copied, logger)
            output = generator(ctx)
            logger.info(f"Completed: {unit_path}")
            return output.result

    except Exception as e:
        log.error(f"Failed to process {unit_path}: {e}")
        return Err(ProcessingError(unit_path, e))


# Global reference for multiprocessing (avoids pickling issues)
_mp_generator: Generator | None = None
_mp_log_buffer: LogBuffer | None = None


def _init_worker(generator: Generator) -> None:
    """Initialize worker process with generator."""
    global _mp_generator, _mp_log_buffer
    _mp_generator = generator
    _mp_log_buffer = LogBuffer()


def _process_in_worker(unit_path: Path) -> tuple[Path, ReportResult]:
    """
    Worker function for parallel processing.

    MUST ONLY be called AFTER calling `_init_worker`
    """
    logger = _mp_log_buffer.create_logger(f"worker.{unit_path.name}")
    return unit_path, process_unit(unit_path, _mp_generator, logger)

def parallel_map(
    units: list[Path],
    generator: Generator,
    max_workers: int | None = None,
    logger: logging.Logger | None = None,
) -> list[ReportResult]:
    """
    Process units in parallel using a process pool.
    
    Args:
        units: List of unit paths to process.
        generator: A callable object which handles processing for units.
        max_workers: Maximum number of worker processes (None = CPU count).
        logger: Optional logger.
        
    Returns:
        List of results in the same order as input units.
    """
    if not units:
        return []

    log = logger or logging.getLogger(__name__)
    log.info(f"Processing {len(units)} units (max_workers={max_workers})")

    results: dict[Path, ReportResult] = {}

    with ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_init_worker,
        initargs=(generator,),
    ) as executor:
        futures = {executor.submit(_process_in_worker, u): u for u in units}

        for future in as_completed(futures):
            unit_path = futures[future]
            try:
                _, result = future.result()
                results[unit_path] = result
            except Exception as e:
                log.error(f"Worker failed for {unit_path}: {e}")
                results[unit_path] = Err(ProcessingError(unit_path, e))

    ordered_results = [results[unit] for unit in units]
    log.info(f"Completed processing. Success: {sum(1 for result in ordered_results if result.is_ok())}, "
             f"Errors: {sum(1 for result in ordered_results if result.is_err())}")

    return ordered_results


# ============================================================================
# Pipeline
# ============================================================================

@dataclass(frozen=True)
class PipelineResult:
    """Complete result of a pipeline run."""
    report: dict[str, Any]
    results: list[ReportResult]
    logs: str

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.is_ok())

    @property
    def error_count(self) -> int:
        return sum(1 for result in self.results if result.is_err())

    def write(self, path: Path, indent: int = 2) -> None:
        """Write the report to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=indent)

    def to_json(self, indent: int = 2) -> str:
        """Serialize the report to a JSON string."""
        return json.dumps(self.report, indent=indent)


def run_pipeline(
    root_dir: Path,
    generator: Generator,
    marker_dir: str = "translated_rust",
    max_workers: int | None = None,
) -> PipelineResult:
    """
    Execute the complete pipeline: discover -> parallel map -> fold.
    
    Args:
        root_dir: Root directory to scan for units.
        generator: Callable object which implements processing for a unit.
        marker_dir: Directory name that marks a unit.
        max_workers: Maximum parallel workers (None = CPU count).
        
    Returns:
        PipelineResult containing merged JSON and metadata.
    """
    log_buffer = LogBuffer()
    logger = log_buffer.create_logger("pipeline")

    logger.info(f"Pipeline started: root={root_dir}, marker={marker_dir}")

    units = discover_units(root_dir, marker_dir)
    logger.info(f"Discovered {len(units)} units")

    results = parallel_map(units, generator, max_workers, logger)
    report = report_fold(results)

    success_count = sum(1 for result in results if result.is_ok())
    error_count = sum(1 for result in results if result.is_err())

    logger.info(f"Pipeline complete: {success_count} succeeded, {error_count} failed")

    return PipelineResult(report, results, log_buffer.contents)


# ============================================================================
# Independent Mode
# ============================================================================

@dataclass(frozen=True)
class MultiPipelineResult:
    results: dict[str, PipelineResult]

    def write_all(self, output_dir: Path, indent: int = 2) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, result in self.results.items():
            result.write(output_dir / f"{name}.json", indent=indent)


def run_independent(
    root: Path,
    generators: dict[str, Generator],
    marker: str = "translated_rust",
    max_workers: int | None = None,
) -> MultiPipelineResult:
    """Run generators independently with separate outputs."""
    def run_one(name: str, gen: Generator) -> tuple[str, PipelineResult]:
        return name, run_pipeline(root, gen, marker, max_workers)

    results: dict[str, PipelineResult] = {}
    with ThreadPoolExecutor(max_workers=len(generators)) as executor:
        futures = [executor.submit(run_one, name, gen) for name, gen in generators.items()]
        for f in as_completed(futures):
            name, result = f.result()
            results[name] = result

    return MultiPipelineResult(results)


# ============================================================================
# Example Generator
# ============================================================================

@register("example")
def example_generator(directory: Path, logger: logging.Logger) -> dict[str, Any]:
    """
    Example generator: creates a testsuite with one testcase per .rs file.
    
    Replace with your actual analysis logic.
    """
    logger.debug(f"Scanning {directory}")

    rust_dir = directory / "translated_rust"
    rust_files = list(rust_dir.rglob("*.rs")) if rust_dir.exists() else []

    return {
        "name": directory.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "files": [
            {
                "name": rust_file.name,
                "path": str(rust_file.relative_to(directory)),
            }
            for rust_file in rust_files
        ],
    }

# ============================================================================
# Rust Runner Implementation
# ============================================================================

@register("runner")
def runner_generator(directory: Path, logger: logging.Logger) -> dict[str, Any]:
    """
    Rust Runner Generator implementation to run test vectors.
    """
    logger.debug(f"Generating JUnit for Runner on {directory}")

    rust_dir = directory / "translated_rust"
    cargo_toml = rust_dir / "Cargo.toml" if rust_dir.exists() else []

    # Invoke existing Rust Runner
    suite = {
        "name": directory.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    return suite

# ============================================================================
# Rust Unsafe Operations Analysis Implementation
# ============================================================================
@register("unsafeops")
def unsafeops_generator(directory: Path, logger: logging.Logger) -> dict[str, Any]:
    """
    UnsafeOps Runner Generator implementation to run automated unsafe operations analysis.
    """
    logger.debug(f"Generating JSON for UnsafeOps on {directory}")

    rust_dir = directory / "translated_rust"
        
    # Invoke unsafety analysis to produce json output
    unsafeops_results = run_unsafeops(rust_dir)

    suite: dict[str, Any] = {
        "name": directory.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "unsafeops_count": len(unsafeops_results),
        "unsafeops": unsafeops_results,
    }

    return suite

# ============================================================================
# Rust Unsafety Analysis Implementation
# ============================================================================
@register("unsafety")
def unsafety_generator(directory: Path, logger: logging.Logger) -> dict[str, Any]:
    """
    Unsafety Runner Generator implementation to run automated unsafety results.
    """
    logger.debug(f"Generating JSON for Unsafety on {directory}")

    rust_dir = directory / "translated_rust"
        
    # point to the included measure_unsafety project written in Rust
    script_dir = Path(__file__).resolve().parent
    measure_unsafety_dir = script_dir / "static" / "measure_unsafety"

    # Invoke unsafety analysis to produce json output
    unsafety_results = run_unsafety(rust_dir, measure_unsafety_dir)

    suite: dict[str, Any] = {
        "name": directory.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "unsafety": unsafety_results
    }

    return suite

# ============================================================================
# Idiomaticity Analysis Implementation
# ============================================================================
@register("idiomaticity")
def idiomaticity_generator(directory: Path, logger: logging.Logger) -> dict[str, Any]:
    """
    Automated Idiomaticity testing Generator implementation.
    """

    logger.debug(f"Generating JSON for Idiomaticity on {directory}")

    rust_dir = directory / "translated_rust"
    idiomaticity_results = all_idiomaticity_measures(rust_dir)
    suite: dict[str, Any] = {
        "name": directory.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "idiomaticity": idiomaticity_results,
    }
    
    return suite

# ============================================================================
# Binary / Library Size
# ============================================================================
@register("size")
def size_generator(directory: Path, logger: logging.Logger) -> dict[str, Any]:
    """
    Gets the size in bytes for each binary / .so
    NOTE: This requires that the given corpuses given have already been built
    """
    logger.debug(f"Getting size information for {directory}")

    rust_dir = directory / "translated_rust"
    c_dir = directory / "build-ninja"

    if rust_dir.exists():
        artifact_dir = rust_dir / "target" / "release"

        # Make sure there is a Cargo.toml for successful translation
        if not (rust_dir / "Cargo.toml").exists():
            raise RuntimeError("Can't get size information because translation wasn't sucessful")
    elif c_dir.exists():
        artifact_dir = c_dir
    else:
        raise RuntimeError(f"Couldn't find `translated_rust` or `build-ninja` in {directory}")

    artifacts = []
    is_lib = True if "_lib" in str(directory) else False

    if is_lib:
        # Look for all .so files in `artifact_dir`
        total_size = 0
        number_of_libraries = 0
        for file in artifact_dir.iterdir():
            if file.is_file() and file.suffix == ".so":
                total_size += file.stat().st_size
                number_of_libraries += 1
    else:
        artifact = artifact_dir / "driver"
        total_size = artifact.stat().st_size
        number_of_libraries = None
        if not artifact.exists():
            raise RuntimeError("Couldn't find executable named `driver`")

        total_size = artifact.stat().st_size
        artifacts.append(artifact)

    suite: dict[str, Any] = {
        "name": directory.name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_lib": is_lib,
        "artifact_size_bytes": total_size,
        "number_of_libraries": number_of_libraries if number_of_libraries else None
    }

    return suite


# ============================================================================
# CLI
# ============================================================================

def _parse_compose_mode(s: str) -> ComposeMode:
    """Parse string to ComposeMode at CLI boundary."""
    match s.lower():
        case "chain": return ComposeMode.CHAIN
        case "parallel": return ComposeMode.PARALLEL
        case "independent": return ComposeMode.INDEPENDENT
        case _: raise ValueError(f"Unknown mode: {s}")


def _parse_rejoin_strategy(s: str) -> RejoinStrategy:
    """Parse string to RejoinStrategy at CLI boundary."""
    match s.lower():
        case "merge_all": return RejoinStrategy.MERGE_ALL
        case "first_ok": return RejoinStrategy.FIRST_OK
        case "all_must_succeed": return RejoinStrategy.ALL_MUST_SUCCEED
        case "any_must_succeed": return RejoinStrategy.ANY_MUST_SUCCEED
        case _: raise ValueError(f"Unknown rejoin strategy: {s}")

def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Rust analysis runner")
    parser.add_argument("root", type=Path, help="Root directory")
    parser.add_argument("-o", "--output", type=Path, default=Path("report.json"))
    parser.add_argument("-g", "--generators", nargs="+", default=["example"])
    parser.add_argument("-m", "--mode", choices=["chain", "parallel", "independent"],
                        default="chain")
    parser.add_argument("-r", "--rejoin",
                        choices=["merge_all", "first_ok", "all_must_succeed", "any_must_succeed"],
                        default="merge_all")
    parser.add_argument("-w", "--workers", type=int, default=None)
    parser.add_argument("--marker", default="translated_rust")
    parser.add_argument("--list", action="store_true")

    args = parser.parse_args()

    if args.list:
        print("Generators:", ", ".join(list_generators()))
        return
    
    mode = _parse_compose_mode(args.mode)
    rejoin_strategy = _parse_rejoin_strategy(args.rejoin)
    rejoin = rejoin_strategy.to_function()

    match mode:
        case ComposeMode.INDEPENDENT:
            gens = {n: get_generator(n) for n in args.generators}
            runs = run_independent(args.root, gens, args.marker, args.workers)
            runs.write_all(args.output.parent / "results")
            for name, result in runs.results.items():
                print(result.logs)
                print(f"{name}: {result.success_count} ok, {result.error_count} failed\n")
        case ComposeMode.CHAIN | ComposeMode.PARALLEL:
            gen = compose_by_names(args.generators, mode, rejoin)
            result = run_pipeline(args.root, gen, args.marker, args.workers)
            result.write(args.output)
            print(result.logs)
            print(f"\nWrote {args.output}: {result.success_count} ok, {result.error_count} failed")


if __name__ == "__main__":
    main()
