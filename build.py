"""From an x86 MSVC prompt: python build.py Lords-of-Shadow-AP-0.7.6.zip

Python 3.10+. Reuses game assets/YAML from that release. --apworld-only skips MSVC.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent
RELEASE_SHA256 = '6982d5f5d7ccd4e336c8db6086ba067d1cc05e24df48b825081b40f10fbd0b5a'


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(name, data)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('release', type=Path)
    parser.add_argument('--apworld-only', action='store_true')
    args = parser.parse_args()
    payload = args.release.read_bytes()
    if hashlib.sha256(payload).hexdigest() != RELEASE_SHA256:
        parser.error('Use the matching 0.7.6 release ZIP.')
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    with zipfile.ZipFile(io.BytesIO(files['Archipelago/los.apworld'])) as archive:
        world = {name: archive.read(name) for name in archive.namelist()
                 if Path(name).suffix not in {'.py', '.lua', '.json'}}
    for path in sorted((ROOT / 'apworld').rglob('*')):
        if path.is_file() and path.suffix in {'.py', '.lua', '.json'}:
            world[path.relative_to(ROOT / 'apworld').as_posix()] = path.read_bytes()
    files['Archipelago/los.apworld'] = zip_bytes(world)
    out = ROOT / 'dist'
    (out / 'Archipelago').mkdir(parents=True, exist_ok=True)
    (out / 'Archipelago/los.apworld').write_bytes(files['Archipelago/los.apworld'])
    if args.apworld_only:
        print(out / 'Archipelago/los.apworld')
        return
    compiler = shutil.which('cl')
    if not compiler:
        parser.error('Run from an x86 MSVC developer prompt, or use --apworld-only.')
    native = ROOT / 'native'
    build = out / 'build'
    build.mkdir(exist_ok=True)
    subprocess.run([
        compiler, '/nologo', '/std:c++17', '/EHsc', '/O2', '/MT', '/LD',
        '/DUNICODE', '/D_UNICODE', str(native / 'dinput8_proxy.cpp'), 'user32.lib',
        '/link', '/MACHINE:X86', '/INCREMENTAL:NO',
        '/DEF:' + str(native / 'dinput8_proxy.def'), '/OUT:dinput8.dll',
    ], cwd=build, check=True)
    files['Game Folder/bin/dinput8.dll'] = (build / 'dinput8.dll').read_bytes()
    for name in ('enemy_early.lua', 'enemy_floor.lua', 'enemy_loader.lua', 'enemy_runtime.lua'):
        files['Game Folder/bin/APEnemy/' + name] = world['los/client/' + name]
    for name, data in files.items():
        path = out / name
        if not path.resolve().is_relative_to(out.resolve()):
            raise ValueError(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    version = json.loads(world['los/archipelago.json'])['world_version']
    target = out / f'Lords-of-Shadow-AP-{version}.zip'
    target.write_bytes(zip_bytes(files))
    print(target)


if __name__ == '__main__':
    main()
