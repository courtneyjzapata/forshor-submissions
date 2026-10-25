'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const lifecycle = require('./ci/pr_publication.js');
const HEAD = 'a'.repeat(40), OTHER = 'b'.repeat(40), KEY = 'c'.repeat(64);
const REPO = 'zapatacomputing/forshor-submissions';

async function fixture(fn) {
  const root = process.cwd(), directory = fs.mkdtempSync(path.join(os.tmpdir(), 'forshor-pr-check-'));
  process.chdir(directory);
  const calls = [], errors = [], checks = [], comments = [];
  const context = { repo: { owner: 'zapatacomputing', repo: 'forshor-submissions' }, runId: 456 };
  const source = { run: { id: 123, run_attempt: 1, conclusion: 'success' }, pr: { number: 12, headSha: HEAD } };
  let pr = { number: 12, head: { sha: HEAD }, base: { ref: 'main', repo: { full_name: REPO } }, state: 'open', merged: false };
  const github = { paginate: async (method, params) => method(params), rest: {
    checks: {
      listForRef: async () => checks,
      create: async args => { calls.push(['create-check', args]); const c = { ...args, id: 7, app: { slug: 'github-actions' } }; checks.push(c); return { data: c }; },
      update: async args => { calls.push(['update-check', args]); Object.assign(checks[0], args); return { data: checks[0] }; },
      get: async () => ({ data: checks[0] }),
    },
    pulls: {
      get: async () => ({ data: structuredClone(pr) }),
      update: async args => { calls.push(['update-pr', args]); pr.state = args.state; return { data: structuredClone(pr) }; },
    },
    issues: {
      listComments: async () => comments,
      createComment: async args => { calls.push(['comment', args]); comments.push({ ...args, id: 9, user: { login: 'github-actions[bot]' } }); },
      updateComment: async args => { calls.push(['update-comment', args]); comments[0].body = args.body; },
    },
  } };
  const core = { setFailed: message => errors.push(message) };
  const write = (file, value) => fs.writeFileSync(file, JSON.stringify(value));
  write('publication-source.json', source);
  write('evaluation-metadata.json', { repository: REPO, headSha: HEAD, runId: '123', evaluationKey: KEY,
    pullRequestUrl: `https://github.com/${REPO}/pull/12` });
  write('publication-result.json', { snapshotId: 'd'.repeat(64), updatedAt: '2026-10-25T02:37:59.063Z' });
  const begin = () => lifecycle.begin({ github, context, ...source });
  const finish = (outcome = 'success') => lifecycle.finalize({ github, context, core, outcome });
  try { await fn({ github, context, source, checks, comments, calls, errors, write, begin, finish,
    get pr() { return pr; }, set pr(value) { pr = value; } }); }
  finally { process.chdir(root); fs.rmSync(directory, { recursive: true, force: true }); }
}

test('one check on the exact source SHA; publication receipt precedes comment, close and success', () => fixture(async f => {
  await f.begin();
  assert.equal(f.checks[0].head_sha, HEAD);
  assert.equal(f.checks[0].status, 'in_progress');
  await f.finish();
  assert.deepEqual(f.errors, []);
  assert.equal(f.checks[0].conclusion, 'success');
  assert.equal(f.pr.state, 'closed');
  assert.match(f.comments[0].body, /Submission accepted and published/);
  assert.match(f.comments[0].body, /results\/snapshots\/d{64}/);
  assert.deepEqual(f.calls.slice(-3).map(c => c[0]), ['comment', 'update-pr', 'update-check']);
}));

test('a failed Lean attempt skips Qualtran and leaves the PR open', () => fixture(async f => {
  f.source.run.conclusion = 'failure';
  f.write('publication-source.json', f.source);
  await f.begin(); await f.finish();
  assert.equal(f.checks[0].conclusion, 'skipped');
  assert.equal(f.pr.state, 'open'); assert.equal(f.comments.length, 0);
}));

for (const outcome of ['failure', 'cancelled']) test(`${outcome} cannot close or claim publication even if a receipt exists`, () => fixture(async f => {
  await f.begin(); await f.finish(outcome);
  assert.equal(f.checks[0].conclusion, outcome);
  assert.equal(f.pr.state, 'open'); assert.equal(f.comments.length, 0);
}));

for (const result of [null, {}, { snapshotId: 'd'.repeat(64) }, { alreadyPublished: true, evaluationKey: 'forged' }]) {
  test(`missing or forged publication receipt cannot close a PR: ${JSON.stringify(result)}`, () => fixture(async f => {
    if (result === null) fs.unlinkSync('publication-result.json');
    else f.write('publication-result.json', result);
    await f.begin(); await f.finish();
    assert.equal(f.checks[0].conclusion, 'failure'); assert.equal(f.pr.state, 'open');
    assert.equal(f.comments.length, 0); assert.equal(f.errors.length, 1);
  }));
}

