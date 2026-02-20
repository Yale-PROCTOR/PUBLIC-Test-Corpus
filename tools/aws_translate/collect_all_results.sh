#!/bin/bash -ue

# © 2026 Massachusetts Institute of Technology
# MIT License

#
# Run collect_results.sh on all the translators [in parallel]

set -o pipefail

SCRIPT_DIR=$(cd -- $(dirname ${BASH_SOURCE[0]}) > /dev/null && pwd)

# All the projects to evaluate
# The numbers are used to name output directories (i.e,. bumped up to prevent new runs from overwriting old runs)

OFFSET=0

ALL_PROJECT_CONFIGS="
    self-host-llm:$((200 + $OFFSET)) \
    llm:$((210 + $OFFSET)) \
    c$((2 + $OFFSET))rust:220 \
    aarno:$((300 + $OFFSET)) \
    galois:$((310 + $OFFSET)) \
    harvest:$((320 + $OFFSET)) \
    intel:$((330 + $OFFSET)) \
    uwisc:$((340 + $OFFSET)) \
    yale:$((350 + $OFFSET)) \
    "

XPIDS=

OPTARG=
OPTIND=
XOPT=
VERBOSE=

DRY_RUN=
TEST_MATCH_RE=
PROJECT_MATCH_RE=
OUTDIR_BASE=results
COLLECT_ARGS=""

while getopts h0123m:no:p:rtv XOPT; do
    case $XOPT in
        h) cat <<EOF
Run [on AWS] translators on test cases for a specific project. The two phases are:
* phase 1: Convert C to Rust (phase 1), and
* phase 2: give it to the Rust runner [to verify that Rust output matches C output]

$0 [-m <TEST_MATCH_RE>] [-o <OUTDIR_BASE>] [-p <PROJECT_MATCH_RE>] [-r] [<DESC>]

-0 : Skip all phases. Just unpack local archived results.
-1 : Only do phase 1 (AWS stuff). Otherwise, just use local archived results.
-2 : Only do phase 2 (rust runner, etc). Otherwise, just skip it.
-m : Only run test keys that match <MATCH_RE> (e.g., "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz")
-n : Do dry-run. Do not actually submit jobs.
-o : Where to write output to (default: "$OUTDIR_BASE")
-p : Only run projects that match <PROJECT_MATCH_RE>
-r : Resume a previous AWS run
-t : Run in test-mode (alias for -m DEFAULT_TEST_MODE_MATCH_RE)

<DESC> Optional description for run

e.g., Following will run B01 + B01 on baselines (submit *new* jobs + run rust runner)
    $0 -o $OUTDIR_BASE -p "c2rust|llm|self-host-llm" -m "B01|B02"

    $0 -o $OUTDIR_BASE -p "c2rust" -m "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz"

e.g., Following will run spot checks on performers (submit *new* jobs + run rust runner)
    $0 -o $OUTDIR_BASE -p "aarno|galois|harvest|intel|uwisc|yale" -t

    $0 -o $OUTDIR_BASE -p "c2rust" -t

e.g., Following will resume a prior run ($OUTDIR_BASE/c2rust.222_b01_b02/c2rust/aws_batch_translate.log must already exist)
    $0 -o $OUTDIR_BASE -p "c2rust" -r

e.g., Following will only do AWS stuff
    $0 -1 ...

e.g., Following will only do rust runner
    $0 -2 ...

e.g., Following will only unpack local archives results (don't do AWS nor rust runner). A file like aws_results.220.b01_b02.c2rust.tbz must already exist)
    $0 -0 -o $OUTDIR_BASE -p "c2rust"

e.g., Following will run the rust runner from archived AWS results for c2rust
    cp -p /mnt/llfs_div5/Projects/TRACTOR/results/aws_results.220.b01_b02.c2rust.tbz .
    $0 -o $OUTDIR_BASE -p "c2rust" -0     # to create results.50/ unpacked from .tbz
    $0 -o $OUTDIR_BASE -p "c2rust" -r     # if you want to include AWS steps (e.g., refetch S3)
    $0 -o $OUTDIR_BASE -p "c2rust" -2 -r  # if you want to skip AWS

e.g., Following will cancel a run
    $0 ...
    Ctrl+C
EOF
            exit 0
            ;;
        0)  COLLECT_ARGS="$COLLECT_ARGS -0" ;;
        1)  COLLECT_ARGS="$COLLECT_ARGS -1" ;;
        2)  COLLECT_ARGS="$COLLECT_ARGS -2" ;;
        m)  TEST_MATCH_RE=$OPTARG ;;
        n)  COLLECT_ARGS="$COLLECT_ARGS -n" ;;
        o)  OUTDIR_BASE=$OPTARG ;;
        p)  PROJECT_MATCH_RE=$OPTARG ;;
        r)  COLLECT_ARGS="$COLLECT_ARGS -r" ;;
        t)  COLLECT_ARGS="$COLLECT_ARGS -t" ;;
        v)  VERBOSE=1 ;;
        *)
            echo "Bad option: $XOPT"
            exit 1
            ;;
    esac
done
shift `expr $OPTIND - 1`

DESC_SUFFIX=${1:-}

if [ $# -gt 1 ]; then
    echo "Too many arguments"
    exit 1
fi

[ -z "$VERBOSE" ] || set -x

if [ -z "$PROJECT_MATCH_RE" -a -z "$TEST_MATCH_RE" ]; then
    echo -n "You will run all projects (if this is not what you want, try using the -p or -m options).  Are you sure? (y/N) "
    read YES_NO
    if [ "$YES_NO" != "y" ]; then
        exit 0
    fi
fi

IS_ABORTING=

function abort() {
    # Ignore errors. We don't want killing non-existent PID to preventing killing of other PID
    if [ -n "$IS_ABORTING" ]; then
        # Prevent abort() from infinitely recursing (possible because initial collect_all_process.sh has PID == GPID)
        return
    fi
    IS_ABORTING=1
    set +e
    # Kill all children processes, which all inherit collect_all_results.sh's PID as their GPID.
    # NB: negative PID causes kill to send to entire group, not just single
    # process. This is more robust than killing individual procs because child
    # proc may spawn more procs but may not necessary propagate signals.
    echo "Killing GPID=$$ ..."
    kill -- -$$
    # Wait for termination
    join
}

# Terminate background/child processes on Ctrl-C (otherwise, they continue running orphaned)
trap abort INT TERM

function join() {
    for P in $XPIDS; do
        echo "Waiting on PID=$P ..."
        wait $P
    done
}

function run_batch_for_project() {
    local PROJECT_CONFIG=$1
    local DESC_SUFFIX=${2:-}

    PROJECT=$(echo $PROJECT_CONFIG | cut -d: -f1)
    NUMBER=$(echo $PROJECT_CONFIG | cut -d: -f2)

    if [ -z "$PROJECT_MATCH_RE" ] || echo "$PROJECT" | egrep -q "^($PROJECT_MATCH_RE)\$"; then
        echo "Collecting results for project $PROJECT ..."
        $SCRIPT_DIR/collect_results.sh $COLLECT_ARGS ${VERBOSE:+-v} ${TEST_MATCH_RE:+-m "$TEST_MATCH_RE"} -o $OUTDIR_BASE $PROJECT "$NUMBER${DESC_SUFFIX:+.$DESC_SUFFIX}" &
        XPIDS="$XPIDS $!"
    fi
}

for PROJECT_CONFIG in $ALL_PROJECT_CONFIGS; do
    run_batch_for_project $PROJECT_CONFIG $DESC_SUFFIX
done

set -x
join

# vim:et
