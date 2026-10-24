from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from verification_identity import identity, valid_receipt, reuse


class VerificationIdentityTests(unittest.TestCase):
    def test_commit_and_configuration_change_identity(self):
        with patch('subprocess.check_output', return_value=b'contract-v1'):
            first = identity(Path('.'), 'a' * 40)
            self.assertNotEqual(first['key'], identity(Path('.'), 'b' * 40)['key'])
        with patch('subprocess.check_output', return_value=b'contract-v2'):
            self.assertNotEqual(first['key'], identity(Path('.'), 'a' * 40)['key'])

    def test_forged_or_incomplete_receipts_are_not_reusable(self):
        expected = identity(Path('.'), 'a' * 40)
        receipt = {**expected, 'runId': '123', 'runAttempt': 2, 'pullRequest': 1}
        self.assertTrue(valid_receipt(receipt, expected))
        self.assertFalse(valid_receipt({**receipt, 'fingerprint': 'forged'}, expected))
        self.assertFalse(valid_receipt({**receipt, 'runId': '../elsewhere'}, expected))
        self.assertFalse(valid_receipt({**receipt, 'runAttempt': 0}, expected))

    def test_ci_only_edits_do_not_invalidate_math_but_scoring_changes_do(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', directory], check=True)
            (root / 'TableGeneration').mkdir()
            (root / 'TableGeneration/Basic.lean').write_text('contract')
            subprocess.run(['git', '-C', directory, 'add', '.'], check=True)
            subprocess.run(['git', '-C', directory, '-c', 'user.name=test', '-c', 'user.email=test@example.com',
                            'commit', '-qm', 'contract'], check=True)
            first = identity(root, 'a' * 40)
            (root / 'README.md').write_text('docs')
            subprocess.run(['git', '-C', directory, 'add', '.'], check=True)
            subprocess.run(['git', '-C', directory, '-c', 'user.name=test', '-c', 'user.email=test@example.com',
                            'commit', '-qm', 'docs'], check=True)
            self.assertEqual(first, identity(root, 'a' * 40))
            (root / 'TableGeneration/Basic.lean').write_text('new contract')
            subprocess.run(['git', '-C', directory, 'add', '.'], check=True)
            subprocess.run(['git', '-C', directory, '-c', 'user.name=test', '-c', 'user.email=test@example.com',
                            'commit', '-qm', 'contract change'], check=True)
            self.assertNotEqual(first['key'], identity(root, 'a' * 40)['key'])

    def test_exact_accepted_receipt_skips_verification(self):
        expected = identity(Path('.'), 'a' * 40)
        receipt = {**expected, 'runId': '123', 'runAttempt': 1, 'pullRequest': 1}
        index = {'policies': [{'policy_id': 'a' * 40, 'source': {'run_id': '123'}}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GH_TOKEN': 'test-only'}), \
                patch('urllib.request.urlopen', side_effect=[io.StringIO(json.dumps(receipt)), io.StringIO(json.dumps(index))]):
            self.assertTrue(reuse(Path('.'), 'a' * 40, Path(directory)))
            self.assertEqual(json.loads((Path(directory) / 'reused-verification.json').read_text()), receipt)

    def test_receipt_for_a_replaced_configuration_is_not_reused(self):
        expected = identity(Path('.'), 'a' * 40)
        receipt = {**expected, 'runId': '123', 'runAttempt': 1, 'pullRequest': 1}
        index = {'policies': [{'policy_id': 'a' * 40, 'source': {'run_id': '456'}}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GH_TOKEN': 'test-only'}), \
                patch('urllib.request.urlopen', side_effect=[io.StringIO(json.dumps(receipt)), io.StringIO(json.dumps(index))]):
            self.assertFalse(reuse(Path('.'), 'a' * 40, Path(directory)))

    def test_missing_receipt_is_a_miss_but_api_failure_is_not(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'GH_TOKEN': 'test-only'}):
            with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('https://api.github.com', 404, '', {}, None)):
                self.assertFalse(reuse(Path('.'), 'a' * 40, Path(directory)))
            with patch('urllib.request.urlopen', side_effect=urllib.error.HTTPError('https://api.github.com', 403, '', {}, None)):
                with self.assertRaises(urllib.error.HTTPError):
                    reuse(Path('.'), 'a' * 40, Path(directory))


if __name__ == '__main__':
    unittest.main()
import io
import json
import os