test('publisher retry reuses its check/comment and does not reclose a closed accepted PR', () => fixture(async f => {
  await f.begin(); await f.finish();
  f.write('publication-result.json', { alreadyPublished: true, evaluationKey: KEY });
  await f.begin(); await f.finish();
  assert.equal(f.checks.length, 1); assert.equal(f.comments.length, 1);
  assert.equal(f.calls.filter(c => c[0] === 'update-pr').length, 1);
  assert.equal(f.calls.filter(c => c[0] === 'update-comment').length, 1);
  assert.deepEqual(f.errors, []); assert.equal(f.checks[0].conclusion, 'success');
}));

test('lost-acknowledgement recovery accepts the Google publisher snapshot receipt', () => fixture(async f => {
  f.write('publication-result.json', { alreadyPublished: true, snapshotId: 'd'.repeat(64), updatedAt: '2026-10-25T02:37:59.063Z' });
  await f.begin(); await f.finish();
  assert.deepEqual(f.errors, []); assert.equal(f.checks[0].conclusion, 'success');
  assert.equal(f.pr.state, 'closed');
}));

test('a failed final check update reopens a PR closed by this attempt', () => fixture(async f => {
  await f.begin();
  const update = f.github.rest.checks.update;
  f.github.rest.checks.update = async args => {
    if (args.conclusion === 'success') throw new Error('Final check reporting interrupted');
    return update(args);
  };
  await f.finish();
  assert.equal(f.pr.state, 'open'); assert.equal(f.checks[0].conclusion, 'failure');
  assert.deepEqual(f.errors, ['Final check reporting interrupted']);
}));

test('superseded source never closes a newer PR head', () => fixture(async f => {
  await f.begin(); f.pr.head.sha = OTHER; await f.finish();
  assert.equal(f.pr.state, 'open'); assert.equal(f.checks[0].conclusion, 'cancelled');
  assert.equal(f.comments.length, 0);
}));

test('a push while adding the result comment prevents PR closure', () => fixture(async f => {
  await f.begin();
  f.github.rest.issues.createComment = async () => { f.pr.head.sha = OTHER; };
  await f.finish();
  assert.equal(f.pr.state, 'open'); assert.equal(f.checks[0].conclusion, 'cancelled');
  assert.equal(f.calls.filter(c => c[0] === 'update-pr').length, 0);
}));

test('a push racing the close endpoint reopens the PR for the newer commit', () => fixture(async f => {
  await f.begin();
  const update = f.github.rest.pulls.update;
  f.github.rest.pulls.update = async args => { if (args.state === 'closed') f.pr.head.sha = OTHER; return update(args); };
  await f.finish();
  assert.equal(f.pr.state, 'open'); assert.equal(f.checks[0].conclusion, 'cancelled');
  assert.deepEqual(f.calls.filter(c => c[0] === 'update-pr').map(c => c[1].state), ['closed', 'open']);
}));

for (const endpoint of ['comment', 'close']) test(`${endpoint} API failure produces a red recoverable check and leaves PR open`, () => fixture(async f => {
  await f.begin();
  const fail = async () => { throw new Error('Transient GitHub API failure'); };
  if (endpoint === 'comment') f.github.rest.issues.createComment = fail;
  else f.github.rest.pulls.update = fail;
  await f.finish();
  assert.equal(f.pr.state, 'open'); assert.equal(f.checks[0].conclusion, 'failure');
  assert.deepEqual(f.errors, ['Transient GitHub API failure']);
}));

test('an old finalizer cannot overwrite a newer publisher retry', () => fixture(async f => {
  await f.begin(); f.checks[0].external_id += '-new-attempt';
  const before = f.calls.length; await f.finish();
  assert.equal(f.calls.length, before); assert.equal(f.pr.state, 'open');
}));

test('GitHub Actions canonicalizes details_url without changing trusted check ownership', () => fixture(async f => {
  await f.begin();
  f.checks[0].details_url = `https://github.com/${REPO}/runs/${f.checks[0].id}`;
  await f.finish();
  assert.deepEqual(f.errors, []); assert.equal(f.checks[0].conclusion, 'success');
  assert.equal(f.pr.state, 'closed');
}));

test('recovery upgrades a pending check created before publisher ownership was embedded', () => fixture(async f => {
  await f.begin(); f.checks[0].external_id = 'forshor-publication:123:1';
  f.checks[0].name = 'Qualtran estimation and publication';
  await f.begin(); await f.finish();
  assert.equal(f.checks.length, 1); assert.equal(f.checks[0].conclusion, 'success');
  assert.equal(f.checks[0].name, lifecycle.NAME);
  assert.equal(f.checks[0].external_id, `forshor-publication:123:1:456:${Number(process.env.GITHUB_RUN_ATTEMPT || 1)}`);
}));

test('mismatched trusted source or metadata cannot close the PR', () => fixture(async f => {
  await f.begin(); f.source.pr.number = 99; f.write('publication-source.json', f.source);
  await f.finish();
  assert.equal(f.pr.state, 'open'); assert.equal(f.checks[0].conclusion, 'failure');
  assert.match(f.errors[0], /identity changed/);
}));

test('no trusted check means finalization performs no API operations', () => fixture(async f => {
  await f.finish(); assert.deepEqual(f.calls, []);
}));
