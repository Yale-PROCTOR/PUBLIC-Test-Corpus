#!/bin/bash -ue

# © 2026 Massachusetts Institute of Technology
# MIT License

# set -x

# * for each test result
#   * number of test cases (# of AWS jobs)
#       * all
#           * for B01
#           * for B02
#           * for Other
#       * look at `all_jobs.json` => count those with `test_key` matching B01/B02/etc
#   * translated test cases (input for rust runner)
#       * all
#           * for B01
#           * for B02
#           * for Other
#       * look at `all_jobs.json` => count those with `test_key` matching B01/B02/etc + status = success + .tar.gz exists
#   * successful test vectors
#       * for B01
#       * for B02
#       * for Other
#   * failed/skipped/etc test values
#       * for B01
#       * for B02
#       * for Other

RESULTS_DIR="results.49.rust_runner"
ALL_PROJ_DIRS="\
    $RESULTS_DIR/aarno.304_spot_check/aarno \
    $RESULTS_DIR/yale.354_spot_check/yale \
    $RESULTS_DIR/uwisc.344_spot_check/uwisc \
    $RESULTS_DIR/harvest.324_spot_check/harvest \
    $RESULTS_DIR/intel.334_spot_check/intel \
    $RESULTS_DIR/galois.314_spot_check/galois \
    $RESULTS_DIR/self-host-llm.202_b01_b02/self-host-llm \
    $RESULTS_DIR/llm.212_b01_b02/llm \
    $RESULTS_DIR/c2rust.222_b01_b02/c2rust \
    "

