'use strict';

// Trusted-main code only. No uploaded artifact chooses a PR, commit, or check.
const fs = require('node:fs');
const NAME = 'Estimate resources with Qualtran and publish results';
const CHECK_NAMES = new Set([NAME, 'Qualtran estimation and publication']);
const STATE = 'publication-check.json';
const REPOSITORY = 'zapatacomputing/forshor-submissions';
const DASHBOARD = 'https://forshor-staging-769861884059.us-central1.run.app';
const digest = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);

function workflowUrl(context) {
  const attempt = Number(process.env.GITHUB_RUN_ATTEMPT || 1);
  if (!Number.isSafeInteger(context.runId) || !Number.isSafeInteger(attempt) || attempt < 1)
    throw new Error('Missing trusted publisher run identity');
  return `https://github.com/${REPOSITORY}/actions/runs/${context.runId}/attempts/${attempt}`;
}

async function begin({ github, context, run, pr }) {
  const sourceId = `forshor-publication:${run.id}:${run.run_attempt}`;
  const detailsUrl = workflowUrl(context);
  const externalId = `${sourceId}:${context.runId}:${Number(process.env.GITHUB_RUN_ATTEMPT || 1)}`;
  const checks = await github.paginate(github.rest.checks.listForRef, {
    ...context.repo, ref: pr.headSha, filter: 'all', per_page: 100,
  });
  // Reuse the same source-attempt check on publisher retries. Only the Actions
  // app's checks qualify; a contributor cannot nominate another check ID.
  const existing = checks.filter(c => CHECK_NAMES.has(c.name)
    && (c.external_id === sourceId || c.external_id?.startsWith(`${sourceId}:`))
    && c.head_sha === pr.headSha && c.app?.slug === 'github-actions').sort((a, b) => b.id - a.id)[0];
  const body = { ...context.repo, name: NAME, details_url: detailsUrl, external_id: externalId,
    status: 'in_progress', started_at: new Date().toISOString(),
    output: { title: 'Waiting for resource estimation and publication',
      summary: `[Publisher workflow](${detailsUrl}). Lean verification is being inspected. This check succeeds only after results are published.` } };
  const { data: check } = existing
    ? await github.rest.checks.update({ ...body, check_run_id: existing.id })
    : await github.rest.checks.create({ ...body, head_sha: pr.headSha });
  const state = { checkId: check.id, externalId, detailsUrl, pr, run: { id: run.id, attempt: run.run_attempt } };
  fs.writeFileSync(STATE, JSON.stringify(state));
  return state;
}

async function finishCheck(github, context, state, conclusion, title, summary) {
  await github.rest.checks.update({ ...context.repo, check_run_id: state.checkId,
    status: 'completed', conclusion, completed_at: new Date().toISOString(),
    output: { title, summary: `${summary}\n\n[Publisher workflow](${state.detailsUrl})` } });
}

function receipt(source, metadata, result) {
  const expectedPr = `https://github.com/${REPOSITORY}/pull/${source.pr.number}`;
  if (metadata.repository !== REPOSITORY || metadata.headSha !== source.pr.headSha
      || metadata.pullRequestUrl !== expectedPr || !/^[1-9][0-9]*$/.test(metadata.runId)
      || !digest(metadata.evaluationKey)) throw new Error('Publication metadata does not match the verified PR');
  if (metadata.kind === 'policy') {
    if (result.schema !== 'forshor.publication/v2' || result.kind !== 'policy'
        || result.policy?.headSha !== metadata.headSha || result.policy?.login !== metadata.githubLogin
        || result.policy?.pull !== source.pr.number || result.policy?.digest !== metadata.policyDigest
        || !digest(metadata.policyDigest) || !/^[a-f0-9]{16}$/.test(metadata.epoch))
      throw new Error('Policy publication receipt does not match the verified policy');
  }
  // Reused evaluations refer to the original trusted verifier run. The archive,
  // not a submitted receipt, supplies that identity (publication.archive).
  if (result.alreadyPublished === true && result.evaluationKey !== undefined) {
    if (result.evaluationKey !== metadata.evaluationKey) throw new Error('Published evaluation identity does not match');
  } else if (!digest(result.snapshotId) || !Number.isFinite(Date.parse(result.updatedAt))) {
    throw new Error('Missing a complete successful publication receipt');
  }
  return result;
}

async function currentPullRequest(github, context, state) {
  const { data: pr } = await github.rest.pulls.get({ ...context.repo, pull_number: state.pr.number });
  return pr;
}

function sameHead(pr, state) {
  return pr.head?.sha === state.pr.headSha && pr.base?.ref === 'main'
    && pr.base?.repo?.full_name === REPOSITORY && !pr.merged;
}

