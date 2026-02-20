// © 2026 Massachusetts Institute of Technology
// MIT License

/**
 * GitHub action to handle JUnit test failures (i.e., fail the CI)
 *
 * This is a poor man's version of [action-junit-report](https://github.com/marketplace/actions/junit-report-actionrun)
 */

const core = require('@actions/core');
// const github = require('@actions/github');
const fs = require('fs');
const parser = require('xml-js');

/**
 * Pluck out "failure" nodes and return an error of error strings (1 per failure)
 */

function parseResults(rootNd /* : object */, rootKey /* : string? */ = undefined) /* : {failures: string[], errors: string[], skipped: string[], passCount: number} */ {
	let failures = [];
	let errors = [];
	let skipped = [];
	let passCount = 0;
	for (const testsuite of (rootNd?.testsuites?.testsuite || [])) {
		for (const testcase of (testsuite?.testcase || [])) {
			const failure = testcase?.failure;
			const error = testcase?.error;
			const singleSkipped = testcase?.skipped;
			if (failure) {
				failures.push(`${testsuite._attributes.name} :: ${testcase._attributes.name} :: ${failure._attributes.message}`);
			} else if (error) {
				errors.push(`${testsuite._attributes.name} :: ${testcase._attributes.name} :: ${error._attributes.message}`);
			} else if (singleSkipped) {
				skipped.push(`${testsuite._attributes.name} :: ${testcase._attributes.name} :: ${singleSkipped._attributes.message}`);
			} else {
				passCount += 1;
			}
		}
	}
	return { failures, errors, skipped, passCount };
}

/**
 * From action.yml
 *
 * inputs:
 *   report_paths:
 *     description: 'Path to XML file'
 *     required: false
 *     default: 'junit.xml'
 * outputs:
 *   failed:
 *     description: 'The count of all failed tests (compiled but run failed)'
 *   errored:
 *     description: 'The count of all tests that errored (e.g., could not compile)'
 *   skipped:
 *     description: 'The count of all skipped tests'
 *   passed:
 *     description: 'The count of all passing tests'
 */
async function main() {
	try {
		core.startGroup("Reporting JUnit results");
		const reportPath = core.getInput('report_path')
		const reportXml = fs.readFileSync(reportPath, 'utf8');
		const reportJson = JSON.parse(parser.xml2json(reportXml, { compact: true }))
		const { failures, errors, skipped, passCount } = parseResults(reportJson);
		for (const failure of failures) {
			core.error(`Test failed: ${failure}`);
		}
		for (const error of errors) {
			core.error(`Test errored: ${error}`);
		}
		for (const singleSkipped of skipped) {
			core.warning(`Skipped test: ${singleSkipped}`);
		}
		const failedCount = failures.length;
		const errorCount = errors.length;
		const skippedCount = skipped.length;
		core.setOutput('failed', failedCount)
		core.setOutput('errored', errorCount)
		core.setOutput('skipped', skippedCount);
		core.setOutput('passed', passCount);
		if (failedCount) {
			core.setFailed(`${failedCount} tests failed`);
		}
		if (errorCount) {
			core.setFailed(`${errorCount} tests errored`);
		}
		if (skippedCount) {
			core.warning(`${skippedCount} tests were skipped`);
		}
		core.info(`${passCount} tests passed`);
		core.endGroup();
	} catch (err) {
		core.setFailed(err.message)
	}
}

main();
