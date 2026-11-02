import subprocess
import unittest
from unittest.mock import patch
from inspection_app.folder_picker import choose_folder


class FolderPickerTests(unittest.TestCase):
    @patch('inspection_app.folder_picker.subprocess.run')
    def test_windows_selected_folder_and_cancel(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, 'C:\\Backups\n', '')
        self.assertEqual(choose_folder('win32'), 'C:\\Backups')
        self.assertIn('-STA', run.call_args.args[0])
        run.return_value = subprocess.CompletedProcess([], 0, '', '')
        self.assertIsNone(choose_folder('win32'))

    @patch('inspection_app.folder_picker.subprocess.run')
    def test_macos_cancel(self, run):
        run.return_value = subprocess.CompletedProcess([], 1, '', 'User canceled. (-128)')
        self.assertIsNone(choose_folder('darwin'))

    @patch('inspection_app.folder_picker.subprocess.run')
    def test_picker_failure_has_actionable_error(self, run):
        run.side_effect = FileNotFoundError()
        with self.assertRaisesRegex(ValueError, 'folder chooser'):
            choose_folder('win32')
