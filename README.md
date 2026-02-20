DISTRIBUTION STATEMENT A. Approved for public release. Distribution is unlimited.

This material is based upon work supported by the Under Secretary of War for
Research and Engineering under Air Force Contract No. FA8702-15-D-0001 or
FA8702-25-D-B002. Any opinions, findings, conclusions or recommendations
expressed in this material are those of the author(s) and do not necessarily
reflect the views of the Under Secretary of War for Research and Engineering.
 
© 2026 Massachusetts Institute of Technology.

The software/firmware is provided to you on an As-Is basis Delivered to the
U.S. Government with Unlimited Rights, as defined in DFARS Part 252.227-7013 or
7014 (Feb 2014). Notwithstanding any copyright notice, U.S. Government rights
in this work are defined by DFARS 252.227-7013 or DFARS 252.227-7014 as
detailed above. 

<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->

- [Test Corpus Organization](#test-corpus-organization)
  - [Top Level Structure](#top-level-structure)
- [Test Case Structure:](#test-case-structure)
- [Test Runner (found here)](#test-runner-found-here)
  - [Test Runner Phases](#test-runner-phases)
  - [Requirements](#requirements)
  - [Quick Start](#quick-start)
  - [Repository Expectations](#repository-expectations)
  - [Discovery and Selection](#discovery-and-selection)
  - [Configure and Build](#configure-and-build)
  - [Testing Model](#testing-model)
    - [Executables (`ExecRunner`)](#executables-execrunner)
    - [Libraries (`LibRunner`)](#libraries-librunner)
  - [Test Vector Schema (JSON)](#test-vector-schema-json)
    - [Executable Tests](#executable-tests)
      - [Examples](#examples)
    - [Library Tests](#library-tests)
      - [Examples](#examples-1)
  - [JUnit-style XML Output](#junit-style-xml-output)
  - [CLI Reference](#cli-reference)
  - [Troubleshooting](#troubleshooting)
- [AWS Batch Runner](#aws-batch-runner)
- [Notes](#notes)
  - [Expected Output of CI Script on Public-Tests](#expected-output-of-ci-script-on-public-tests)
  - [Skipped Test Vectors](#skipped-test-vectors)
  - [Skipped Tests Cases: Long-running Tests](#skipped-tests-cases-long-running-tests)
- [Running Against Rust Translations](#running-against-rust-translations)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Test Corpus Organization
This repository contains C projects to translate into Rust for the TRACTOR program.

The files contained here are sorted into batteries and projects.

## Top Level Structure
The major directory heirarchy is as follows:
1. Visibility
2. Bundles
3. Test Cases
4. Test Vectors

The top level defines the visibility of the translation being tested and is composed of three kinds of visibility (Explicitly, three subdirectories): `Public-Tests`, `Hidden-Tests`, and `Backup-Tests`. 
The `Hidden-Tests` contain additional examples of the features in `Public-Tests` and will be used during the evaluation period. The `Backup-Tests` are reserved and not anticipated to be used. 

When a test battery is first released, only `Public-Tests` will be available; after each evaluation period the the `Hidden-Tests` and any `Backup-Tests` used in the evaluation will be released. 
Before release, the `Hidden-Tests` and `Backup-Tests` are included as submodules which are only accessible from the Lincoln Laboratory intranet.

Bundles form the next level of the hierarchy and correspond to test releases following the three naming schemes: `B##_synthetic`, `B##_organic`, and `P##_<project name>`.

- Directories starting with B are part of a test battery; for instance, `B01_synthetic` contains synthetic C projects, while `B01_organic` contains C projects drawn from real-world code.
- Directories starting with a P contain a major test project.

  These test examples are larger and more complicated than the C projects found in a test battery.
  For example, [`P00_perlin_noise`](./P00_perlin_noise) contains a real-world library for generating Perlin noise.

Test Cases form the next level of the hierarchy and correspond to specific C code for translation.
If a test case's folder name ends in `_lib`, it is a library to be translated; otherwise, it is an executable to be translated.
Some test cases exist in both library and executable forms.

Test Vectors contain inputs and expected outputs for Test Cases represented in JSON format.


# Test Case Structure:
Both major and minor test cases have the same basic folder structure, containing:
- `test_case`, the C test case to be converted. This directory is all that will be provided to the translation tool during translation.
    - `src`, containing the `.c` and any `.h` files private to the implementation.
        - If the test case compiles to produce a single executable, these files will include `main.c`, a file containing the `main()` entry point.
        - If the test case compiles to produce a library instead of an executable, the file is `lib.c`.
    - `include` if the test case is a library, containing any `.h` files it exposes to callers.
        - If the test case is not a library, there will be no `include`.
    - `CMakeLists.txt`, a simple cmake file that builds the test case.
        - Note that this file will include `add_executable()` if the test case produces an executable, and `add_library()` if the test case produces a library.
        - Example usage from a `test_case` directory:
        ```
        cmake -S ./test_case -B ./build-ninja -G Ninja
        cd build-ninja
        cmake --build ./
        ```
        Afterwards, `build-ninja` will contain the compiled library or executable.

        If presets exist, instead run `cmake -S ./test-case --preset test`.
        
        While you can build test cases manually, the provided [Python script](deployment/scripts/github-actions/runtests) is the intended means of building and executing the provided C test cases against their test vectors.
- `test_vectors`, a folder meant to contain all material for testing; each test case is a JSON file containing a dictionary. Each JSON specifies a single input/output pair, with entries:
   - "argv": Input arguments for executable tests
   - "stdin": Standard input (default empty)
   - "stdout": A dictionary containing a "pattern" for standard output (default empty) and a flag "is_regex" indicating the pattern should be compiled as regex before comparison
   - "stderr": A dictionary containing a "pattern" for standard error (default empty) and a flag "is_regex" indicating the pattern should be compiled as regex before comparison
   - "rc": Return code (default 0)
   - "has_ub": A string describing how the test vector exhibits undefined behavior. If this field is present, the test vector must be manually evaluated and will be skipped by the automated instrumentation
   - "lib_state_in": An Object containing the state of a program running a library function including all provided arguments and, if present, return values initialized to the default value of their type.
   - "lib_state_out": An object containing the state after library function execution modifies outputs by return or inputs by reference.

  For details on the expected contents of an executable or library test, see [Test Vector Schema (JSON)](README.md#test-vector-schema-json)

- `runner`, if the test case is a library, there will be a small Rust project which calls an exposed function from that library via FFI. This runner leverages a Rust project we've developed named [cando](tools/cando/).
   - `Cargo.toml`: Provided to `cargo` to build a `cando` runner linked against the library under test
   - `src`
     - `lib.rs`: Contains locations of the shared object, the name of the library function, serialization info, and sets up the call to execute the library function
     - `main.rs`: Boilerplate calling the `conduct` function from `cando`
   - `Cargo.lock`

# Test Runner ([found here](deployment/scripts/github-actions/runtests/))
For automated building and testing of the batteries and projects, we have provided a runner which discovers the test cases, configures them with CMake/Ninja, builds them, and runs the test vectors 
for each discovered test case. The runner works for all bundles (projects and battery), and includes both the executable and library forms as applicable.

Afterwards, the script emits a colorized console summary along with an optional JUnit-style XML report.

## Test Runner Phases

- **Build**: CMake + Ninja
- **Discovery**: Valid hierarchy for test cases is any directory containing `test_case/` along with `test_vectors/`.
- **Test Modes**: Runs executable driver or a runner that links against a shared library.
- **Reporting**: Console and optional XML.

## Requirements

`cmake`, `ninja`, and `cargo` must be present in `PATH`. `python` version 3.11+ is additionally required for running the script.
> [!NOTE]
> `cargo` is required up front because the library tests compile a Rust runner and the CLI validates the toolchain at startup.

## Quick Start
```bash
# From the root of the repository
./deployment/scripts/github-actions/run-ci.sh \
    --jobs 0 \
    --junit-xml junit.xml
```
Common flags:
- `--jobs ##` -- Parallel jobs allowed. `--jobs 0` uses all available cores.
- `--match "_lib"` -- Filter by regex (Repeatable, multiple instances are joined by disjunction).
- `--subset "Public-Tests"` -- Test explicit subsets of test case(s) (Repeatable, multiple instances are joined by disjunction).
- `--keep-going` -- Continue after failures.
- `--build-timeout 600` -- Cap the configuration and build phases (in seconds).
- `--test-timeout 120` -- Cap test runs to 2 minutes.
- `--skip-lib-tests` -- Build the library-based tests (any case with the suffix "_lib"), but don't run their test vectors.
- `--verbose` -- Include tool output and unified diffs on failures.
- `--list` -- Perform the test discovery phase and exit without building or running any tests.
Exit codes:
- `0`: All configuration, builds, and tests succeeded.
- `1`: One or more failures occured
    - No test cases were found for a given set of `--subset` and `--match` constraints
    - One or more test case builds or configures failed
    - One or more test vectors failed
- `2`: Required tool was not found in `PATH`

## Repository Expectations
```python
test_case/         # CMake source directory which contains the top-level (except build overrides) CMakeLists.txt
test_vectors/      # JSON files defining test vectors (see schema below)
CMakePresets.json  # (Optional) Per-test build configurations. Must define a "test" configure preset
CMakeLists.txt     # (Optional) Build Overrides such as set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ...)
runner/            # Only for libraries. Cargo project used by cando.
```
Library tests are identified by a directory name ending with `_lib`.

## Discovery and Selection
1. By default, the runner scans these top-level folders under `--root`:
   ```
    Backup-Tests/    Hidden-Tests/    Public-Tests/
   ```
2. A **Bundle** is a directory whose immediate subdirectories are test cases. A bundle will follow the naming convention `^[BP]([0-9]+)_.*`.
3. A **Test Case** is any directory that contains both `test_case/` and `test_vectors/`.
4. You can narrow the search set for test cases with:
    - `--match REGEX` (repeatable; given a relative path to a test case, selected if the path matches the regex)
    - `--subset DIR` (repeatable; either absolute or relative to `--root` path to a directory containing bundles, test cases, or test_vectors)
5. `--list` prints the discovered test cases and exits.

## Configure and Build
- The runner configures non-preset cases into `build-ninja/`:
  ```bash
  cmake -S ./test_case -B ./build-ninja -G Ninja
  ```
  and builds from that directory (`./build-ninja`).

- If `CMakePresets.json` exists in a text case directory and defined a configure preset named `test`, the configuration step uses
  ```bash
  cmake -S <case_dir> --preset test
  ```
  and the build directory is taken from the preset's binaryDir (with `sourceDir` expanded).

- Builds use:
  ```bash
  cmake --build --preset test # when using presets (cwd=./test_case)
  cmake --build ./            # when not using presets (cwd=./test_case)
  ```

## Testing Model
### Executables (`ExecRunner`)
- For each JSON file (test vector) in `test_vectors`:
    - If the JSON file defines a `has_ub` member, the test vector is skipped.
    - Run the previously-built driver at `build-ninja/driver`
    - Pass `argv` from the vector's `args` member defaulting to no arguments.
    - Pass `stdin` from the vector's `stdin` member defaulting to empty stdin.
    - Capture the return code, `stdout`, and `stderr`.
    - Compare the return code from running the driver to the vector's `rc` member defaulting to comparing against `0`.
    - Compare the captured `std{out/err}` from running the driver to the vector's `std{out/err}` member.
        - If `is_regex = true`, compare against the `std{out/err}` member as regex, otherwise as exact strings.
        - Default to `stdout = {pattern = "", is_regex = false}` and `stderr = {pattern = "", is_regex = false}` (expect no output)

### Libraries (`LibRunner`)
- Builds the Rust runner in `runner/` with:
  ```bash
  cargo build --release --target-dir <testcase_dir>/runner
  ```
- For each JSON file (test vector) in `test_vectors`:
    - If the JSON file defines a `has_ub` member, the test vector is skipped.
    - Run the previously-built runner `release/runner lib -c <testname>.json`
    - Use the same `std{out/err}` rules as the executable tests.
> [!NOTE]
> 1. The LibRunner (`cando`) expects that any shared object files produced by the CMake process are at the root of `build-ninja/`
> 2. `runner/` must be a valid Cargo project with a `runner` binary target.

## Test Vector Schema (JSON)
### Executable Tests
```json
{
  "argv": ["--flag", "value"],                         // optional; appended after the driver path
  "stdin": "input string\n",                           // optional
  "rc": 0,                                             // optional; default 0
  "stdout": { "pattern": "ok\n", "is_regex": false },  // exact by default
  "stderr": { "pattern": "", "is_regex": false },      // exact by default
  "has_ub": "overflow"                                 // optional; if present, test is skipped
}
```
#### Examples
Define a test vector which provides a single argument (`"10"`), no stdin, and expects a return code of 0, an _exact_ stdout of `42\n`, and no stderr. 
```json
{
  "argv": ["10"],
  "stdout": { "pattern": "42\n" },
  "stderr": { "pattern": "" }
}
```

Define a test vector which provides no arguments, no stdin, and expects a return code of 0, any stdout of matching the regex `^result: [0-9]+\\n`, and no stderr. 
```json
{
  "stdout": { "pattern": "^result: [0-9]+\\n$", "is_regex": true },
  "stderr": { "pattern": "" }
}
```

Define a test vector which will be skipped during automated testing. Additionally provide a note explaining why the test vector is being skipped.
```json
{ "stdin": "input string causing a buffer overflow\n", 
  "has_ub": "Buffer Overflow" }
```

### Library Tests
```json
{
  "stdin": "input string\n",                           // optional
  "lib_state_in": {                                    // defines initial state before running test
    "foo": 1,
    "bar": 2, 
  },
  "lib_state_out": {                                   // defined terminal state after running test
    "foo": 3,
    "bar": 4, 
  },
  "stdout": { "pattern": "ok\n", "is_regex": false },  // exact by default
  "stderr": { "pattern": "", "is_regex": false },      // exact by default
  "has_ub": "overflow"                                 // optional; if present, test is skipped
}
```

#### Examples
Define a test vector which provides no stdin, an initial state of `foo = 11`, and expects a return code of 0, an _exact_ stdout of `42\n`, no stderr, an a terminal state of `foo = 9`.  
```json
{
  "stdout": {
    "pattern": "42\n"
  },
  "lib_state_in": {
    "foo": 11
  },
  "lib_state_out": {
    "foo": 9
  }
}
```

Define a test vector which will be skipped during automated testing. Additionally provide a note explaining why the test vector is being skipped.
```json
{
  "lib_state_in": {
    "foo": "Input string causing a buffer overflow\n"
  },
  "has_ub": "Buffer Overflow" }
```

## JUnit-style XML Output
Add `--junit-xml path/to/junit.xml` to write an XML summary. The structure is:
```xml
<?xml version='1.0' encoding='utf-8'>
<!-- Here, N F E and S are relative to the test cases -->
<testsuites name="Tests" tests="N" failures="F" errors="E" skipped="S">
  <!-- Here, N F E and S are relative to the test vectors -->
  <testsuite name="Public-Tests/foo/bar" tests="N" failures="F" errors="E" skipped="S">
    <testcase name="configure" classname="Public-Tests/foo"/>
    <testcase name="build" classname="Public-Tests/foo"/>
    <testcase name="execution" classname="Public-Tests/foo/bar">
      <!-- Only present if an execution error occurs -->
    </testcase>
    <!-- Passed vectors have no child element -->
    <testcase name="vector_name" classname="Public-Tests/foo/bar"/>
    <testcase name="vector_name" classname="Public-Tests/foo/bar">
      <failure message="...">
      <!-- Only present if a given test vector fails -->
      </failure>
    </testcase>
    <testcase name="vector_name" classname="Public-Tests/foo/bar">
      <!-- Only present if a given test vector is skipped (for instance, due to UB) -->
      <skipped message="..."/>
    </testcase>
  </testsuite>
</testsuites>
```

- A junit **suite** corresponds to a "test case" in our terminology (keyed by its relative path)
- Built-in **testcase**s correspond to a "test vector" in our terminology. They include `configure`, `build`, an `execution` error on runner failure, and one entry per JSON vector.
- Status mapping:
  - If the vector passes, is not skipped, and runs, we produce no child element
  - If the vector fails, is not skipped, and runs, we produce a `<failure/>` child element
  - If the vector fails to run, we produce an `<error/>` child element
  - If the vector is skipped, we produce a `<skipped/>` child element

## CLI Reference
```bash
usage: run-ci.sh [-h] [--root ROOT] [-j JOBS] [-m MATCH_REGEX] [-s SUBSET]
                 [-t TIMEOUT] [-x JUNIT_XML] [--clean] [--keep-going]
                 [--list] [--no-color] [--skip-lib-tests] [--verbose]
                 [--only ONLY] [--config-fuzz] [--asan]
CI testing

options:
  -h, --help            show this help message and exit
  --root ROOT           Path to root (default: current working directory)
  -j, --jobs JOBS       Parallel build and configure jobs (default = use all
                        cores) (default: None)
  -m, --match-regex MATCH_REGEX
                        Regex to select test cases by their relative path; can
                        be repeated (default: [])
  -s, --subset SUBSET   Explicit directories to search for tests; can be
                        repeated. Relative to --root unless absolute.
                        (default: [])
  --build-timeout BUILD_TIMEOUT
                        Set a timeout (in seconds) for building tests (default: None)
  --test-timeout TEST_TIMEOUT
                        Set a timeout (in seconds) for running tests (default: 120)
  -x, --junit-xml JUNIT_XML
                        Write a JUnit XML report to this path (default: None)
  --clean               Delete temporary build artifacts (default: False)
  --keep-going          Continue building and running other testcases if one
                        fails (default: False)
  --list                List selected test cases and exit (default: False)
  --no-color            Don't use escape codes for coloring output (default:
                        False)
  --skip-lib-tests      Don't run the tests for libraries (default: False)
  --verbose             Print all command output (default: False)
  --only ONLY           Select a single pass to perform of `config`, `build`,
                        `build-runner`, `test` (default: None)
  --config-fuzz         Configure test cases to build with fuzzing support
                        (default: False)
  --asan                Enable building with asan and ubsan (default: False)
```

## Troubleshooting
- **Tool Missing** (`cmake`, `cargo`, `ninja`):

  The runner exits with code `2`. Ensure the tools are on `PATH`.
- **Wrong Python Version**:

  If you received a `python` error for `match` or `StrEnum`, ensure your `python` version is at least `3.11`.
- **Preset not Used**:

  Ensure `CMakePresets.json` defined the configure preset named `"test"` and includes `binaryDir`.
- **Library Runner Fails to Build**:

  Confirm that `runner/` is a valid Cargo project with a `runner` binary target.
- **No Test Cases Found**:

  If using `-s` and / or `-m`, check if the folders exist and there is a test case in their intersection.
  Additionally, ensure that your test case directory has a `test_case` and `test_vector` folder.
  Note that `-s` and `-m` cannot be used to select for a specific test _vector_, only test _cases_.

# AWS Batch Runner

Translations and rust runner can be run en masse via [AWS Batch](https://aws.amazon.com/batch/).

[collect_all_results.sh](tools/aws_translate/collect_results.sh) is the main script \[that can be run from any directory]. The following gives an idea of how to use it:

```
collect_all_results.sh [-m <TEST_MATCH_RE>] [-o <OUTDIR_BASE>] [-p <PROJECT_MATCH_RE>] [-r] [<DESC>]

-0 : Skip all phases. Just unpack local archived results.
-1 : Only do phase 1 (AWS stuff). Otherwise, just use local archived results.
-2 : Only do phase 2 (rust runner, etc). Otherwise, just skip it.
-m : Only run test keys that match <MATCH_RE> (e.g., "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz")
-n : Do dry-run. Do not actually submit jobs.
-o : Where to write output to (default: "results")
-p : Only run projects that match <PROJECT_MATCH_RE>
-r : Resume a previous AWS run
-t : Run in test-mode (alias for -m DEFAULT_TEST_MODE_MATCH_RE)

<DESC> Optional description for run

e.g., Following will run B01 + B01 on baselines (submit *new* jobs + run rust runner)
    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust|llm|self-host-llm" -m "B01|B02"

    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust" -m "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz"

e.g., Following will run spot checks on performers (submit *new* jobs + run rust runner)
    ./tools/aws_translate/collect_all_results.sh -o results -p "aarno|galois|harvest|intel|uwisc|yale" -t

    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust" -t

e.g., Following will resume a prior run (results/c2rust.222_b01_b02/c2rust/aws_batch_translate.log must already exist)
    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust" -r

e.g., Following will only do AWS stuff
    ./tools/aws_translate/collect_all_results.sh -1 ...

e.g., Following will only do rust runner
    ./tools/aws_translate/collect_all_results.sh -2 ...

e.g., Following will only unpack local archives results (don't do AWS nor rust runner). A file like aws_results.220.b01_b02.c2rust.tbz must already exist)
    ./tools/aws_translate/collect_all_results.sh -0 -o results -p "c2rust"

e.g., Following will run the rust runner from archived AWS results for c2rust
    cp -p /mnt/llfs_div5/Projects/TRACTOR/results/aws_results.220.b01_b02.c2rust.tbz .
    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust" -0     # to create results/ unpacked from .tbz
    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust" -r     # if you want to include AWS steps (e.g., refetch S3)
    ./tools/aws_translate/collect_all_results.sh -o results -p "c2rust" -2 -r  # if you want to skip AWS

e.g., Following will cancel a run
    ./tools/aws_translate/collect_all_results.sh ...
    Ctrl+C
```

# Notes
## Expected Output of CI Script on Public-Tests
<pre>
Summary:
- Test Cases Discovered:      338
- Test Cases Skipped:         2
- Test Cases Tested:          336
- Test Cases Failed:          0
- Test Vectors Passed:        2612
- Test Vectors Skipped:       158
- Test Vectors Failed:        0
</pre>
## Skipped Test Vectors
There are currently 158 test vectors in the Public-Tests corpus which are marked as having undefined behavior. These tests will come up as "Skipped" in the CI script's output. A list of these tests is included [here](Public-Tests-UB.md).

## Skipped Tests Cases: Long-running Tests 
There are currently two test cases marked as "Skipped". This is because the only test vector for these cases is [marked](Public-Tests/B01_synthetic/008_long_run/test_vectors/76.json.bak) as [backup](Public-Tests/B01_synthetic/008_long_run_lib/test_vectors/76.json.bak). If you would like to run this test manually, simply rename the file to 76.json.

# Running Against Rust Translations
While we plan to exercise most of the testing behavior on AWS through Docker, the Test Runner in this repository also supports a feature to compile and run Rust translations of a test case against the test vectors. To exercise this feature, you can call the sibling script `run-rust.sh` with the same arguments (modulo `--asan`). When using the rust script, instead of building against a `test_case` directory the script will instead search for a directory `translated_rust`, run `cargo` to build the library or executable, and store it in `translated_rust/target`. The Test Runner will then perform the normal evaluation operations against the binary or shared library produced from the translated Rust. While we do not embed a translator to demonstrate this behavior in this repository (nor automate it at this time), the existing C2Rust translator container in the `pipeline-automation` repository can be used to translate a `test_case`. 

> [!NOTE]
> Please note that by default C2Rust produces a static library. If you use our translator, you will need to modify the `Cargo.toml` file in the translated test case to produce a `cdylib` to be compatible with the instrumentation in `cando`.
