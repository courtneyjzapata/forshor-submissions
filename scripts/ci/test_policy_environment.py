import copy
import json
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from policy_environment import configuration, build, run_with_disk_budget, share_matching_dependencies, FORSHOR_ROOTS

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

    def test_disk_guard_stops_its_own_process_group_before_logs_are_lost(self):
        process = Mock(pid=123, returncode=None)
        process.poll.return_value = None
        with patch('policy_environment.subprocess.Popen', return_value=process), \
             patch('policy_environment.shutil.disk_usage', return_value=SimpleNamespace(free=2 << 30)), \
             patch('policy_environment.os.killpg') as kill:
            with self.assertRaisesRegex(RuntimeError, '3 GiB'):
                run_with_disk_budget(['lake', 'build'], ROOT, {})
        kill.assert_called_once_with(123, signal.SIGTERM)
        process.wait.assert_called_once_with(timeout=10)

    def test_failed_build_exit_is_preserved(self):
        process = Mock(returncode=7)
        process.poll.return_value = 7
        with patch('policy_environment.subprocess.Popen', return_value=process):
            with self.assertRaises(subprocess.CalledProcessError) as failure:
                run_with_disk_budget(['lake', 'build'], ROOT, {})
        self.assertEqual(failure.exception.returncode, 7)

    def test_targeted_fetch_suppresses_automatic_full_mathlib_download(self):
        config = configuration(ROOT)
        with tempfile.TemporaryDirectory() as directory, \
             patch('policy_environment.subprocess.check_output', return_value=config['forshor']['ref']), \
             patch('policy_environment.share_matching_dependencies'), \
             patch('policy_environment.run_with_disk_budget') as run:
            log = Path(directory) / 'bootstrap.json'
            build(ROOT, Path(directory), log)
            calls = run.call_args_list
            self.assertEqual(calls[0].args[0], ['lake', 'exe', 'cache', 'get', *FORSHOR_ROOTS])
            self.assertEqual(calls[2].args[0], ['lake', 'exe', 'cache', 'get', *config['sto_build']])
            self.assertTrue(all(c.args[2]['MATHLIB_NO_CACHE_ON_UPDATE'] == '1' for c in calls))
            self.assertEqual(len(json.loads(log.read_text())), 4)

    def test_failed_stage_still_writes_timing_and_disk_diagnostics(self):
        config = configuration(ROOT)
        with tempfile.TemporaryDirectory() as directory, \
             patch('policy_environment.subprocess.check_output', return_value=config['forshor']['ref']), \
             patch('policy_environment.run_with_disk_budget', side_effect=RuntimeError('disk budget')):
            log = Path(directory) / 'bootstrap.json'
            with self.assertRaisesRegex(RuntimeError, 'disk budget'):
                build(ROOT, Path(directory), log)
            stages = json.loads(log.read_text())
            self.assertEqual(len(stages), 1)
            self.assertFalse(stages[0]['success'])
            self.assertIn('diskFreeGiB', stages[0])

    def test_dependencies_are_shared_only_for_identical_trusted_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            source, destination = Path(directory) / 'forshor', Path(directory) / 'sto'
            common = {'name': 'mathlib', 'type': 'git', 'url': 'https://example/mathlib', 'rev': 'a' * 40}
            different = {**common, 'name': 'different'}
            for root, packages in [(source, [common, different]), (destination, [common, {**different, 'rev': 'b' * 40}])]:
                root.mkdir()
                (root / 'lake-manifest.json').write_text(json.dumps({'packages': packages}))
                for package in packages:
                    (root / '.lake/packages' / package['name']).mkdir(parents=True)
            share_matching_dependencies(destination, source)
            shared = destination / '.lake/packages/mathlib'
            self.assertTrue(shared.is_symlink())
            self.assertFalse(shared.readlink().is_absolute())
            self.assertEqual(shared.resolve(), (source / '.lake/packages/mathlib').resolve())
            self.assertFalse((destination / '.lake/packages/different').is_symlink())
            # Restored relative links remain safe to prepare again.
            share_matching_dependencies(destination, source)
            self.assertTrue(shared.is_dir())
