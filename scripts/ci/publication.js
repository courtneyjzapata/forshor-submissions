'use strict';

// Runs only from trusted main. Submitted Lean/source archives are never executed.
const fs = require('node:fs');
const { execFileSync } = require('node:child_process');
const { createHash } = require('node:crypto');
const reporting = require('./table_generation_report.js');
const REPOSITORY = 'zapatacomputing/forshor-submissions';
const sha = value => /^[a-f0-9]{40}$/.test(value);

function verificationIdentity(head) {
  return JSON.parse(execFileSync('python3', ['scripts/ci/verification_identity.py', '--head', head], { encoding: 'utf8' }));
}

function evaluationKey(identity) {
  const hash = createHash('sha256').update(`forshor-evaluation/v1\n${identity.key}\n`);
  for (const path of ['evaluation/estimate.py', 'evaluation/requirements.lock']) hash.update(fs.readFileSync(path));
  return hash.digest('hex');
}

async function readJson(github, context, path) {
  try {
    const { data } = await github.rest.repos.getContent({ ...context.repo, path, ref: 'submission-results' });
    if (data.encoding !== 'base64') throw new Error('Expected a versioned archive file');
    return JSON.parse(Buffer.from(data.content, 'base64').toString());
  } catch (error) {
    if (error.status === 404) return null;
    throw error;
  }
}

async function acceptedReceipt(github, context, identity) {
  const receipt = await readJson(github, context, `results/evaluations/${identity.key}.json`);
  if (!receipt) return null;
  assertReceipt(receipt, identity);
  const index = await readJson(github, context, 'leaderboard/results.json');
  const policy = index?.policies.find(p => p.policy_id === identity.headSha);
  return policy?.source.repository === REPOSITORY && policy.source.run_id === receipt.runId
    && Number(policy.source.pr_number) === receipt.pullRequest ? receipt : null;
}

async function inspect({ github, context, core }) {
  const event = context.payload.workflow_run;
  if (!event || event.event !== 'pull_request' || event.path !== '.github/workflows/table-generation-submission.yml'
      || !Number.isSafeInteger(event.id) || !Number.isSafeInteger(event.run_attempt) || !sha(event.head_sha))
    throw new Error('Unexpected source verification workflow');
  if (event.conclusion !== 'success') {
    await core.summary.addHeading('Submission not accepted').addRaw(
      `Verification concluded **${event.conclusion}**. Published results are unchanged.\n\n`
    ).addLink('Verification details', event.html_url).write();
    core.setOutput('process', 'false');
    return;
  }
  // Bind recovery to the original attempt, even after the source is rerun.
  const { data: run } = await github.rest.actions.getWorkflowRunAttempt({
    ...context.repo, run_id: event.id, attempt_number: event.run_attempt,
  });
  if (run.event !== event.event || run.path !== event.path || run.head_sha !== event.head_sha || run.conclusion !== 'success')
    throw new Error('Source workflow identity changed');
  let pr;
  try {
    pr = await reporting.resolveTrustedPullRequest(github, context, run);
  } catch (error) {
    if (error.code !== 'SUPERSEDED') throw error;
    await core.summary.addHeading('Superseded submission').addRaw('The PR now has a newer commit. This old result will not be archived or published.').write();
    core.setOutput('process', 'false');
    return;
  }
  const receipt = await acceptedReceipt(github, context, verificationIdentity(pr.headSha));
  let artifact = `table-generation-submission-${run.id}-${event.run_attempt}`;
  if (receipt) {
    // Modern workflows skip download entirely once the trusted archive owns
    // verification. For an older, frozen workflow YAML that still downloads,
    // choose a surviving artifact only as unused data. Its contents cannot
    // grant reuse or replace the trusted archived result.
    const { data } = await github.rest.actions.listWorkflowRunArtifacts({ ...context.repo, run_id: run.id, per_page: 100 });
    const available = data.artifacts.filter(a => !a.expired && a.name.startsWith(`table-generation-submission-${run.id}-`));
    artifact = available.find(a => a.name === artifact)?.name || available[0]?.name || artifact;
  }
  fs.writeFileSync('publication-source.json', JSON.stringify({ run, pr }));
  core.setOutput('process', 'true');
  core.setOutput('download', receipt ? 'false' : 'true');
  core.setOutput('artifact', artifact);
}

function assertReceipt(receipt, identity) {
  if (!receipt || Object.entries(identity).some(([key, value]) => receipt[key] !== value)
      || !/^[1-9][0-9]*$/.test(receipt.runId) || !Number.isSafeInteger(receipt.runAttempt)
      || receipt.runAttempt < 1 || !Number.isSafeInteger(receipt.pullRequest) || receipt.pullRequest < 1)
    throw new Error('Invalid trusted verification receipt');
}

async function archive({ github, context, core }) {
  const { run, pr } = JSON.parse(fs.readFileSync('publication-source.json', 'utf8'));
  const identity = verificationIdentity(pr.headSha);
  let receipt = await acceptedReceipt(github, context, identity);
  const reused = Boolean(receipt);
  if (!receipt) {
    if (fs.existsSync('artifacts/reused-verification.json')) throw new Error('No trusted verification to reuse');
    const marker = JSON.parse(fs.readFileSync('artifacts/verification-identity.json', 'utf8'));
    if (Object.entries(identity).some(([key, value]) => marker[key] !== value))
      throw new Error('Verification configuration changed; rerun verification against current main');
    const result = JSON.parse(fs.readFileSync('artifacts/table-generation-submission-result.json', 'utf8'));
    if (result.phase !== 'full' || result.status !== 'success'
        || result.metadata?.head_sha !== pr.headSha || String(result.metadata?.run_id) !== String(run.id)
        || result.metadata?.repository !== REPOSITORY || String(result.metadata?.pr_number) !== String(pr.number)
        || Number(result.metadata?.run_attempt) !== Number(process.env.SOURCE_RUN_ATTEMPT))
      throw new Error('Artifact is not a complete successful verification of this source attempt');
    receipt = { ...identity, runId: String(run.id), runAttempt: Number(process.env.SOURCE_RUN_ATTEMPT), pullRequest: pr.number };
    fs.writeFileSync('artifacts/verification-receipt.json', JSON.stringify(receipt));
    await reporting.persistBenchmarkResults({ github, context, core });
  }
  const { data: details } = await github.rest.pulls.get({ ...context.repo, pull_number: receipt.pullRequest });
  fs.writeFileSync('evaluation-metadata.json', JSON.stringify({
    repository: REPOSITORY, headSha: identity.headSha, runId: receipt.runId,
    githubLogin: details.user.login, pullRequestUrl: details.html_url,
    submittedAt: details.created_at, evaluationKey: evaluationKey(identity),
  }));
  await core.summary.addHeading(reused ? 'Reusing accepted verification' : 'Verified submission archived')
    .addLink('Verified source run', `https://github.com/${REPOSITORY}/actions/runs/${receipt.runId}/attempts/${receipt.runAttempt}`)
    .addRaw('\n\nThe publication step can be retried independently of Lean verification.\n').write();
}

module.exports = { inspect, archive, verificationIdentity, evaluationKey, assertReceipt };
