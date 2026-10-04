"""Portable runtime identity checks, shared by task tooling and private launchers.

Only the standard library is used. The private bridge copies this exact module
so it can also check immutable older images which do not contain this module.
Creation provenance is never rewritten or used as a runtime compatibility test.
"""
from __future__ import annotations

import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys


class BindingMismatch(ValueError):
    pass


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def file_hash(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda: stream.read(1024*1024), b''):
            value.update(data)
    return value.hexdigest()


def tree_hashes(root):
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise BindingMismatch(f'Bound file tree must be an existing directory: {root}')
    values = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink():
            raise BindingMismatch(f'Symlink in bound files: {path}')
        if path.is_file():
            values[path.relative_to(root).as_posix()] = file_hash(path)
    return values


def installed_runtime(root=None, *, check_imports=True):
    """Rehash actual files; SOURCE.json alone is not evidence of loaded code.

    Hash serialization matches images/topogym/prune.py, including its spaces.
    Private planning helpers may be imported outside the installed public tree.
    """
    if root is None:
        import topogym
        root = Path(topogym.__file__).resolve().parents[1]
    root = Path(root).resolve()
    recorded = root/'SOURCE.json'
    if not recorded.is_file():
        raise BindingMismatch(f'No installed simulator SOURCE.json at {root}; a checkout is not a bound image')
    files = {'topogym/'+name: value for name, value in tree_hashes(root/'topogym').items()}
    source = dict(sha256=hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), files=len(files))
    if source != json.loads(recorded.read_text()):
        raise BindingMismatch('Installed simulator files differ from SOURCE.json')
    if check_imports:
        for name, module in tuple(sys.modules.items()):
            if name != 'topogym' and not name.startswith('topogym.'):
                continue
            if name == 'topogym.planning' or name.startswith('topogym.planning.'):
                continue
            path = getattr(module, '__file__', None)
            if path and not Path(path).resolve().is_relative_to(root/'topogym'):
                raise BindingMismatch(f'Public simulator module loaded outside the bound image: {name}: {path}')
    dependencies = {}
    for name in ('genesis-world', 'pyuipc', 'torch', 'numpy', 'scipy'):
        try:
            dependencies[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies[name] = None
    build = Path('/opt/uipc-build.json')
    return dict(source=source, python=sys.version.split()[0], dependencies=dependencies,
                uipc_build_sha256=file_hash(build) if build.is_file() else None)


def validate_lock(lock):
    required = {'schema_version','instance_sha256','asset_files','tooling_sha256','runtime','image','creation_source'}
    if not isinstance(lock, dict) or not required <= lock.keys() or lock['schema_version'] != 1:
        raise BindingMismatch('Incomplete runtime binding')
    for key in ('instance_sha256','tooling_sha256'):
        if not isinstance(lock[key], str) or re.fullmatch(r'[0-9a-f]{64}', lock[key]) is None:
            raise BindingMismatch(f'Invalid binding {key}')
    for image in [lock['image']] + ([lock['agent_image']] if 'agent_image' in lock else []):
        if (not isinstance(image, dict) or re.fullmatch(r'sha256:[0-9a-f]{64}', str(image.get('id',''))) is None
                or not image.get('reference')):
            raise BindingMismatch('Runtime binding needs a resolved Docker image identity')
    if not isinstance(lock['runtime'], dict) or not lock['runtime'].get('source'):
        raise BindingMismatch('Runtime binding lacks installed simulator identity')
    source = lock['runtime']['source']
    if (not isinstance(source, dict) or re.fullmatch(r'[0-9a-f]{64}', str(source.get('sha256',''))) is None
            or type(source.get('files')) is not int or source['files'] < 1):
        raise BindingMismatch('Runtime source identity is malformed')
    if not isinstance(lock['asset_files'], dict) or not isinstance(lock['creation_source'], dict):
        raise BindingMismatch('Runtime binding lacks asset or creation identity')
    return lock


def check_inputs(instance_path, tooling_path, lock):
    validate_lock(lock)
    instance_path = Path(instance_path)
    instance = json.loads(instance_path.read_text())
    if canonical_hash(instance) != lock['instance_sha256']:
        raise BindingMismatch('Instance JSON differs from the runtime binding')
    if instance.get('topogym_source') != lock['creation_source']:
        raise BindingMismatch('Instance creation provenance changed')
    assets = {'instance_assets/'+k:v for k,v in tree_hashes(instance_path.parent/'instance_assets').items()}
    if assets != lock['asset_files']:
        raise BindingMismatch('Frozen instance assets differ from the runtime binding')
    if file_hash(tooling_path) != lock['tooling_sha256']:
        raise BindingMismatch('Loaded task tooling differs from the runtime binding')
    return instance


def check_runtime(lock, *, root=None):
    validate_lock(lock)
    actual = installed_runtime(root)
    if actual != lock['runtime']:
        raise BindingMismatch('Actual installed source/dependencies differ from the bound runtime')
    return actual


def binding_id(lock):
    validate_lock(lock)
    return canonical_hash(lock)
