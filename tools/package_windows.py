"""Build a portable Windows folder from an official embeddable runtime ZIP."""
import argparse
from pathlib import Path, PurePosixPath
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parent.parent

def build(runtime_zip, output):
    output = Path(output)
    with ZipFile(runtime_zip) as archive:
        names = set(archive.namelist())
        versions = [version for version in ('311', '314')
                    if {'python.exe', f'python{version}.dll', f'python{version}.zip', f'python{version}._pth'} <= names]
        if len(versions) != 1:
            raise ValueError('Expected an official Python 3.11 or 3.14 x64 embeddable runtime')
        version = versions[0]
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Unsafe runtime archive path')
        runtime = output / 'runtime' / 'windows'
        runtime.mkdir(parents=True, exist_ok=True)
        archive.extractall(runtime)
    pth = runtime / f'python{version}._pth'
    pth.write_text(f'python{version}.zip\n.\n../..\nLib/site-packages\nimport site\n', encoding='utf-8')
    packages = runtime / 'Lib' / 'site-packages'
    packages.mkdir(parents=True, exist_ok=True)
    vendors = [ROOT / 'runtime/mac/lib/python3.14/site-packages',
               ROOT / 'runtime/windows/Lib/site-packages', ROOT / 'runtime/windows/site-packages']
    vendor = next((path for path in vendors if all((path / name).is_dir() for name in ('openpyxl', 'et_xmlfile'))), None)
    if vendor is None:
        raise ValueError('Bundled openpyxl and et_xmlfile packages are missing')
    for name in ('openpyxl', 'et_xmlfile'):
        shutil.copytree(vendor / name, packages / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('inspection_app', 'static', 'reference', 'tests', 'tools'):
        shutil.copytree(ROOT / name, output / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
    for name in ('app.py', 'Start Inspection App.bat', 'README.md'):
        if (ROOT / name).exists(): shutil.copy2(ROOT / name, output / name)
    (output / 'data').mkdir(exist_ok=True)
    return output

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime-zip', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    build(args.runtime_zip, args.output)
