#!/bin/bash -ue

# © 2026 Massachusetts Institute of Technology
# MIT License

set -o pipefail

SCRIPT_DIR=$(cd -- $(dirname ${BASH_SOURCE[0]}) > /dev/null && pwd)
REPO_ROOT=$(cd $SCRIPT_DIR/../.. > /dev/null && pwd)

TS=$(date +'%Y%m%d-%H%M%S')

OUTSIDE=$1

OPTARG=
OPTIND=
XOPT=
VERBOSE=

# Internal flag to suppress relaunching script with output piped to file
WRAPPED=
DRY_RUN=
OUTDIR_BASE=results
DISABLE_ALL_PHASES=
DO_PHASE1=
DO_PHASE2=
RESUME_PHASE1=
TEST_MODE=
MATCH_RE=

while getopts h012m:no:rtwv XOPT; do
    case $XOPT in
        h) cat <<EOF
Run [on AWS] translators on test cases for a specific project. The two phases are:
* phase 1: Convert C to Rust (phase 1), and
* phase 2: give it to the Rust runner [to verify that Rust output matches C output]

$0 [-w] [-0] [-1] [-2] [-m <MATCH_RE>] [-n] [-o <OUTDIR_BASE>] [-t] [-v] <PROJECT> [<DESC>]

-0 : Skip all phases. Just unpack local archived results.
-1 : Only do phase 1 (AWS stuff). Otherwise, just use local archived results.
-2 : Only do phase 2 (rust runner, etc). Otherwise, just skip it.
-m : Only run test keys that match <MATCH_RE> (e.g., "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz")
-n : Do dry-run. Do not actually submit jobs.
-o : Where to write output to (default: "$OUTDIR_BASE")
-v : Show verbose/debug output

<DESC> used to named files (default: current time, e.g., $TS)

If neither -0, -1, nor -2 are specified, default to (-1 -2)

e.g., Following will capture output to directory $OUTDIR_BASE/c2rust.222_b01_b02/
    $0 -o $OUTDIR_BASE -m "B01|B02" c2rust 222_b01_b02

    $0 -o $OUTDIR_BASE -m "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz" c2rust 222_b01_b02

e.g., Following will just do AWS stuff
    $0 -1 c2rust ...

e.g., Following will just do rust analysis
    $0 -2 c2rust ...

e.g., Following will just unpack local archives results (don't do AWS nor rust runner). A file like aws_results.220.b01_b02.c2rust.tbz must already exist)
    $0 -0 c2rust ...

e.g., Following will resume a prior run ($OUTDIR_BASE/c2rust.222_b01_b02/c2rust/aws_batch_translate.log must already exist)
    $0 -o $OUTDIR_BASE -r c2rust 222_b01_b02
EOF
            exit 0
            ;;
        0)  DISABLE_ALL_PHASES=1 ;;
        1)  DO_PHASE1=1 ;;
        2)  DO_PHASE2=1 ;;
        m)  MATCH_RE=$OPTARG ;;
        n)  DRY_RUN=1 ;;
        o)  OUTDIR_BASE=$OPTARG ;;
        r)  RESUME_PHASE1=1 ;;
        t)  TEST_MODE=1 ;;
        w)  WRAPPED=1
            ;;
        v)  VERBOSE=1 ;;
        *)
            echo "Bad option: $XOPT"
            exit 1
            ;;
    esac
done
ORIG_ARGS="$@"
shift `expr $OPTIND - 1`

[ -z "$VERBOSE" ] || set -x

PROJECT=$1
DESC=${2:-$TS}

# Must be absolute path. Make sure we can still locate translator results after we change the current dir.
RESULTS_ROOT_DIR=$PWD/$OUTDIR_BASE/$PROJECT.$DESC

