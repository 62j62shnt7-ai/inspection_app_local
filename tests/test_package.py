import subprocess
import shutil
from contextlib import contextmanager
from unittest.mock import patch
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

@contextmanager
def synthetic_reference(root):
    from tools import package_windows
    reference = root / 'synthetic-reference'
    reference.mkdir()
    (reference / 'synthetic.txt').write_text('Synthetic package fixture')
    copytree = shutil.copytree
    def copy_with_synthetic_reference(src, dst, *args, **kwargs):
        if Path(src) == package_windows.ROOT / 'reference':
            src = reference
        return copytree(src, dst, *args, **kwargs)
    with patch('tools.package_windows.shutil.copytree', side_effect=copy_with_synthetic_reference):
        yield

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
            with synthetic_reference(root):
                build(root/'runtime.zip',output)
            self.assertEqual((output/'reference'/'synthetic.txt').read_text(), 'Synthetic package fixture')
            self.assertEqual((output/'data'/'inspection_plan.db').read_bytes(), b'keep')
            self.assertIn('import site', (output/'runtime/windows/python314._pth').read_text())
            self.assertTrue((output/'runtime/windows/Lib/site-packages/openpyxl/__init__.py').exists())

    def test_entrypoint_loads_with_isolated_runtime_path(self):
        import openpyxl
        packages = str(Path(openpyxl.__file__).resolve().parent.parent)
        app = Path(__file__).resolve().parents[1] / 'app.py'
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, '-I', '-c',
                 "import runpy,sys; sys.path.append(sys.argv[2]); sys.argv=[sys.argv[1], '--help']; runpy.run_path(sys.argv[0], run_name='__main__')",
                 str(app), packages], cwd=tmp, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Local Master Inspection Plan', result.stdout)

    def test_packages_bundled_python311_runtime_with_importable_app(self):
        from tools.package_windows import build
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with ZipFile(root / 'runtime.zip', 'w') as archive:
                for name in ('python.exe', 'python311.dll', 'python311.zip', 'python311._pth'):
                    archive.writestr(name, b'fixture')
            output = root / 'Inspection app – تفتيش'
            with synthetic_reference(root):
                build(root / 'runtime.zip', output)
            runtime = output / 'runtime' / 'windows'
            paths = [(runtime / line).resolve() for line in (runtime / 'python311._pth').read_text(encoding='utf-8').splitlines()
                     if line and not line.startswith('import ')]
            self.assertTrue(any((path / 'inspection_app' / '__init__.py').is_file() for path in paths))
            self.assertTrue(any((path / 'openpyxl' / '__init__.py').is_file() for path in paths))
