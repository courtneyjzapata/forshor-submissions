'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const reporting = require('./ci/table_generation_report.js');
const publication = require('./ci/publication.js');
const HEAD = 'a'.repeat(40);
const context = { repo: { owner: 'zapatacomputing', repo: 'forshor-submissions' } };

test('the real archiver generates operations first and merges both policies after a conflict', async () => {
  const root = process.cwd(), directory = fs.mkdtempSync(path.join(os.tmpdir(), 'forshor-full-archive-'));
  const oldRun = process.env.SOURCE_RUN_ID, oldAttempt = process.env.SOURCE_RUN_ATTEMPT;
  const baseline = JSON.parse(fs.readFileSync('evaluation/fixtures/baseline-state.json')).archive;
  const competing = structuredClone(baseline);
  competing.policies.push({ ...structuredClone(baseline.policies[0]), policy_id: 'b'.repeat(40) });
  for (const dir of ['scripts', 'leaderboard', 'artifacts']) fs.mkdirSync(path.join(directory, dir));
  fs.copyFileSync('scripts/leaderboard.py', path.join(directory, 'scripts/leaderboard.py'));
  fs.copyFileSync('leaderboard/config.json', path.join(directory, 'leaderboard/config.json'));
  const targets = [];
  const config = JSON.parse(fs.readFileSync('leaderboard/config.json'));
  for (let k = config.target_matrix.k_min; k <= config.target_matrix.k_max; k++)
    for (const mode of config.target_matrix.modes) targets.push({ mode, k });
  const result = { schema_version: 1, challenge: 'table-generation', status: 'success',
    metadata: { head_sha: HEAD, repository: 'zapatacomputing/forshor-submissions', pr_number: '1', run_id: '123' },
    target: { configured: true, targets }, metrics: { targets: [{ mode: 'PhaseProduct', k: 2,
      arithmetic_operation_count: 0, parallel_phase_product_layer_count: 0, phase_product_count: 0,
      total_operation_count: 0, point_count: 0, program: '[]', points: '[]', point_order: '[]' }] } };
  fs.writeFileSync(path.join(directory, 'artifacts/table-generation-submission-result.json'), JSON.stringify(result));
  fs.writeFileSync(path.join(directory, 'artifacts/table-generation-results.json'), '{}');
  fs.writeFileSync(path.join(directory, 'artifacts/table-generation-results.md'), 'verified');
  fs.writeFileSync(path.join(directory, 'artifacts/table-generation-submission-source.zip'), 'source bytes');
  let head = 'first', next = 0, conflicts = 0;
  const blobs = new Map(), trees = new Map();
  const github = { paginate: async (method, params) => method(params), rest: {
    actions: { getWorkflowRunAttempt: async () => ({ data: { conclusion: 'success', head_sha: HEAD } }) },
    repos: {
      listPullRequestsAssociatedWithCommit: async () => [{ number: 1, base: { ref: 'main' }, head: { sha: HEAD } }],
      getContent: async ({ ref }) => ({ data: { encoding: 'base64', content: Buffer.from(JSON.stringify(ref === 'first' ? baseline : competing)).toString('base64') } }),
    },
    pulls: { listFiles: async () => [{ filename: 'TableGeneration/Submission/Policy.lean' }] },
    git: {
      getRef: async () => ({ data: { object: { sha: head } } }),
      getCommit: async ({ commit_sha }) => ({ data: { tree: { sha: commit_sha } } }),
      createBlob: async ({ content }) => { const sha = `blob-${++next}`; blobs.set(sha, Buffer.from(content, 'base64').toString()); return { data: { sha } }; },
      createTree: async ({ base_tree, tree }) => { const sha = `tree-${++next}`; trees.set(sha, { parent: base_tree, tree }); return { data: { sha } }; },
      createCommit: async ({ tree }) => ({ data: { sha: tree } }),
      updateRef: async ({ sha }) => { if (!conflicts++) { head = 'competing'; throw Object.assign(new Error('Conflict'), { status: 422 }); } head = sha; },
    },
  } };
  try {
    process.chdir(directory); process.env.SOURCE_RUN_ID = '123'; process.env.SOURCE_RUN_ATTEMPT = '1';
    await reporting.persistBenchmarkResults({ github, context, core: { setOutput() {} } });
    const tree = trees.get(head).tree;
    const stored = name => JSON.parse(blobs.get(tree.find(entry => entry.path === name).sha));
    const index = stored('leaderboard/results.json');
    assert.equal(index.policies.length, baseline.policies.length + 2);
    assert.ok(index.policies.some(p => p.policy_id === HEAD));
    assert.ok(index.policies.some(p => p.policy_id === 'b'.repeat(40)));
    assert.equal(stored(`results/policies/${HEAD}/operations.json`).policy_id, HEAD);
  } finally {
    process.chdir(root); fs.rmSync(directory, { recursive: true, force: true });
    if (oldRun === undefined) delete process.env.SOURCE_RUN_ID; else process.env.SOURCE_RUN_ID = oldRun;
    if (oldAttempt === undefined) delete process.env.SOURCE_RUN_ATTEMPT; else process.env.SOURCE_RUN_ATTEMPT = oldAttempt;
  }
});

