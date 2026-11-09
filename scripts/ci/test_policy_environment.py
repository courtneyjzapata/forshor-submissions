import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from policy_environment import configuration, build

ROOT = Path(__file__).resolve().parents[2]


class PolicyEnvironmentTests(unittest.TestCase):
    def test_only_the_trusted_public_pin_and_self_sto_are_allowed(self):
        config = json.loads((ROOT / 'evaluation/policy-trees.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'evaluation').mkdir()
            for key, value in [('forshor', {**config['forshor'], 'repo': 'https://untrusted.example/tree'}), ('sto', {'repo': 'elsewhere'})]:
                bad = copy.deepcopy(config); bad[key] = value
                (root / 'evaluation/policy-trees.json').write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    configuration(root)

    def test_wrong_forshor_checkout_is_rejected_before_building(self):
        with patch('subprocess.check_output', return_value='a' * 40), patch('subprocess.run') as run:
            with self.assertRaisesRegex(ValueError, 'pin'):
                build(ROOT, Path('/tmp/wrong-forshor'), Path('/tmp/unused-policy-log.json'))
            run.assert_not_called()
