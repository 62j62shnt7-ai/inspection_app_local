import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app


class StartupTests(unittest.TestCase):
    def test_unwritable_data_directory_reports_error_without_traceback(self):
        with patch('sys.argv', ['app.py']), patch.object(Path, 'mkdir', side_effect=PermissionError('Access denied')):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(app.main(), 1)
            self.assertIn('Unable to start', output.getvalue())

    def test_startup_error_survives_legacy_windows_console_encoding(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = io.BytesIO()
            output = io.TextIOWrapper(raw, encoding='ascii')
            with patch('sys.argv', ['app.py', '--data', tmp]), patch('app.data_lock', side_effect=OSError('Access denied: تفتيش')):
                with contextlib.redirect_stdout(output):
                    self.assertEqual(app.main(), 1)
            output.flush()
            self.assertIn(b'Unable to start', raw.getvalue())

    def test_unavailable_default_copy_folder_does_not_prevent_local_app_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'recovery-copies').write_text('Not a folder')
            server=type('Server',(),{'server_port':8766,'serve_forever':lambda self:None,'server_close':lambda self:None})()
            output=io.StringIO()
            with patch('sys.argv',['app.py','--data',tmp]),patch('app.create_server',return_value=server),patch('app.threading.Timer'),contextlib.redirect_stdout(output):
                self.assertEqual(app.main(),0)
            self.assertIn('backup',output.getvalue().lower())
