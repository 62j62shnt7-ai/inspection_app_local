import tempfile
import unittest
from pathlib import Path

class LockTests(unittest.TestCase):
    def test_only_one_process_can_open_data_directory(self):
        from inspection_app.lock import data_lock
        with tempfile.TemporaryDirectory() as tmp:
            with data_lock(Path(tmp)):
                with self.assertRaises(RuntimeError):
                    with data_lock(Path(tmp)): pass
            with data_lock(Path(tmp)): pass
