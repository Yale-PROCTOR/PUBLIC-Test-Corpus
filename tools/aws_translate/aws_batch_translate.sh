#!/bin/bash -ue

# © 2026 Massachusetts Institute of Technology
# MIT License

#
# Run translators on test cases

set -o pipefail

################################################################################ Functions

log_it() {
    echo "$@" | tee -a $LOG_FILE
}

submit_jobs() {
    # e.g.  Public-Tests/B01_organic/bin2hex_lib.tar.gz Public-Tests/B01_organic/bitwriter_add_lib.tar.gz
    local PROJECT="$1"
    local TEST_KEYS="$2"
    local JOB_IDS=
    for TEST_KEY in $TEST_KEYS; do
        # convert / etc into _ so it can be embedded into job name
        TEST_KEY_SAFE=`echo "$TEST_KEY" | sed -e 's#[^-_a-zA-Z0-9]#_#g'`

        # e.g., s3://c2rust-output-bucket/output/Public-Tests/B01_organic/bin2hex_lib.tar.gz
        local OUTPUT_ARCHIVE="s3://$OUTPUT_S3_ROOT_DIR/$TEST_KEY"

        local TAGS="$(cat <<EOF
{
    "output_archive": "$OUTPUT_ARCHIVE",
    "test_key": "$TEST_KEY",
    "project": "$PROJECT"
}
EOF
)"
        if [ -n "$DRY_RUN" ]; then
            echo aws batch submit-job \
                --job-name $PROJECT-translate-$TS-$TEST_KEY_SAFE \
                --job-queue test-$PROJECT-job-queue \
                --job-definition test-$PROJECT-fargate-job \
                --container-overrides "$(project_container_overrides $TEST_KEY)" \
                --tags "$TAGS" \
                --profile ${AWS_PROFILE:-g53-poweruser} 1>&2
        else
            SUBMIT_RESULT=$(aws batch submit-job \
                --job-name $PROJECT-translate-$TS-$TEST_KEY_SAFE \
                --job-queue test-$PROJECT-job-queue \
                --job-definition test-$PROJECT-fargate-job \
                --container-overrides "$(project_container_overrides $TEST_KEY)" \
                --tags "$TAGS" \
                --profile ${AWS_PROFILE:-g53-poweruser})
            JOB_ID=$(jq -r .jobId <(echo $SUBMIT_RESULT))
            JOB_IDS="$JOB_IDS $JOB_ID"
        fi
        echo -n "+" 1>&2
    done
    echo $JOB_IDS
}

wait_for_jobs() {
    local JOB_IDS="$1"
    # NB "aws batch describe-jobs" with 101+ jobs will results in
    #   An error occurred (ClientException) when calling the DescribeJobs operation: Error executing request, Exception : Maximum number of jobs supported is  100#
    # so we need to use xargs to repeat the "aws batch describe-jobs" multiple times with chunks
    #
    # NB:
    #       echo "$JOB_IDS" | xargs -n 100 aws batch describe-jobs --jobs
    # =>
    #       { "jobs": [ { "status": "SUCCEEDED" }, ...  ] }   # for jobs 1 - 100
    #       { "jobs": [ { "status": "SUCCEEDED" }, ...  ] }   # for jobs 101 - 100
    #       ...
    #       { "jobs": [ { "status": "SUCCEEDED" }, ...  ] }   # for jobs ...
    # NB:
    #       ...  | jq '[.jobs[].status] | all(. == "SUCCEEDED" or . == "FAILED")'
    # => either
    #       true        # for jobs 1 - 100 all done
    #       false       # for jobs 101 - 200 with some still pending
    #       ...  #       true
    # => or
    #       true        # for jobs 1 - 100 all done
    #       true        # for jobs 101 - 200 all done
    #       ...
    #       true
    while echo "$JOB_IDS" | xargs -n 100 aws batch describe-jobs --jobs | jq '[.jobs[].status] | all(. == "SUCCEEDED" or . == "FAILED")' | grep -q false; do
        sleep 5
        echo -n "." 1>&2
    done
}

