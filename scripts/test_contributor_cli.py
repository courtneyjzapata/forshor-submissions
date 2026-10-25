"""Contributor-side trust, freshness, and publication correlation regressions."""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

loader = importlib.machinery.SourceFileLoader('contributor_cli', str(Path(__file__).parents[1] / 'forshor'))
spec = importlib.util.spec_from_loader(loader.name, loader)
cli = importlib.util.module_from_spec(spec)
loader.exec_module(cli)


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


class WorkingFiles(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        git(self.root, 'init', '-b', 'main')
        git(self.root, 'config', 'user.name', 'CLI tests')
        git(self.root, 'config', 'user.email', 'cli@invalid')
        (self.root / cli.POLICY).parent.mkdir(parents=True)
        (self.root / cli.POLICY).write_text('original policy\n')
        (self.root / 'protected.lean').write_text('trusted statement\n')
        (self.root / '.gitignore').write_text('artifacts/\n')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'baseline')
        self.base = git(self.root, 'rev-parse', 'HEAD')

    def test_check_includes_uncommitted_and_untracked_lean_helpers(self):
        before = cli.fingerprint(self.root, self.base)
        (self.root / cli.POLICY).write_text('edited policy\n')
        helper = self.root / cli.HELPERS / 'Nested/Proof.lean'
        helper.parent.mkdir(parents=True)
        helper.write_text('new proof\n')
        paths = cli.validate_changes(self.root, self.base)
        self.assertEqual(paths, [cli.POLICY, str(helper.relative_to(self.root))])
        self.assertNotEqual(before, cli.fingerprint(self.root, self.base))
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), self.base)

    def test_protected_rename_cannot_hide_its_deleted_source(self):
        target = self.root / cli.HELPERS / 'Stolen.lean'
        target.parent.mkdir(parents=True)
        git(self.root, 'mv', 'protected.lean', str(target.relative_to(self.root)))
        git(self.root, 'commit', '-m', 'rename protected file')
        with self.assertRaisesRegex(cli.UserError, 'protected.lean'):
            cli.validate_changes(self.root, self.base)

    def test_staged_unrelated_files_block_submission_before_any_push(self):
        (self.root / 'protected.lean').write_text('changed statement\n')
        git(self.root, 'add', 'protected.lean')
        args = argparse.Namespace(watch=False, json=False, timeout=1, title='test')
        with patch.object(cli, 'authenticate'), patch.object(cli, 'repository', return_value=self.root), \
                patch.object(cli, 'refresh_base', return_value=self.base), patch.object(cli, 'network_git') as push:
            with self.assertRaisesRegex(cli.UserError, 'protected.lean'):
                cli.submit(args)
            push.assert_not_called()

    def test_nested_symlink_is_refused(self):
        helper = self.root / cli.HELPERS / 'Escape.lean'
        helper.parent.mkdir(parents=True)
        helper.symlink_to(self.root / 'protected.lean')
        with self.assertRaisesRegex(cli.UserError, 'symlink'):
            cli.validate_changes(self.root, self.base)

    def test_checker_cache_cannot_replace_an_unrecognized_directory(self):
        cache = cli.storage(self.root) / 'checker'
        cache.mkdir()
        sentinel = cache / 'keep.txt'
        sentinel.write_text('user data')
        with self.assertRaisesRegex(cli.UserError, 'unrecognized'):
            cli.trusted_checkout(self.root, self.base)
        self.assertEqual(sentinel.read_text(), 'user data')

    def test_full_check_rejects_a_preflight_only_success(self):
        artifacts = self.root / 'artifacts/forshor/verification'
        artifacts.mkdir(parents=True)
        (artifacts / 'table-generation-submission-result.json').write_text(json.dumps({'status': 'success', 'phase': 'preflight'}))
        # Pre-create the trusted clone and let check snapshot real edited files.
        cache = self.root / '.git/fake-checker'
        subprocess.run(['git', 'clone', '--quiet', str(self.root), str(cache)], check=True)
        (self.root / cli.POLICY).write_text('edited policy\n')
        with patch.object(cli, 'authenticate'), patch.object(cli, 'lean_environment', return_value={}), \
                patch.object(cli, 'prepare', return_value=cache), patch.object(cli, 'logged'):
            with self.assertRaisesRegex(cli.UserError, 'Full verification'):
                cli.check(self.root, self.base)
        self.assertNotIn('checked', cli.read_state(self.root))
        self.assertEqual((self.root / cli.POLICY).read_text(), 'edited policy\n')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD'), self.base)

    def test_submit_rechecks_after_an_edit_instead_of_reusing_stale_success(self):
        cli.write_state(self.root, {'checked': {'base': self.base, 'digest': cli.fingerprint(self.root, self.base)}})
        (self.root / cli.POLICY).write_text('changed after verification\n')
        args = argparse.Namespace(watch=False, json=False, timeout=1, title='test')
        with patch.object(cli, 'authenticate'), patch.object(cli, 'repository', return_value=self.root), \
                patch.object(cli, 'refresh_base', return_value=self.base), \
                patch.object(cli, 'check', side_effect=cli.UserError('check rejected edit')) as check, \
                patch.object(cli, 'network_git') as push:
            with self.assertRaisesRegex(cli.UserError, 'check rejected edit'):
                cli.submit(args)
            check.assert_called_once_with(self.root, self.base)
            push.assert_not_called()

    def test_submit_reuses_existing_pr_after_interrupted_state_save(self):
        git(self.root, 'switch', '-c', 'submission/test')
        (self.root / cli.POLICY).write_text('new table\n')
        git(self.root, 'add', cli.POLICY)
        git(self.root, 'commit', '-m', 'table')
        head = git(self.root, 'rev-parse', 'HEAD')
        cli.write_state(self.root, {'checked': {'base': self.base, 'digest': cli.fingerprint(self.root, self.base)}})
        pr = {'number': 12, 'url': 'https://github.com/example/pull/12', 'headRefOid': head, 'state': 'OPEN'}
        details = {'head': {'sha': head, 'repo': {'full_name': cli.REPO}},
                   'base': {'ref': 'main', 'repo': {'full_name': cli.REPO}}}
        args = argparse.Namespace(watch=False, json=False, timeout=1, title='test')
        with patch.object(cli, 'authenticate'), patch.object(cli, 'repository', return_value=self.root), \
                patch.object(cli, 'refresh_base', return_value=self.base), \
                patch.object(cli, 'gh_json', return_value=[pr]) as github, \
                patch.object(cli, 'api', return_value=details), patch.object(cli, 'network_git'), \
                patch.object(cli, 'watch'), patch.object(cli, 'check') as check:
            cli.submit(args)
            check.assert_not_called()
            self.assertEqual(github.call_count, 1, 'Only PR discovery is needed; no second PR creation')
            self.assertEqual(cli.read_state(self.root)['submission']['pr'], 12)

    def test_two_commands_cannot_reset_the_same_checker_concurrently(self):
        with cli.repository_lock(self.root):
            with self.assertRaisesRegex(cli.UserError, 'Another ForShor command'):
                with cli.repository_lock(self.root):
                    self.fail('A second command entered the checker')


