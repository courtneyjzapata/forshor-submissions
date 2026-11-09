import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('policy_memcap', Path(__file__).parents[1] / 'memcap.py')
memcap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(memcap)


class LinuxMemoryTests(unittest.TestCase):
    def test_cap_counts_resident_and_swapped_pages(self):
        status = 'Name:\tlean\nVmRSS:\t1024 kB\nVmSwap:\t512 kB\n'
        with patch.object(memcap.sys, 'platform', 'linux'), patch.object(Path, 'read_text', return_value=status):
            self.assertEqual(memcap.mem(123), 1536 * 1024)

    def test_a_process_exiting_between_polls_is_not_an_error(self):
        with patch.object(memcap.sys, 'platform', 'linux'), patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            self.assertEqual(memcap.mem(123), 0)