async function comment(github, context, state, result, metadata) {
  const marker = `<!-- forshor-publication:${state.pr.headSha} -->`;
  const verification = `https://github.com/${REPOSITORY}/actions/runs/${state.run.id}/attempts/${state.run.attempt}`;
  const isPolicy = metadata.kind === 'policy';
  const archive = `https://github.com/${REPOSITORY}/tree/submission-results/results/${isPolicy ? 'policy-submissions' : 'policies'}/${state.pr.headSha}`;
  const snapshotPath = isPolicy ? `/results/v2/e/${metadata.epoch}/s/${result.snapshotId}/dashboard.json` : `/results/snapshots/${result.snapshotId}/dashboard.json`;
  const snapshot = result.snapshotId ? `\nSnapshot: [\`${result.snapshotId.slice(0, 12)}\`](${DASHBOARD}${snapshotPath}).` : '';
  const body = `${marker}\n### Submission accepted and published\n\n`
    + `Lean verification passed and Google confirmed publication for commit \`${state.pr.headSha}\`.\n\n`
    + `[Lean verification](${verification}) · [Qualtran and publication](${state.detailsUrl}) · [Archived ${isPolicy ? 'policy' : 'table'}](${archive}) · [Staging dashboard](${DASHBOARD})${snapshot}\n\n`
    + (isPolicy ? `Refresh the dashboard to see ${result.name ? `\`${result.name}\`` : 'your policy'}. A valid policy need not take first place. ` : 'Refresh the dashboard to see the latest results. A valid table need not change the winning plan. ')
    + 'Accepted submission PRs are closed without merging; their results and source remain in the archive. '
    + `Use a new submission PR for your next ${isPolicy ? 'policy' : 'table'}.`;
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...context.repo, issue_number: state.pr.number, per_page: 100,
  });
  const existing = comments.find(c => c.user?.login === 'github-actions[bot]' && c.body?.startsWith(marker));
  if (existing) await github.rest.issues.updateComment({ ...context.repo, comment_id: existing.id, body });
  else await github.rest.issues.createComment({ ...context.repo, issue_number: state.pr.number, body });
}

async function finalize({ github, context, core, outcome }) {
  if (!fs.existsSync(STATE)) return; // Source did not pass trusted PR resolution.
  const state = JSON.parse(fs.readFileSync(STATE, 'utf8'));
  // An older finally/retry cannot overwrite the check now owned by a newer run.
  const { data: check } = await github.rest.checks.get({ ...context.repo, check_run_id: state.checkId });
  // GitHub rewrites details_url for checks created by the Actions app. Bind the
  // owner through external_id, which GitHub preserves, not that display URL.
  if (state.detailsUrl !== workflowUrl(context)
      || check.external_id !== state.externalId || check.head_sha !== state.pr.headSha) return;
  let closedHere = false;
  try {
    const source = JSON.parse(fs.readFileSync('publication-source.json', 'utf8'));
    if (source.pr.number !== state.pr.number || source.pr.headSha !== state.pr.headSha
        || source.run.id !== state.run.id || source.run.run_attempt !== state.run.attempt)
      throw new Error('Trusted source identity changed');
    if (!sameHead(await currentPullRequest(github, context, state), state)) {
      await finishCheck(github, context, state, 'cancelled', 'Superseded submission',
        'The PR has moved or was merged. This old result will not close the current PR.');
      return;
    }
    if (source.run.conclusion !== 'success') {
      await finishCheck(github, context, state, 'skipped', 'Not run: Lean did not pass',
        `Lean concluded **${source.run.conclusion}**. Fix the table and push to this PR. Published results are unchanged.`);
      return;
    }
    if (outcome !== 'success') {
      await finishCheck(github, context, state, outcome === 'cancelled' ? 'cancelled' : 'failure',
        'Resource estimation or publication did not finish',
        `The PR remains open. [Inspect and rerun the publisher](${state.detailsUrl}); accepted Lean verification is reused.`);
      return;
    }
    const metadata = JSON.parse(fs.readFileSync('evaluation-metadata.json', 'utf8'));
    const result = receipt(source, metadata, JSON.parse(fs.readFileSync('publication-result.json', 'utf8')));
    await comment(github, context, state, result, metadata);
    // Recheck after network operations. GitHub's close endpoint has no expected
    // SHA guard, so inspect its response too and restore open if a push raced it.
    const pr = await currentPullRequest(github, context, state);
    if (!sameHead(pr, state)) {
      await finishCheck(github, context, state, 'cancelled', 'Superseded submission', 'A newer commit needs its own checks. The PR remains open.');
      return;
    }
    if (pr.state === 'open') {
      const { data: closed } = await github.rest.pulls.update({ ...context.repo, pull_number: state.pr.number, state: 'closed' });
      closedHere = true;
      if (!sameHead(closed, state)) {
        await github.rest.pulls.update({ ...context.repo, pull_number: state.pr.number, state: 'open' });
        closedHere = false;
        await finishCheck(github, context, state, 'cancelled', 'Superseded submission', 'A push raced PR closure. The PR was reopened for the new commit.');
        return;
      }
    }
    await finishCheck(github, context, state, 'success', 'Accepted and published',
      `[Results are on staging](${DASHBOARD}). The submission is archived and the PR is closed without merging.\n\n[Publisher details](${state.detailsUrl})`);
  } catch (error) {
    // If final success reporting failed after our close, restore a recoverable
    // open PR. Do not reopen a PR that was already closed before this attempt.
    if (closedHere) await github.rest.pulls.update({ ...context.repo, pull_number: state.pr.number, state: 'open' });
    await finishCheck(github, context, state, 'failure', 'Publication reporting needs recovery',
      `Could not confirm publication and finish PR reporting. [Inspect and rerun the publisher](${state.detailsUrl}).`);
    core.setFailed(error.message);
  }
}

module.exports = { NAME, begin, finalize, receipt };