class PublicationIdentity(unittest.TestCase):
    def setUp(self):
        self.submission = {'pr': 12, 'head': 'a' * 40, 'url': 'https://github.com/example/pull/12'}
        self.verifier = {'id': 123, 'run_attempt': 2, 'head_sha': 'a' * 40, 'html_url': 'https://github.com/example/actions/runs/123'}
        self.source = {'run': dict(self.verifier), 'pr': {'number': 12, 'headSha': 'a' * 40}}
        self.publisher = {'id': 456, 'run_attempt': 1, 'conclusion': 'success', 'html_url': 'https://github.com/example/actions/runs/456'}

    def test_receipt_must_match_verifier_attempt_pr_and_commit(self):
        self.assertTrue(cli.publication_matches(self.source, self.submission, self.verifier))
        for section, key, value in [('run', 'id', 999), ('run', 'run_attempt', 1),
                                    ('run', 'head_sha', 'b' * 40), ('pr', 'number', 13),
                                    ('pr', 'headSha', 'b' * 40)]:
            with self.subTest(key=key):
                altered = json.loads(json.dumps(self.source))
                altered[section][key] = value
                self.assertFalse(cli.publication_matches(altered, self.submission, self.verifier))

    def test_unrelated_success_does_not_mean_our_submission_published(self):
        self.source['pr']['number'] = 88
        self.assertIsNone(cli.publication_result(self.publisher, self.source, {'snapshotId': 'c' * 64}, self.submission, self.verifier))

    def test_success_without_a_receipt_is_not_publication(self):
        with self.assertRaisesRegex(cli.UserError, 'without a publication receipt'):
            cli.publication_result(self.publisher, self.source, None, self.submission, self.verifier)

    def test_failed_publication_directs_recovery_to_publisher_not_lean(self):
        self.publisher['conclusion'] = 'failure'
        with self.assertRaisesRegex(cli.UserError, 'rerun its failed job'):
            cli.publication_result(self.publisher, self.source, None, self.submission, self.verifier)

    def test_completed_replay_is_a_success_without_a_new_snapshot(self):
        result = cli.publication_result(self.publisher, self.source, {'alreadyPublished': True}, self.submission, self.verifier)
        self.assertEqual(result['stage'], 'published')
        self.assertTrue(result['alreadyPublished'])

    def test_pr_moved_to_another_head_is_superseded(self):
        with self.assertRaisesRegex(cli.UserError, 'another commit'):
            cli.validate_pr({'head': {'sha': 'b' * 40}}, 'a' * 40)


class ToolchainSetup(unittest.TestCase):
    def test_existing_toolchain_is_reused_and_environment_is_pinned(self):
        with patch.object(cli, 'git', return_value='leanprover/lean4:v4.28.0'), \
                patch.object(cli.shutil, 'which', return_value='/bin/elan'), \
                patch.object(cli, 'run', return_value=SimpleNamespace(stdout='leanprover/lean4:v4.28.0 (default)\n')), \
                patch.object(cli, 'logged') as logged:
            env = cli.lean_environment(Path('/tmp'), 'a' * 40)
            self.assertEqual(env['ELAN_TOOLCHAIN'], 'leanprover/lean4:v4.28.0')
            self.assertEqual(logged.call_count, 1)
            self.assertEqual(logged.call_args.args[2], ['elan', 'run', 'leanprover/lean4:v4.28.0', 'lean', '--version'])

    def test_missing_pinned_version_is_installed_without_changing_default(self):
        with patch.object(cli, 'git', return_value='leanprover/lean4:v4.28.0'), \
                patch.object(cli.shutil, 'which', return_value='/bin/elan'), \
                patch.object(cli, 'run', return_value=SimpleNamespace(stdout='leanprover/lean4:v4.30.0\n')), \
                patch.object(cli, 'logged') as logged:
            cli.lean_environment(Path('/tmp'), 'a' * 40)
            self.assertEqual(logged.call_args_list[0].args[2], ['elan', 'toolchain', 'install', 'leanprover/lean4:v4.28.0'])
            self.assertEqual(logged.call_count, 2)


if __name__ == '__main__':
    unittest.main()