summarize_jobs() {
    local JOB_IDS="$1"
    local ALL_JOBS_FILE=$2  # all_jobs.json to write to
    local ALL_JOB_DEFINITIONS_FILE=$3   # where to write job deifinition json to
    local S3_TMP_DIR=$4    # where to store temporary s3 downloads to

    # Find all job.json files, keep only the ones that match job ID
    # -s      : to concatenate across all xargs chunk's
    # flatten : to flatten out nested arrays into 1 long array
    mkdir -p $S3_TMP_DIR
    echo "$JOB_IDS" | xargs -n 100 aws batch describe-jobs --jobs  | jq -s | jq '[.[].jobs] | flatten' > $ALL_JOBS_FILE

    # Show final job counts
    jq 'group_by(.status) | map({job_count: length, status: .[0].status})' $ALL_JOBS_FILE

    # Download logs
    local LOG_IDS=$(jq -r '.[].container.logStreamName' $ALL_JOBS_FILE | tr '\n' ' ')
    log_it "LOG_IDS=$LOG_IDS"

    # Download translator results (assuming bucket only contains new results)
    aws s3 cp --recursive --quiet s3://$OUTPUT_S3_ROOT_DIR $S3_TMP_DIR

    # Generate summary files. e.g.,
    # $RESULTS_DIR/status.txt    # how many jobs SUCCEEDED or FAILED
    # $RESULTS_DIR/summary.json  # how log all the jobs took to run

    # Find all job_definition.json files
    local JOB_DEFINITION_IDS=$(jq -r 'map(.jobDefinition) | unique | .[] | "\(.)"' $ALL_JOBS_FILE)
    aws batch describe-job-definitions --job-definitions $JOB_DEFINITION_IDS | jq -r '.jobDefinitions' > $ALL_JOB_DEFINITIONS_FILE

    jq -r '.[].status' $ALL_JOBS_FILE | sort | uniq -c > $RESULTS_DIR/status.txt
    # NB: (.startedAt | values) instead of (.startedAt) because a job can be
    # terminated/cancelled before it even starts, in which case it has a stoppedAt but no startedAt
    jq -r '
    {
        job_count: . | length,
        total_elapse_sec: ((. | map(.stoppedAt - (.startedAt | values)) | add | values / 1000) // null),
        min_startedAt_sec: ((.| map((.startedAt | values)) | min | values / 1000) // null),
        max_stoppedAt_sec: (.| map(.stoppedAt) | max / 1000)
    }
    | . +
    {
        avg_elapse_sec: (((.total_elapse_sec | values) / .job_count) // null),
        wall_elapsed_sec: ((.max_stoppedAt_sec - (.min_startedAt_sec | values)) // null),
        min_startedAt: ((.min_startedAt_sec | values | todate) // null),
        max_stoppedAt: .max_stoppedAt_sec | todate
    }' $ALL_JOBS_FILE > $RESULTS_DIR/summary.json
}

download_job_results() {
    local JOB_IDS="$1"
    local ALL_JOBS_FILE=$2  # all_jobs.json file to read from
    local ALL_JOB_DEFINITIONS_FILE=$3   # where to get job deifinition json from
    local S3_TMP_DIR=$4    # where to get temporary s3 downloads from
    local MISSING_S3=
    local UNEXPECTED_S3=
    local MISSING_LOG_JOB_IDS=

    if [ ! -f "$ALL_JOBS_FILE" ]; then
        # Make sure summarize_jobs() is correct
        echo "Cannot find file $ALL_JOBS_FILE"
        return 1
    fi

    for JOB_ID in $JOB_IDS; do
        local IS_FAILED=

        if [ "$(jq -r 'map(select(.jobId == "'"$JOB_ID"'")) | length' $ALL_JOBS_FILE)" = "0" ]; then
            echo "Cannot find job ID $JOB_ID. Was CDK stack deleted/rebuilt?"
            return 1
        fi

        local TAGS=$(jq 'map(select(.jobId == "'"$JOB_ID"'")) | .[].tags' $ALL_JOBS_FILE)
        if [ -z "$TAGS" ]; then
            echo "$JOB_ID is missing tags. Was job not submitted using $0?"
            return 1
        fi
        local TEST_KEY=$(echo "$TAGS" | jq -r '.test_key')

        # e.g., results/c2rust/Public-Tests/B01_organic/bin2hex_lib
        local JOB_RESULTS_DIR=$RESULTS_DIR/${TEST_KEY%%.tar.gz}
        local METADATA_DIR=$JOB_RESULTS_DIR/metadata

        mkdir -p $JOB_RESULTS_DIR $METADATA_DIR

        #### Download all metadata

        # Download all job metadata
        jq -r '.[] | select(.jobId == "'$JOB_ID'")' $ALL_JOBS_FILE > $METADATA_DIR/job.json

        # Relocate job definition (i.e., what the CDK set up)
        # e.g., arn:aws-us-gov:batch:us-gov-east-1:999999999999:job-definition/test-c2rust-fargate-job:15
        local JOB_DEFINITION_ID=$(jq -r '.jobDefinition' $METADATA_DIR/job.json)
        jq -r '.[] | select(.jobDefinitionArn == "'"$JOB_DEFINITION_ID"'")' $ALL_JOB_DEFINITIONS_FILE > $METADATA_DIR/job_definition.json

        # Get container image from job definition
        # e.g., 999999999999.dkr.ecr.us-gov-east-1.amazonaws.com/cdk-hnb659fds-container-assets-999999999999-us-gov-east-1:1e32f332560ebce69ecb65fbe9b48123d25616d6401d4c518dd84dfbbbd68dcd
        jq -r '.containerProperties.image' $METADATA_DIR/job_definition.json > $METADATA_DIR/container_image.txt

        #### Download the actual results (stuff from translator + logs)

        # Relocate translator results (already downloaded by summarize_jobs())
        local OUTPUT_ARCHIVE=$(echo "$TAGS" | jq -r '.output_archive')
        SRC_TGZ="$S3_TMP_DIR/${OUTPUT_ARCHIVE##s3://$OUTPUT_S3_ROOT_DIR}"

        JOB_STATUS=$(jq -r '.status' $METADATA_DIR/job.json)

        if [ -e "$SRC_TGZ" ]; then
            if [ "$JOB_STATUS" == "SUCCEEDED" ]; then
                mv $SRC_TGZ $JOB_RESULTS_DIR/$(basename "$OUTPUT_ARCHIVE") > /dev/null
            else
                UNEXPECTED_S3="$UNEXPECTED_S3 JOB_ID($JOB_ID)->$OUTPUT_ARCHIVE->$SRC_TGZ"
            fi
        else
            if [ "$JOB_STATUS" == "SUCCEEDED" ]; then
                # Don't fail immediately. Prevent incomplete/failed jobs from messing up download of successful jobs.
                MISSING_S3="$MISSING_S3 JOB_STATUS($JOB_ID)->$OUTPUT_ARCHIVE->$SRC_TGZ"
                IS_FAILED=1
            fi
            # else Failed jobs don't create s3 output. This is normal
        fi

        # Download logs
        if ! get_logs_by_job_id "$JOB_ID" $ALL_JOBS_FILE > $JOB_RESULTS_DIR/job.log; then
            MISSING_LOG_JOB_IDS="$MISSING_LOG_JOB_IDS $JOB_ID"
            IS_FAILED=1
        fi

        if [ -z "$IS_FAILED" ]; then
            echo -n "~" 1>&2
        else
            echo -n "!" 1>&2
        fi
    done
    echo ""
    echo "Results downloads to $RESULTS_DIR/"
    if [ -n "$MISSING_S3" -o -n "$MISSING_LOG_JOB_IDS" -o -n "$UNEXPECTED_S3" ]; then
        if [ -n "$MISSING_S3" ]; then
            # Some jobs are missing S3 output
            echo "Warning: Following S3 results are missing: $(echo $MISSING_S3 | tr ' ' '\n')"
        fi
        if [ -n "$UNEXPECTED_S3" ]; then
            # Some jobs are have unxpected S3 output
            echo "Warning: Following S3 results unexpectedly exist. They may be holdover from previous jobs: $(echo $UNEXPECTED_S3 | tr ' ' '\n')"
        fi
        if [ -n "$MISSING_LOG_JOB_IDS" ]; then
            # Some jobs are missing logs
            echo "Warning: Following jobs are missing logs:$(echo $MISSING_LOG_JOB_IDS | tr ' ' '\n')"
        fi

        # NB: Intentionally ignore missing logs/S3. Allow caller collect_results.sh to crate aws_results.tbz + run rust runner etc.
        # Uncomment next line if want to do otherwise [for debugging]:
        # return 0
    fi
}

get_logs() {
    local LOG_ID=$1
    local CONTENT=
    local CUR_PAGE=
    local NEXT_PAGE=
    while true; do
        CUR_PAGE=$NEXT_PAGE
        CONTENT=`aws logs get-log-events --log-group-name /aws/batch/job --log-stream-name $LOG_ID ${CUR_PAGE:+--next-token $CUR_PAGE}`
        # First page [newest logs] can be empty => go backwards to get older logs
        NEXT_PAGE=`echo "$CONTENT" | jq -r '.nextBackwardToken'`
        echo "$CONTENT" | jq -r '.events[] | "\(.timestamp/1000|todateiso8601) \(.message)"'
        if [ "$NEXT_PAGE" = "$CUR_PAGE" ]; then
            # Last page reach when .nextBackwardToken loops back to itself => stop
            break
        fi
    done
}

get_logs_by_job_id() {
    local JOB_ID=$1
    local ALL_JOBS_FILE=$2
    local LOG_ID=$(jq -r 'map(select(.jobId == "'"$JOB_ID"'")) | .[].container.logStreamName' $ALL_JOBS_FILE)
    get_logs "$LOG_ID"
}

################################################################################ Main program

# Parse CLI options

OPTARG=
OPTIND=
XOPT=
VERBOSE=

DELETE_OUTPUT=
DRY_RUN=
MATCH_RE=
RESULTS_ROOT_DIR=results

TS=$(date +'%Y%m%d-%H%M%S')

## Keep only 4 representative test cases for spot checking. e.g.,
## input/Public-Tests/B01_organic/bin2hex_lib.tar.gz
## input/Public-Tests/B01_organic/gaussian_kernel_lib.tar.gz
## input/Public-Tests/B01_synthetic/024_struct_and_static.tar.gz
## input/Public-Tests/B01_synthetic/024_struct_and_static_lib.tar.gz
# DEFAULT_TEST_MODE_MATCH_RE='bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz'

## Spot check on performers on 2025-12-04
## Public-Tests/B01_organic/gaussian_kernel_lib.tar.gz
## Public-Tests/B01_synthetic/024_struct_and_static.tar.gz
## Public-Tests/B01_synthetic/024_struct_and_static_lib.tar.gz
## Public-Tests/P01_sphincs_plus/007_sphincs_PQCgenKAT_sign_blake_128s_simple.tar.gz
DEFAULT_TEST_MODE_MATCH_RE='Public-Tests/B01_organic/gaussian_kernel_lib.tar.gz|Public-Tests/B01_synthetic/024_struct_and_static.tar.gz|Public-Tests/B01_synthetic/024_struct_and_static_lib.tar.gz|Public-Tests/P01_sphincs_plus/007_sphincs_PQCgenKAT_sign_blake_128s_simple.tar.gz'

while getopts hdo:m:ntT:v XOPT; do
    case $XOPT in
        h) cat <<EOF
$0 [-v] [-d] [-m <MATCH_RE>] [-n] [-o <OUTDIR>] [-t] [-T <TS>] (c2rust | llm | self-host-llm | aarno | galois | harvest | intel | uwisc | yale)
$0 [-v] [-d]                 [-n] [-o <OUTDIR>]      [-T <TS>] (c2rust | llm | self-host-llm | aarno | galois | harvest | intel | uwisc | yale) JOB_ID1 ...

-d : Delete output from prior runs (i.e., S3 bucket and local output folder <OUTDIR>)
-m : Only run test keys that match <MATCH_RE> (e.g., "bin2hex_lib.tar.gz|gaussian_kernel_lib.tar.gz|024_struct_and_static.tar.gz|024_struct_and_static_lib.tar.gz")
-n : Do dry-run. Do not actually submit jobs.
-o : Set local output folder to <OUTDIR> (default: $RESULTS_ROOT_DIR)
-t : Run in test-mode (alias for -m "$DEFAULT_TEST_MODE_MATCH_RE")
-T : Set timestamp to <TS> (default: current time. e.g., $TS)
-v : Show verbose/debug output

Specify JOB_ID1 etc if the job was already submitted and you just want to download job results.
Otherwise, new jobs will be submitted.
EOF
            exit 0
            ;;
        d)  DELETE_OUTPUT=1 ;;
        m)  MATCH_RE=$OPTARG ;;
        n)  DRY_RUN=1 ;;
        o)  RESULTS_ROOT_DIR=$OPTARG ;;
        t)  MATCH_RE=$DEFAULT_TEST_MODE_MATCH_RE ;;
        T)  TS=$OPTARG ;;
        v)  VERBOSE=1
            set -x
            ;;
        *)
            echo "Bad option: $XOPT"
            exit 1
            ;;
    esac