for PROJ_DIR in $ALL_PROJ_DIRS; do
    PROJ=`basename $PROJ_DIR`
    pushd $PROJ_DIR > /dev/null
    echo "======================================== $PROJ"
    # jq -r '"\(length) total test cases were given to translator"' tmp/all_jobs.json
    # jq -r '"... of which only \(group_by(.status)[1] | length) were translated (i.e., created ok Cargo.toml project)"' tmp/all_jobs.json
    echo "---------- AWS results"

    jq -r '"\(length) total test cases were given to translator"' tmp/all_jobs.json
    jq -r '
        map(select(.tags.test_key | test("B01"))) // []
        | "... of which \(length // 0) were B01"' tmp/all_jobs.json
    jq -r '
        map(select(.tags.test_key | test("B02"))) // []
        | "... of which \(length // 0) were B02"' tmp/all_jobs.json
    jq -r '
        map(select(.tags.test_key | test("B01|B02") | not)) // []
        | "... of which \(length // 0) were other"' tmp/all_jobs.json

    SUCCEEDED_COUNT=$(jq -r '
        (group_by(.status)
            | map({status: .[0].status, count: length}
            | select(.status == "SUCCEEDED")
            | .count)[]) // 0' tmp/all_jobs.json)
    echo "$SUCCEEDED_COUNT were translated"
    jq -r '
        (map(select(.tags.test_key | test("B01")))
            | group_by(.status)
            | map({status: .[0].status, count: length}
            | select(.status == "SUCCEEDED")
            | .count)[]) // 0
        | "... of which \(.) were B01"' tmp/all_jobs.json
    jq -r '
        (map(select(.tags.test_key | test("B02")))
            | group_by(.status)
            | map({status: .[0].status, count: length}
            | select(.status == "SUCCEEDED")
            | .count)[]) // 0
        | "... of which \(.) were B02"' tmp/all_jobs.json
    jq -r '
        (map(select(.tags.test_key | test("B01|B02") | not))
            | group_by(.status)
            | map({status: .[0].status, count: length}
            | select(.status == "SUCCEEDED")
            | .count)[]) // 0
        | "... of which \(.) were other"' tmp/all_jobs.json

    echo "----- Breakdown"
    echo "For B01"
    jq -r '
        (map(select(.tags.test_key | test("B01")))
            | group_by(.status)
            | map({status: .[0].status, count: length, statusReason: [.[].statusReason] | unique})[]) // {}
        | "\(.count // 0) jobs \(.status // "SUCCEEDED") with results \(.statusReason // "n/a")"' tmp/all_jobs.json
    echo ""
    echo "For B02"
    jq -r '
        (map(select(.tags.test_key | test("B02")))
            | group_by(.status)[]
            | {status: .[0].status, count: length, statusReason: [.[].statusReason] | unique}) // {}
        | "\(.count // 0) jobs \(.status // "SUCCEEDED") with results \(.statusReason // "n/a")"' tmp/all_jobs.json
    echo ""
    echo "For other"
    jq -r '
        (map(select(.tags.test_key | test("B01|B02") | not))
            | group_by(.status)[]
            | {status: .[0].status, count: length, statusReason: [.[].statusReason] | unique}) // {}
        | "\(.count // 0) jobs \(.status // "SUCCEEDED") with results \(.statusReason // "n/a")"' tmp/all_jobs.json
    TAR_GZ_COUNT=$(find . -name \*.tar.gz | wc -l)
    cat <<EOF

$TAR_GZ_COUNT .tar.gz translated output were found
EOF
    if [ $TAR_GZ_COUNT != $SUCCEEDED_COUNT ]; then
        echo "Warning: .tar.gz count is not $SUCCEEDED_COUNT (i.e., the number of S3 results does not match AWS job status)!!!!!!"
    fi

    echo "---------- rust runner results"

    JUNIT_XML="junit.xml"

    # .testsuites.testsuite | length
    # .testsuites.testsuite
    # .testsuites.testsuite | map(select(."@errors" == 0))
    # .testsuites.testsuite | map(select(."@errors" > 0))
    # .testsuites.testsuite | map(select(."@errors" > 0) | select(."@name" | test("B01")))
    # .testsuites.testsuite | map(select((."@errors" == 0) and (."@name" | test("B01"))))
    # .testsuites.testsuite | map(select(."@errors" > 0) | select(."@name" | test("B01") | not))
    # .testsuites.testsuite | map(select((."@errors" == 0) and (."@name" | test("B01")))) | .[].testcase[] | select(."@name" != "build")
    # [.testsuites.testsuite | map(select((."@errors" == 0) and (."@name" | test("B01")))) | .[].testcase] | flatten | map(select(."@name" != "build"))
    # [.testsuites.testsuite | map(select((."@errors" == 0) and (."@name" | test("B01")))) | .[].testcase] | flatten | map(select(."@name" != "build")) | length
    #
    # .testsuites.testsuite | map(select((."@errors" == 0) and (."@failures" == 0) and (."@skipped" == 0) and (."@name" | test("B01|B02")))) | length
    # .testsuites.testsuite | map(select(."@skipped" > 0)) | length
    # .testsuites.testsuite | map(select(."@errors" > 0)) | length
    # .testsuites.testsuite | map(select(."@failures" > 0)) | length

    JUNIT_JSON="$(basename -s .xml $JUNIT_XML).json"
    xml2js $JUNIT_XML > $JUNIT_JSON

    jq -r '
        .testsuites.testsuite
        | "Of \(length) discovered tests"' $JUNIT_JSON
    jq -r '"... \(.testsuites["@errors"]) tests errored"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" > 0) and (."@name" | test("B01"))))
        | "    ... of which \(length) were B01"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" > 0) and (."@name" | test("B02"))))
        | "    ... of which \(length) were B02"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" > 0) and (."@name" | test("B01|B02") | not)))
        | "    ... of which \(length) were other"' $JUNIT_JSON

    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" == 0) and (."@failures" == 0)))
        | "... \(length) tests passed"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" == 0) and (."@failures" == 0) and (."@name" | test("B01"))))
        | "    ... of which \(length) were B01"' $JUNIT_JSON
    jq -r '
        [.testsuites.testsuite
            | map(select((."@errors" == 0) and (."@failures" == 0) and (."@name" | test("B01"))))
            | .[].testcase]
        | flatten
        | map(select(."@name" != "build"))
        | "        ... with \(length) test vectors"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" == 0) and (."@failures" == 0) and (."@name" | test("B02"))))
        | "    ... of which \(length) were B02"' $JUNIT_JSON
    jq -r '
        [.testsuites.testsuite
            | map(select((."@errors" == 0) and (."@failures" == 0) and (."@name" | test("B02"))))
            | .[].testcase]
        | flatten
        | map(select(."@name" != "build"))
        | "        ... with \(length) test vectors"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select((."@errors" == 0) and (."@failures" == 0) and (."@name" | test("B01|B02") | not)))
        | "    ... of which \(length) were other"' $JUNIT_JSON
    jq -r '
       [.testsuites.testsuite
            | map(select((."@errors" == 0) and (."@failures" == 0) and (."@name" | test("B01|B02") | not)))
            | .[].testcase]
        | flatten
        | map(select(."@name" != "build"))
        | "        ... with \(length) test vectors"' $JUNIT_JSON

    jq -r '
        .testsuites.testsuite
        | map(select(."@failures" > 0))
        | "... \(length) tests were failures"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select(."@failures" > 0 and (."@name" | test("B01"))))
        | "    ... of which \(length) were B01"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select(."@failures" > 0 and (."@name" | test("B02"))))
        | "    ... of which \(length) were B02"' $JUNIT_JSON
    jq -r '
        .testsuites.testsuite
        | map(select(."@failures" > 0 and (."@name" | test("B01|B02") | not)))
        | "    ... of which \(length) were other"' $JUNIT_JSON

    popd > /dev/null
done

# vim:et:ts=4:sw=4
