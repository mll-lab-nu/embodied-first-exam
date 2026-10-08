#!/usr/bin/env python3
"""Build-only CMake fix, the hash-checked determinism source patches, CUDA wheel audit and hash-checked runtime install."""
import argparse
import email
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def materials(source, config):
    for name, expected in config['material_sha256'].items():
        if sha(source / name) != expected:
            raise ValueError(f'original material implementation changed: {name}')


def patched(source, config):
    for name, expected in config.get('patched_sha256', {}).items():
        if not (source / name).is_file() or sha(source / name) != expected:
            raise ValueError(f'patched IPC source differs: {name}')


def apply_patches(source, config):
    # TopoGym determinism series (uipc-build.json source_patches): fixed-order sums instead of float atomics in the
    # linear solve, assembly, candidate lists and segmented reductions; physics and materials unchanged.
    for item in config.get('source_patches', []):
        patch = Path('/recipe') / item['path']
        if sha(patch) != item['sha256']:
            raise ValueError(f'IPC source patch hash mismatch: {item["path"]}')
        subprocess.run(['git', '-C', str(source), 'apply', '--whitespace=nowarn', str(patch)], check=True)
    patched(source, config)


def prepare(source, config):
    materials(source, config)
    path = source / 'src/backends/cuda/CMakeLists.txt'
    if sha(path) != config['cmake_before_sha256']:
        raise ValueError('unexpected original CUDA CMake file')
    old = '    CUDA_ARCHITECTURES ${UIPC_CUDA_ARCHITECTURES}\n'
    text = path.read_text()
    if text.count(old) != 1:
        raise ValueError('expected exactly one CUDA target property')
    # A list must remain one property value. Materials stay original; the only solver source changes are the hash-checked
    # determinism patches (summation order).
    path.write_text(text.replace(old, '    CUDA_ARCHITECTURES "${UIPC_CUDA_ARCHITECTURES}"\n'))
    apply_patches(source, config)


def audit(folder, config, source):
    materials(source, config)
    head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    if head != config['source_commit']:
        raise ValueError('IPC source commit changed')
    changed = subprocess.check_output(['git', '-C', str(source), 'diff', '--name-only'], text=True).splitlines()
    tracked = set(subprocess.check_output(['git', '-C', str(source), 'ls-files'], text=True).splitlines())
    patched_files = config.get('patched_sha256', {})
    expected = sorted(['src/backends/cuda/CMakeLists.txt', *(f for f in patched_files if f in tracked)])
    if sorted(changed) != expected:
        raise ValueError(f'unexpected upstream source changes: {changed}')
    patched(source, config)
    wheels = list(folder.glob('*.whl'))
    if len(wheels) != 1:
        raise ValueError('expected one repaired CPython 3.11 wheel')
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive, tempfile.TemporaryDirectory() as tmp:
        metadata = [p for p in archive.namelist() if p.endswith('.dist-info/METADATA')]
        package = email.message_from_bytes(archive.read(metadata[0]))
        if package['Version'] != config['version']:
            raise ValueError('unexpected wheel version')
        libraries = [p for p in archive.namelist() if p.endswith('/libuipc_backend_cuda.so')]
        if len(libraries) != 1:
            raise ValueError('missing/ambiguous IPC CUDA backend')
        library = Path(tmp) / 'libuipc_backend_cuda.so'
        library.write_bytes(archive.read(libraries[0]))
        elf = subprocess.check_output(['cuobjdump', '--list-elf', str(library)], text=True)
        # RDC builds retain PTX in relocatable fatbins, beside linked SASS.
        ptx = subprocess.check_output(['cuobjdump', '--all-fatbin', '--list-ptx', str(library)], text=True)
        sass = sorted(set(re.findall(r'\bsm_\d+\b', elf)))
        if not set(config['required_sass']) <= set(sass):
            raise ValueError(f'wheel lacks required native CUDA kernels: {sass}')
        # The PTX each `<N>-virtual` architecture of the config embeds (the release config's 120-virtual: compute_120).
        for arch in re.findall(r'(\d+)-virtual', config['architectures']) or ['120']:
            if not re.search(rf'(?:sm|compute)_{arch}\b', ptx):
                raise ValueError(f'wheel lacks compute-{arch} PTX')
        record = dict(config, wheel=wheel.name, wheel_sha256=sha(wheel), backend_sha256=sha(library),
                      backend_path=libraries[0], sass=sass, ptx_listing=ptx.splitlines(),
                      ptx_scope='all_fatbins_including_relocatable',
                      cuda_compiler=subprocess.check_output(['nvcc', '--version'], text=True),
                      submodules=subprocess.check_output(['git', '-C', str(source), 'submodule', 'status', '--recursive'], text=True),
                      cmake_after_sha256=sha(source/'src/backends/cuda/CMakeLists.txt'),
                      source_changes=changed, source_added=sorted(f for f in patched_files if f not in tracked),
                      materials_unchanged=True)
    (folder / 'uipc-build.json').write_text(json.dumps(record, indent=2) + '\n')


def without_pyuipc(text):
    lines = text.splitlines(keepends=True)
    out, found, i = [], 0, 0
    while i < len(lines):
        if lines[i].startswith('pyuipc=='):
            if not lines[i].startswith('pyuipc==0.0.25 '):
                raise ValueError('unexpected baseline IPC requirement')
            found += 1
            while lines[i].rstrip().endswith('\\'):
                i += 1
            i += 1
        else:
            out.append(lines[i]); i += 1
    if found != 1:
        raise ValueError('expected exactly one original IPC requirement')
    return ''.join(out)


def dependencies(lock):
    with tempfile.TemporaryDirectory() as tmp:
        requirements = Path(tmp) / 'runtime.lock'
        requirements.write_text(without_pyuipc(lock.read_text()))
        subprocess.run(['uv', 'pip', 'install', '--system', '--require-hashes', '--torch-backend',
                        os.environ.get('TOPOGYM_CUDA_FLAVOR', 'cu128'),
                        '-r', str(requirements)], check=True)


def install(folder, lock=None):
    record = json.loads((folder / 'uipc-build.json').read_text())
    wheel = folder / record['wheel']
    if wheel.parent != folder or sha(wheel) != record['wheel_sha256']:
        raise ValueError('IPC wheel hash mismatch')
    with tempfile.TemporaryDirectory() as tmp:
        requirements = Path(tmp) / 'wheel.lock'
        requirements.write_text(f'pyuipc @ {wheel.resolve().as_uri()} --hash=sha256:{record["wheel_sha256"]}\n')
        subprocess.run(['uv', 'pip', 'install', '--system', '--no-deps', '--require-hashes',
                        '-r', str(requirements)], check=True)
    import importlib.metadata as metadata
    package = metadata.distribution('pyuipc')
    if package.version != record['version'] or sha(package.locate_file(record['backend_path'])) != record['backend_sha256']:
        raise ValueError('installed IPC differs from audited build')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('prepare', 'audit', 'install', 'dependencies'))
    parser.add_argument('path', type=Path)
    parser.add_argument('config_or_lock', type=Path, nargs='?')
    parser.add_argument('source', type=Path, nargs='?')
    args = parser.parse_args()
    if args.operation == 'dependencies':
        dependencies(args.path)
    elif args.operation == 'install':
        install(args.path, args.config_or_lock)
    else:
        config = json.loads(args.config_or_lock.read_text())
        if args.operation == 'prepare': prepare(args.path, config)
        else: audit(args.path, config, args.source)