done
shift `expr $OPTIND - 1`

PROJECT=${1:-c2rust}
if [ $# -ne 0 ]; then
    shift
fi
FORCE_JOB_IDS=${@:-}

if [ -n "$FORCE_JOB_IDS" -a -n "$MATCH_RE" ]; then
    # Filter test keys only works when submitting new jobs.
    # Specifying explicit jobs IDs will resume old jobs.
    echo "Cannot filter test keys (-m) when resuming old jobs with explicit job IDs"
    exit 1
fi

case $PROJECT in
    c2rust)
        OUTPUT_S3_BUCKET="$PROJECT-output-bucket"
        OUTPUT_S3_ROOT_DIR="$OUTPUT_S3_BUCKET/output"
        function project_container_overrides() {
            local TEST_KEY="$1"
            cat <<EOF
{
  "environment": [
    {
      "name": "S3_KEY",
      "value": "$TEST_KEY"
    }
  ]
}
EOF
        }
        ;;
    self-host-llm|aarno|galois|harvest|intel|uwisc|yale)
        OUTPUT_S3_BUCKET="tractor-$PROJECT-output-bucket"
        OUTPUT_S3_ROOT_DIR="$OUTPUT_S3_BUCKET/output"
        function project_container_overrides() {
            local TEST_KEY="$1"
            cat <<EOF
{
  "environment": [
    {
      "name": "S3_KEY",
      "value": "$TEST_KEY"
    },
    {
      "name": "S3_INPUT_BUCKET",
      "value": "tractor-input-bucket"
    },
    {
      "name": "S3_OUTPUT_BUCKET",
      "value": "$OUTPUT_S3_BUCKET"
    }
  ]
}
EOF
        }
        ;;
    llm)
        OUTPUT_S3_BUCKET="tractor-$PROJECT-output-bucket"
        OUTPUT_S3_ROOT_DIR="$OUTPUT_S3_BUCKET/output"
        function project_container_overrides() {
            local TEST_KEY="$1"
            cat <<EOF
{
  "environment": [
    {
      "name": "S3_KEY",
      "value": "$TEST_KEY"
    },
    {
      "name": "OPENAI_BASE_URL",
      "value": "https://api.openai.com/v1"
    },
    {
      "name": "S3_INPUT_BUCKET",
      "value": "tractor-input-bucket"
    },
    {
      "name": "S3_OUTPUT_BUCKET",
      "value": "$OUTPUT_S3_BUCKET"
    }
  ]
}
EOF
        }
        ;;
    *)
        echo "Unsupported project. $PROJECT should be one of: c2rust, llm, etc"
        exit 1
        ;;