test('a competing archive update rebuilds the index against the winning parent', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'forshor-archive-'));
  const index = path.join(directory, 'index.json');
  const parents = [], blobs = new Map(), trees = new Map();
  let head = 'first', next = 0, conflicts = 0;
  const github = { rest: { git: {
    getRef: async () => ({ data: { object: { sha: head } } }),
    getCommit: async ({ commit_sha }) => ({ data: { tree: { sha: commit_sha } } }),
    createBlob: async ({ content }) => {
      const sha = `blob-${++next}`; blobs.set(sha, JSON.parse(Buffer.from(content, 'base64'))); return { data: { sha } };
    },
    createTree: async ({ base_tree, tree }) => {
      const sha = `tree-${++next}`; trees.set(sha, { parent: base_tree, tree }); return { data: { sha } };
    },
    createCommit: async ({ tree }) => ({ data: { sha: tree } }),
    updateRef: async ({ sha }) => {
      if (!conflicts++) { head = 'competing-policy'; throw Object.assign(new Error('Not fast-forward'), { status: 422 }); }
      head = sha;
    },
  } } };
  try {
    await reporting.persistFiles(github, context, [], 'persist this policy', async parent => {
      parents.push(parent);
      fs.writeFileSync(index, JSON.stringify(parent === 'first' ? ['this-policy'] : ['other-policy', 'this-policy']));
      return [['leaderboard/results.json', index]];
    });
    assert.deepEqual(parents, ['first', 'competing-policy']);
    assert.equal(trees.get(head).parent, 'competing-policy');
    assert.deepEqual(blobs.get(trees.get(head).tree[0].sha), ['other-policy', 'this-policy']);
  } finally { fs.rmSync(directory, { recursive: true, force: true }); }
});

test('recovery resolves a closed PR through GitHub and still checks admitted files', async () => {
  const github = { paginate: async (method, params) => method(params), rest: {
    repos: { listPullRequestsAssociatedWithCommit: async () => [] },
    pulls: {
      list: async params => {
        assert.equal(params.state, 'all'); assert.equal(params.head, 'contributor:submission');
        return [{ number: 1, base: { ref: 'main' }, head: { sha: HEAD } }];
      },
      listFiles: async () => [{ filename: 'TableGeneration/Submission/Policy.lean' }],
    },
  } };
  const run = { head_sha: HEAD, head_branch: 'submission', head_repository: { owner: { login: 'contributor' } } };
  assert.deepEqual(await reporting.resolveTrustedPullRequest(github, context, run), { number: 1, headSha: HEAD });
  github.rest.pulls.listFiles = async () => [{ filename: '.github/workflows/table-generation-submission.yml' }];
  await assert.rejects(reporting.resolveTrustedPullRequest(github, context, run), /outside the submission surface/);
});

test('an old run for a PR that has moved is explicitly superseded', async () => {
  const github = { paginate: async (method, params) => method(params), rest: {
    repos: { listPullRequestsAssociatedWithCommit: async () => [{ number: 1, base: { ref: 'main' }, head: { sha: 'b'.repeat(40) } }] },
  } };
  await assert.rejects(reporting.resolveTrustedPullRequest(github, context, { head_sha: HEAD }),
    error => error.code === 'SUPERSEDED');
});

test('verification failure produces a visible outcome without archiving or publishing', async () => {
  const output = {}, messages = [];
  const summary = { addHeading(x) { messages.push(x); return this; }, addRaw(x) { messages.push(x); return this; },
    addLink() { return this; }, async write() {} };
  await publication.inspect({ github: {}, core: { summary, setOutput(k, v) { output[k] = v; } }, context: {
    ...context, payload: { workflow_run: { event: 'pull_request', path: '.github/workflows/table-generation-submission.yml',
      id: 123, run_attempt: 1, head_sha: HEAD, conclusion: 'failure', html_url: 'https://github.com/run' } },
  } });
  assert.equal(output.process, 'false');
  assert.match(messages.join(' '), /Published results are unchanged/);
});