if [ -z "$WRAPPED" ]; then
    # Relaunch this script but with everything logged to a collect.log file
    COLLECT_LOG_FILE="collect.$DESC.$PROJECT.log"

    function relocate_log_file() {
        # Put the top level collect.log together with the results [if they exist]
        if [ -d "$RESULTS_ROOT_DIR/" ]; then
            FINAL_COLLECT_LOG_FILE="$RESULTS_ROOT_DIR/$COLLECT_LOG_FILE"
            if [ -f "$FINAL_COLLECT_LOG_FILE" ]; then
                # Append to existing collect.log [from previous runs]
                cat $FINAL_COLLECT_LOG_FILE $COLLECT_LOG_FILE > $COLLECT_LOG_FILE.tmp
                mv $COLLECT_LOG_FILE.tmp $FINAL_COLLECT_LOG_FILE
            else
                # Relocate collect.log
                mv $COLLECT_LOG_FILE $FINAL_COLLECT_LOG_FILE
            fi
        fi
    }

    # Always move log even on non-0 exit
    trap relocate_log_file EXIT

    # Replace current proc with the main program (i.e., stuff after "Running AWS jobs ..."
    exec $0 -w $ORIG_ARGS 2>&1 | tee $COLLECT_LOG_FILE

    # NB: Next line strictly *not* necessary as exec skip it ... but put it there as defensive just-in-case
    exit $?
fi
# else Script relaunched => do the normal main program

if [ -z "$DISABLE_ALL_PHASES" -a -z "$DO_PHASE1" -a -z "$DO_PHASE2" ]; then
    # Neither -1 nor -2 specified, default to both being specified
    DO_PHASE1=1
    DO_PHASE2=1
fi

# if [ -n "$DO_PHASE1" ]; then
#     echo "Running AWS jobs ..."
# else
#     echo "NOT running AWS jobs (instead use archived results) ..."
# fi
# if [ -z "$DO_PHASE2" ]; then
#     echo "NOT running rust runner ..."
# else
#     echo "Running rust runner ..."
# fi
# exit 43

if [ -n "$RESUME_PHASE1" -a -n "$MATCH_RE" ]; then
    # Filter test keys only works when submitting new jobs. -r will resume old jobs.
    echo "Cannot filter test keys (-m) when resuming old jobs (-r)"
    exit 1
fi

if [ -n "$DO_PHASE1" ]; then
    # Run translator and put results into results/

    echo "Running AWS jobs ..."

    # $SCRIPT_DIR/aws_batch_translate.sh -o $RESULTS_ROOT_DIR -T $TS -m "B01|B02" $PROJECT
    case $PROJECT in
        c2rust|self-host-llm|llm|aarno|galois|harvest|intel|uwisc|yale)
            COLLECT_ARGS=""
            if [ -n "$RESUME_PHASE1" ]; then
                # from file like result/c2rust.220_b01_b02/c2rust/aws_batch_translate.log, parsed out the line:
                #   LOG_IDS=JOB_ID JOB_ID2 ...

                # Temporarily disable error check because grep can fail
                set +e
                JOB_IDS="$(grep '^JOB_IDS' $RESULTS_ROOT_DIR/$PROJECT/aws_batch_translate.log | tail -1 | awk -F= '{print $2}')"
                set -e

                if [ -z "$JOB_IDS" ]; then
                    echo "Cannot find JOB_IDS to resume. Check the file $RESULTS_ROOT_DIR/$PROJECT/aws_batch_translate.log"
                    exit 1
                fi
                echo "Resuming jobs: $JOB_IDS"
                COLLECT_ARGS="$PROJECT $JOB_IDS"
            else
                COLLECT_ARGS="$PROJECT"
            fi
            $SCRIPT_DIR/aws_batch_translate.sh -o $RESULTS_ROOT_DIR -T $TS ${MATCH_RE:+-m "$MATCH_RE"} ${DRY_RUN:+-n} ${TEST_MODE:+-t} ${VERBOSE:+-v} $COLLECT_ARGS
            ;;
        *)
            echo "Unsupported project: $PROJECT"
            exit 1
            # $SCRIPT_DIR/aws_batch_translate.sh -o $RESULTS_ROOT_DIR -T $TS -t $PROJECT
            ;;
    esac

    # Grab snapshot of results _before_ we do analysis on it. That way, if analysis fails, we can retry it w/o redoing AWS stuff.
    AWS_ARCH_0="aws_results.$DESC.$PROJECT.tbz"
    AWS_ARCH="$AWS_ARCH_0"
    COUNT=1
    while true; do
        if [ ! -f "$AWS_ARCH" ]; then
            break
        fi
        AWS_ARCH="$(basename -s .tbz $AWS_ARCH_0)-$(printf '%.2d' $COUNT).tbz"
        COUNT=`expr $COUNT + 1`
    done
    echo "Archiving results: $AWS_ARCH"
    tar cfj $AWS_ARCH -C $RESULTS_ROOT_DIR --checkpoint-action=dot . # e.g., tar cfvj aws_results.220.go.c2rust.tbz -C results/c2rust.220.go.tbz
