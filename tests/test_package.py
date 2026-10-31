import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

class PackageTests(unittest.TestCase):
    def test_rejects_incomplete_windows_runtime(self):
        from tools.package_windows import build
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with ZipFile(root/'runtime.zip','w') as z: z.writestr('python.exe',b'fake')
            with self.assertRaises(ValueError): build(root/'runtime.zip',root/'output')
            self.assertFalse((root/'output'/'runtime'/'windows'/'python.exe').exists())

    def test_package_preserves_existing_data(self):
        from tools.package_windows import build
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with ZipFile(root/'runtime.zip','w') as z:
                z.writestr('python.exe', b'fake')
                z.writestr('python314.dll', b'fake')
                z.writestr('python314.zip', b'fake')
                z.writestr('python314._pth', 'python314.zip\n.\n# import site\n')
            output=root/'output'
            (output/'data').mkdir(parents=True)
            (output/'data'/'inspection_plan.db').write_bytes(b'keep')
            build(root/'runtime.zip',output)
            self.assertEqual((output/'data'/'inspection_plan.db').read_bytes(), b'keep')
            self.assertIn('import site', (output/'runtime/windows/python314._pth').read_text())
            self.assertTrue((output/'runtime/windows/Lib/site-packages/openpyxl/__init__.py').exists())
