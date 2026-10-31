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
        if not {'python.exe', 'python314.dll', 'python314.zip', 'python314._pth'} <= names:
            raise ValueError('Expected the official Python 3.14 x64 embeddable runtime')
        for name in names:
            path = PurePosixPath(name)
            if path.is_absolute() or '..' in path.parts or '\\' in name:
                raise ValueError('Unsafe runtime archive path')
        runtime = output / 'runtime' / 'windows'
        runtime.mkdir(parents=True, exist_ok=True)
        archive.extractall(runtime)
    pth = runtime / 'python314._pth'
    pth.write_text('python314.zip\n.\nLib/site-packages\nimport site\n', encoding='utf-8')
    packages = runtime / 'Lib' / 'site-packages'
    packages.mkdir(parents=True, exist_ok=True)
    vendor = ROOT / 'runtime' / 'mac' / 'lib' / 'python3.14' / 'site-packages'
    for name in ('openpyxl', 'et_xmlfile'):
        shutil.copytree(vendor / name, packages / name, dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('inspection_app', 'static', 'reference'):
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
