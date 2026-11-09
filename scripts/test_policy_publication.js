'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createHash } = require('node:crypto');
const policy = require('./ci/policy_publication.js');
const publication = require('./ci/publication.js');
const HEAD = 'a'.repeat(40), TEXT = 'namespace PolicySubmission\nend PolicySubmission\n';
const hash = text => createHash('sha256').update(text).digest('hex');

async function fixture(fn) {
  const root = process.cwd(), directory = fs.mkdtempSync(path.join(os.tmpdir(), 'forshor-policy-publish-'));
  const identity = publication.verificationIdentity(HEAD);
  process.chdir(directory); fs.mkdirSync('artifacts');
  const verification = { schema: 'forshor.policy-verification/v1', login: 'contributor', digest: 'b'.repeat(64),
    leanSource: TEXT, leanSha256: hash(TEXT), model: {}, envelope: {} };
  const result = { kind: 'policy', challenge: 'forshor-policy', policy: { digest: verification.digest } };
  const outputs = {}, calls = [];
  const summary = { addHeading() { return this; }, addRaw() { return this; }, async write() {} };
  const input = { identity, result, run: { id: 123, run_attempt: 2 }, pr: { number: 12, headSha: HEAD },
    context: { repo: { owner: 'zapatacomputing', repo: 'forshor-submissions' } },
    core: { setOutput(k,v) { outputs[k] = v; }, summary }, github: { paginate: async (f,p) => f(p), rest: {
      pulls: {
        get: async () => ({ data: { user: { login: 'contributor' }, created_at: '2026-11-09T00:00:00Z' } }),
        listFiles: async () => [{ filename: 'TableGeneration/Submission/Policy.lean' }],
      },
      repos: { getContent: async p => { calls.push(p); return { data: { encoding: 'base64', content: Buffer.from(TEXT).toString('base64') } }; } },
    } } };
  const write = () => fs.writeFileSync('artifacts/verification.json', JSON.stringify(verification));
  write();
  try { await fn({ input, verification, result, outputs, calls, write }); }
  finally { process.chdir(root); fs.rmSync(directory, { recursive: true, force: true }); }
}

test('policy publication binds source, GitHub attribution and stable evaluation identity', () => fixture(async f => {
  await policy.prepare(f.input);
  const metadata = JSON.parse(fs.readFileSync('evaluation-metadata.json'));
  assert.equal(metadata.kind, 'policy');
  assert.equal(metadata.githubLogin, 'contributor');
  assert.equal(metadata.evaluationKey, hash(`${HEAD}:123:12`));
  assert.equal(f.calls[0].ref, HEAD);
  assert.equal(f.outputs.kind, 'policy');
  const v = JSON.parse(fs.readFileSync('artifacts/verification.json'));
  assert.equal(v.ciVerification.headSha, HEAD);
  assert.equal(v.ciVerification.runAttempt, 2);
}));

for (const field of ['login', 'leanSource', 'leanSha256', 'digest']) {
  test(`a forged policy ${field} cannot reach publication`, () => fixture(async f => {
    f.verification[field] = 'forged'; f.write();
    await assert.rejects(policy.prepare(f.input));
    assert.ok(!fs.existsSync('evaluation-metadata.json'));
  }));
}

test('helper or renamed files cannot be admitted as a whole-policy submission', () => fixture(async f => {
  f.input.github.rest.pulls.listFiles = async () => [{ filename: 'TableGeneration/Submission/Policy.lean' }, { filename: 'TableGeneration/Submission/Policy/Helper.lean' }];
  await assert.rejects(policy.prepare(f.input), /only Policy/);
  f.input.github.rest.pulls.listFiles = async () => [{ filename: 'TableGeneration/Submission/Policy.lean', previous_filename: 'lakefile.lean' }];
  await assert.rejects(policy.prepare(f.input), /only Policy/);
}));

test('publication can recover from the trusted archive without the run artifact', () => fixture(async f => {
  const receipt = { ...f.input.identity, runId: '111', runAttempt: 1, pullRequest: 12 };
  const recovered = { receipt, base: `results/policy-submissions/${HEAD}`, verification: { ...f.verification, ciVerification: receipt } };
  delete recovered.verification.leanSource;
  fs.unlinkSync('artifacts/verification.json');
  await policy.prepare({ ...f.input, recovered });
  const metadata = JSON.parse(fs.readFileSync('evaluation-metadata.json'));
  assert.equal(metadata.runId, '111');
  assert.equal(metadata.evaluationKey, hash(`${HEAD}:111:12`));
  assert.equal(f.calls[0].ref, 'submission-results');
  assert.equal(f.calls[1].ref, HEAD);
}));

test('archive recovery requires the trusted fingerprint and index source binding', () => fixture(async f => {
  const receipt = { ...f.input.identity, runId: '111', runAttempt: 1, pullRequest: 12 };
  const entry = { policy_id: HEAD, path: `results/policy-submissions/${HEAD}`,
    source: { repository: 'zapatacomputing/forshor-submissions', run_id: '111', pr_number: 12 } };
  const readJson = async (g,c,name) => name.startsWith('leaderboard/') ? { schema: 'forshor.policy-archive/v1', policies: [entry] } : { ciVerification: receipt };
  assert.ok(await policy.accepted({ ...f.input, readJson }));
  entry.source.run_id = '222';
  await assert.rejects(policy.accepted({ ...f.input, readJson }), /identity/);
  receipt.fingerprint = 'changed';
  assert.equal(await policy.accepted({ ...f.input, readJson }), null);
}));
