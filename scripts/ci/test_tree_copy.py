import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('policy_tree_copy', Path(__file__).parents[1] / 'tree_copy.py')
tree_copy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tree_copy)


class IsolatedTreeTests(unittest.TestCase):
    def test_source_and_build_writes_are_isolated_but_dependencies_are_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            source, dest = Path(directory) / 'source', Path(directory) / 'copy'
            (source / '.lake/packages/mathlib').mkdir(parents=True)
            (source / '.lake/build').mkdir()
            (source / 'Policy.lean').write_text('trusted source')
            (source / '.lake/build/Policy.olean').write_text('trusted build')
            (source / '.lake/packages/mathlib/Basic.olean').write_text('dependency')
            with patch.object(tree_copy.sys, 'platform', 'linux'):
                tree_copy.copy_lean_tree(source, dest)
            (dest / 'Policy.lean').write_text('submitted source')
            (dest / '.lake/build/Policy.olean').write_text('submitted build')
            self.assertEqual((source / 'Policy.lean').read_text(), 'trusted source')
            self.assertEqual((source / '.lake/build/Policy.olean').read_text(), 'trusted build')
            self.assertTrue((dest / '.lake/packages').is_symlink())
            self.assertEqual((dest / '.lake/packages/mathlib/Basic.olean').read_text(), 'dependency')

    def test_a_recursive_clone_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                tree_copy.copy_lean_tree(Path(directory), Path(directory) / 'copy')