esac

# Where to save/download job results to
RESULTS_DIR="$RESULTS_ROOT_DIR/$PROJECT"

# Where to store temporary files to
RESULTS_TMP_DIR="$RESULTS_DIR/tmp"

LOG_FILE="$RESULTS_DIR/$(basename -s .sh $0).log"

# Delete old results [if necessary]
if [ -n "$DELETE_OUTPUT" ]; then
    echo Deleting s3://$OUTPUT_S3_ROOT_DIR
    aws s3 rm --recursive s3://$OUTPUT_S3_ROOT_DIR

    echo "Deleting local dir: $RESULTS_ROOT_DIR ..."
    rm -rf $RESULTS_ROOT_DIR
fi

mkdir -p $RESULTS_DIR

if [ -n "$FORCE_JOB_IDS" ]; then
    JOB_IDS=$FORCE_JOB_IDS

    # Make sure all jobs belong to same project
    if aws batch describe-jobs --jobs $JOB_IDS | jq -r "[.jobs[].tags.project] | all(. == \"$PROJECT\")" | grep -q false; then
      echo "Not all projects are $PROJECT: $(aws batch describe-jobs --jobs $JOB_IDS | jq -c -r "[.jobs[].tags.project]")"
    fi
else
    # Find test cases [for translator]
    # One entry per test case (e.g., Public-Tests/B01_organic/bin2hex_lib.tar.gz ...)
    TEST_KEYS=$(aws s3 ls --recursive s3://tractor-input-bucket/input/ | awk '{print $NF}' | sed -e 's#^input/##' | tr '\n' ' ')

    if [ -n "$MATCH_RE" ]; then
        TEST_KEYS=$(echo "$TEST_KEYS" | tr ' ' '\n' | egrep "$MATCH_RE")
    fi

    log_it "PROJECT=$PROJECT"
    log_it "OUTPUT_S3_ROOT_DIR=$OUTPUT_S3_ROOT_DIR"
    log_it "MATCH_RE=$MATCH_RE"
    log_it "TEST_KEYS=$TEST_KEYS"

    # Submit jobs
    JOB_IDS=$(submit_jobs "$PROJECT" "$TEST_KEYS")
fi

log_it "TS=$TS"
log_it "JOB_IDS=$JOB_IDS"

# Wait for all jobs to finish
set +x
cat <<EOF
Monitor jobs at https://us-gov-east-1.console.amazonaws-us-gov.com/batch/home?region=us-gov-east-1#jobs/advanced-search
or: echo \$JOB_IDS | xargs -n 100 aws batch describe-jobs --jobs

To view output s3 bucket, run: aws s3 ls --recursive $OUTPUT_S3_ROOT_DIR | cat -n | sort -n -r -k 1
To view job logs, run: aws logs get-log-events --log-group-name /aws/batch/job --log-stream-name \$(aws batch describe-jobs --jobs \$JOB_ID | jq -r '.jobs[].container.logStreamName') | jq -r '.events[] | "\(.timestamp/1000|todateiso8601) \(.message)"'
EOF
wait_for_jobs "$JOB_IDS"
[ -z "$VERBOSE" ] || set -x

# Output JSON files summarizing jobs
summarize_jobs "$JOB_IDS" "$RESULTS_TMP_DIR/all_jobs.json" "$RESULTS_TMP_DIR/all_job_definitions.json" "$RESULTS_TMP_DIR/s3"

# Download results
download_job_results "$JOB_IDS" "$RESULTS_TMP_DIR/all_jobs.json" "$RESULTS_TMP_DIR/all_job_definitions.json" "$RESULTS_TMP_DIR/s3"

# Possible that we downloaded too much from S3. Delete any extra files.
# This can happen if prior runs outputted more test cases *and* current run did not use "-d".
rm -rf $RESULTS_TMP_DIR/s3

# vim:et