test('artifact-selected PR identities and forged receipts are rejected', async () => {
  await assert.rejects(publication.inspect({ github: {}, core: {}, context: {
    ...context, payload: { workflow_run: { event: 'workflow_dispatch' } },
  } }), /Unexpected source/);
  const identity = publication.verificationIdentity(HEAD);
  const receipt = { ...identity, runId: '123', runAttempt: 1, pullRequest: 1 };
  assert.doesNotThrow(() => publication.assertReceipt(receipt, identity));
  assert.throws(() => publication.assertReceipt({ ...receipt, key: 'forged' }, identity), /Invalid trusted/);
});

test('accepted verification recovers after the original run artifact disappears', async t => {
  const identity = publication.verificationIdentity(HEAD);
  const receipt = { ...identity, runId: '123', runAttempt: 1, pullRequest: 1 };
  const index = { policies: [{ policy_id: HEAD, source: {
    repository: 'zapatacomputing/forshor-submissions', run_id: '123', pr_number: '1',
  } }] };
  const event = { id: 123, run_attempt: 1, event: 'pull_request', conclusion: 'success',
    path: '.github/workflows/table-generation-submission.yml', head_sha: HEAD };
  const output = {};
  t.mock.method(fs, 'writeFileSync', () => {});
  const github = { paginate: async (method, params) => method(params), rest: {
    actions: {
      getWorkflowRunAttempt: async () => ({ data: event }),
      listWorkflowRunArtifacts: async () => ({ data: { artifacts: [
        { name: 'table-generation-submission-123-2', expired: false },
      ] } }),
    },
    repos: {
      listPullRequestsAssociatedWithCommit: async () => [{ number: 1, base: { ref: 'main' }, head: { sha: HEAD } }],
      getContent: async ({ path: name }) => ({ data: { encoding: 'base64', content: Buffer.from(JSON.stringify(
        name.startsWith('results/evaluations/') ? receipt : index)).toString('base64') } }),
    },
    pulls: { listFiles: async () => [{ filename: 'TableGeneration/Submission/Policy.lean' }] },
  } };
  await publication.inspect({ github, context: { ...context, payload: { workflow_run: event } },
    core: { setOutput(k, v) { output[k] = v; } } });
  assert.equal(output.process, 'true');
  assert.equal(output.download, 'false');
  assert.equal(output.artifact, 'table-generation-submission-123-2');
  github.rest.actions.listWorkflowRunArtifacts = async () => ({ data: { artifacts: [] } });
  await publication.inspect({ github, context: { ...context, payload: { workflow_run: event } },
    core: { setOutput(k, v) { output[k] = v; } } });
  assert.equal(output.download, 'false', 'modern recovery needs no surviving run artifact');
});

test('recovery derives publication only from the trusted archive and never reads replacement artifacts', async t => {
  const identity = publication.verificationIdentity(HEAD);
  const receipt = { ...identity, runId: '123', runAttempt: 1, pullRequest: 1 };
  const index = { policies: [{ policy_id: HEAD, source: {
    repository: 'zapatacomputing/forshor-submissions', run_id: '123', pr_number: '1',
  } }] };
  const originalRead = fs.readFileSync;
  const writes = new Map();
  t.mock.method(fs, 'readFileSync', (name, ...args) => {
    if (name === 'publication-source.json') return JSON.stringify({ run: { id: 123 }, pr: { headSha: HEAD, number: 1 } });
    assert.ok(!String(name).startsWith('artifacts/'), 'replacement artifacts must not be used as verification');
    return originalRead(name, ...args);
  });
  t.mock.method(fs, 'writeFileSync', (name, content) => writes.set(name, content));
  const github = { rest: {
    repos: { getContent: async ({ path: name }) => ({ data: { encoding: 'base64', content: Buffer.from(JSON.stringify(
      name.startsWith('results/evaluations/') ? receipt : index)).toString('base64') } }) },
    pulls: { get: async () => ({ data: { user: { login: 'contributor' }, html_url: 'https://github.com/zapatacomputing/forshor-submissions/pull/1', created_at: '2026-01-01T00:00:00Z' } }) },
  } };
  const summary = { addHeading() { return this; }, addLink() { return this; }, addRaw() { return this; }, async write() {} };
  await publication.archive({ github, context, core: { summary } });
  const metadata = JSON.parse(writes.get('evaluation-metadata.json'));
  assert.equal(metadata.runId, '123');
  assert.equal(metadata.headSha, HEAD);
  assert.equal(metadata.evaluationKey, publication.evaluationKey(identity));
});