else
    echo "NOT running AWS jobs (but will instead use archived results) ..."

    # NB: Use "sed" to position foo.tbz before foo-1.tbz in sort (i.e., we prefer foo-2.tbz over foo-1.tbz over foo.tbz)
    AWS_ARCH=$(ls -1 aws_results.$DESC.$PROJECT*.tbz | sed -Ee 's/([^0-9])\.tbz/\1-00.tbz/' | sort | sed -Ee 's/-00\.tbz/.tbz/' | tail -1)
    if [ ! -f "$AWS_ARCH" ]; then
        echo "Cannot locate $AWS_ARCH archived from a prior run. Run $0 run first either with -1 or without -2"
        exit 1
    fi

    echo "Unpacking archived results $AWS_ARCH ..."
    mkdir -p $RESULTS_ROOT_DIR
    tar xf $AWS_ARCH -C $RESULTS_ROOT_DIR --checkpoint-action=dot
fi

if [ -z "$DO_PHASE2" ]; then
    echo "NOT running rust runner ..."
    exit 0
fi

echo "Running rust runner ..."

# Inputs may be specified as relative paths. Make sure we can still locate them after we change the current dir.
ORIG_PWD=$PWD

# Run rust runner to validate that translated Rust has correct output

# Set up directories needed by Rust runner
# NB: extract_and_copy.sh will copy tools/ + deployment/ from repo to current dir
# Rust outputted [from C] by translator
TRANSLATOR_RESULTS_DIR=$RESULTS_ROOT_DIR

# Location of test vectors [used to verify Rust output is correct].
# Default to current repo. But can be different Test-Corpus mono repo checkout
# so that runner code can be tested with older/newer test vectors.
TEST_VECTOR_DIR=${TEST_VECTOR_DIR:-$(cd $SCRIPT_DIR/../.. > /dev/null && pwd)}

set -x
# $SCRIPT_DIR/extract_and_copy.sh $TRANSLATOR_RESULTS_DIR $TEST_VECTOR_DIR $REPO_ROOT
for x in Public-Tests Hidden-Tests Backup-Tests; do
    if [ -d "$TRANSLATOR_RESULTS_DIR/$PROJECT/$x" ]; then
        $SCRIPT_DIR/extract_and_copy.sh $TRANSLATOR_RESULTS_DIR/$PROJECT/$x $TEST_VECTOR_DIR/$x $REPO_ROOT
    fi
done

cd $TRANSLATOR_RESULTS_DIR/$PROJECT
if true; then
    cp $REPO_ROOT/rust-toolchain.toml .
else
    ln -fns $REPO_ROOT/rust-toolchain.toml rust-toolchain.toml
fi

# Run Rust runner
./deployment/scripts/github-actions/run_rust.sh --keep-going

echo "================================================================================"
echo "All results"
if ! ./deployment/scripts/github-actions/run_rust.sh -x junit.xml --keep-going; then
    echo "Some tests failed"
fi

echo "================================================================================"
echo "B01 results"
if ! ./deployment/scripts/github-actions/run_rust.sh -x junit-b01.xml -m B01 --keep-going; then
    echo "Some B01 tests failed"
fi

echo "================================================================================"
echo "B02 results"
if ! ./deployment/scripts/github-actions/run_rust.sh -x junit-b02.xml -m B02 --keep-going; then
    echo "Some B02 tests failed"
fi

# vim:et
