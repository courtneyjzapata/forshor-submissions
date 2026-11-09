'use strict';
// Trusted main only: choose attribution from GitHub and bind evidence to the exact Lean file.
const fs = require('node:fs');
const { createHash } = require('node:crypto');
const REPOSITORY = 'zapatacomputing/forshor-submissions';
const SOURCE = 'TableGeneration/Submission/Policy.lean';
const INDEX = 'leaderboard/policy-submissions.json';
const digest = text => createHash('sha256').update(text).digest('hex');

async function content(github, context, path, ref) {
  const { data } = await github.rest.repos.getContent({ ...context.repo, path, ref });
  if (data.encoding !== 'base64' || typeof data.content !== 'string') throw new Error('Expected a versioned source file');
  return Buffer.from(data.content, 'base64').toString('utf8');
}

async function accepted({ github, context, identity, readJson }) {
  const index = await readJson(github, context, INDEX);
  if (!index) return null;
  if (index.schema !== 'forshor.policy-archive/v1' || !Array.isArray(index.policies)) throw new Error('Invalid policy archive');
  const entry = index.policies.find(p => p.policy_id === identity.headSha);
  if (!entry) return null;
  const base = `results/policy-submissions/${identity.headSha}`;
  const verification = await readJson(github, context, `${base}/verification.json`);
  const receipt = verification?.ciVerification;
  if (!receipt || Object.entries(identity).some(([key, value]) => receipt[key] !== value)) return null;
  if (entry.path !== base || entry.source?.repository !== REPOSITORY
      || String(entry.source.run_id) !== receipt.runId || Number(entry.source.pr_number) !== receipt.pullRequest
      || !/^[1-9][0-9]*$/.test(receipt.runId) || !Number.isSafeInteger(receipt.runAttempt) || receipt.runAttempt < 1)
    throw new Error('Invalid archived policy verification identity');
  return { receipt, verification, base };
}

async function prepare({ github, context, core, run, pr, identity, result, recovered }) {
  const { data: details } = await github.rest.pulls.get({ ...context.repo, pull_number: pr.number });
  const login = details.user.login;
  const files = await github.paginate(github.rest.pulls.listFiles, { ...context.repo, pull_number: pr.number });
  if (files.length !== 1 || files[0].filename !== SOURCE || files[0].previous_filename)
    throw new Error('A policy submission may change only Policy.lean');
  let verification;
  if (recovered) {
    verification = { ...recovered.verification,
      leanSource: await content(github, context, `${recovered.base}/Policy.lean`, 'submission-results') };
  } else {
    if (result.kind !== 'policy' || result.challenge !== 'forshor-policy') throw new Error('Not a policy verification result');
    verification = JSON.parse(fs.readFileSync('artifacts/verification.json', 'utf8'));
    if (result.policy?.digest !== verification.digest) throw new Error('Policy verification digest changed');
  }
  const source = await content(github, context, SOURCE, pr.headSha);
  if (verification.schema !== 'forshor.policy-verification/v1' || verification.login !== login
      || verification.leanSource !== source || verification.leanSha256 !== digest(source))
    throw new Error('Policy evidence does not match the GitHub author and exact submitted source');
  const receipt = recovered?.receipt ?? { ...identity, runId: String(run.id), runAttempt: run.run_attempt, pullRequest: pr.number };
  if (receipt.pullRequest !== pr.number) throw new Error('Archived verification belongs to another PR');
  verification.ciVerification = receipt;
  fs.mkdirSync('artifacts', { recursive: true });
  fs.writeFileSync('artifacts/verification.json', JSON.stringify(verification));
  const evaluationKey = digest(`${pr.headSha}:${receipt.runId}:${pr.number}`);
  fs.writeFileSync('evaluation-metadata.json', JSON.stringify({
    kind: 'policy', repository: REPOSITORY, headSha: pr.headSha, runId: receipt.runId,
    githubLogin: login, pullRequestUrl: `https://github.com/${REPOSITORY}/pull/${pr.number}`,
    pullRequest: pr.number, submittedAt: details.created_at, evaluationKey, policyDigest: verification.digest,
  }));
  core.setOutput('kind', 'policy');
  await core.summary.addHeading(recovered ? 'Reusing archived policy verification' : 'Policy verified; ready to publish')
    .addRaw('The trusted publishing step revalidates this evidence, archives the exact Lean file, and updates the v2 boards.\n').write();
}

module.exports = { accepted, prepare };
