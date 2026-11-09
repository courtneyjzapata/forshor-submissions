import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import publish_policy
import publish


class PolicyPublisherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = Path.cwd()
        os.chdir(self.temp.name)
        self.metadata = {'kind': 'policy', 'repository': 'zapatacomputing/forshor-submissions', 'headSha': 'a' * 40,
                         'githubLogin': 'contributor', 'pullRequest': 12, 'runId': '123',
                         'evaluationKey': 'b' * 64, 'policyDigest': 'c' * 64}
        Path('evaluation-metadata.json').write_text(json.dumps(self.metadata))

    def tearDown(self):
        os.chdir(self.previous)
        self.temp.cleanup()

    def test_already_published_skips_engine_and_keeps_a_bound_v2_receipt(self):
        state = {'epoch': '7a11b2b8b6d68718', 'completedEvaluations': {'b' * 64: {'headSha': 'a' * 40, 'runId': '123'}}}
        env = {'PUBLISHER_URL': 'https://publisher.example', 'PUBLISHER_TOKEN': 'test-only', 'GITHUB_OUTPUT': 'output.txt'}
        with patch.dict(os.environ, env), patch('sys.argv', ['publish_policy.py', '--check']), \
                patch.object(publish, 'request_json', return_value=state), patch('subprocess.run') as run:
            self.assertEqual(publish_policy.main(), 0)
            run.assert_not_called()
        result = json.loads(Path('publication-result.json').read_text())
        self.assertEqual(result['policy']['headSha'], self.metadata['headSha'])
        self.assertEqual(result['evaluationKey'], self.metadata['evaluationKey'])
        self.assertTrue(result['alreadyPublished'])
        self.assertEqual(Path('output.txt').read_text(), 'complete=true\n')
        self.assertEqual(json.loads(Path('evaluation-metadata.json').read_text())['epoch'], state['epoch'])

    def test_new_evaluation_does_not_claim_a_receipt(self):
        env = {'PUBLISHER_URL': 'https://publisher.example', 'PUBLISHER_TOKEN': 'test-only', 'GITHUB_OUTPUT': 'output.txt'}
        with patch.dict(os.environ, env), patch('sys.argv', ['publish_policy.py', '--check']), \
                patch.object(publish, 'request_json', return_value={'epoch': '7a11b2b8b6d68718', 'completedEvaluations': {}}):
            self.assertEqual(publish_policy.main(), 0)
        self.assertFalse(Path('publication-result.json').exists())
        self.assertEqual(Path('output.txt').read_text(), 'complete=false\n')

    def test_intake_uses_trusted_metadata_and_keeps_tokens_out_of_arguments(self):
        env = {'PUBLISHER_URL': 'https://publisher.example', 'ENGINE_PYTHON': '/engine/python', 'PUBLISHER_TOKEN': 'test-only'}
        with patch.dict(os.environ, env), patch('sys.argv', ['publish_policy.py']), patch('subprocess.run') as run:
            run.return_value.returncode = 0
            self.assertEqual(publish_policy.main(), 0)
            args = run.call_args.args[0]
        self.assertEqual(args[0], '/engine/python')
        self.assertEqual(args[args.index('--head-sha') + 1], self.metadata['headSha'])
        self.assertEqual(args[args.index('--run-id') + 1], '123')
        self.assertEqual(args[args.index('--archive') + 1], 'archive')
        self.assertNotIn('test-only', args)
