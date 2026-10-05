"""Stdlib-only contents check for a locally rebuilt helper runtime image."""
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def tree(root):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('missing image assets: ' + str(root))
    # Asset trees may include legitimate package symlinks; hash their resolved bytes.
    values = {str(p.relative_to(root)): sha(p) for p in sorted(root.rglob('*')) if p.is_file()}
    return dict(files=len(values), sha256=digest(values))


def installation_metadata(path):
    # uv_cache.json records the installation timestamp of the local audited wheel.
    # Exclude only installer records inside .dist-info, never same-named code/assets.
    return path.parent.name.endswith('.dist-info') and path.name in ('RECORD', 'direct_url.json', 'uv_cache.json')


def probe(identity_module):
    spec = importlib.util.spec_from_file_location('frozen_identity', identity_module)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    packages = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata['Name'].lower().replace('_', '-')
        if name in packages:
            raise ValueError('duplicate installed Python distribution: ' + name)
        values = {}
        for path in dist.files or []:
            # Bytecode and installer provenance depend on installation time/path.
            # All installed code, native libraries and package resources are hashed.
            if '__pycache__' in path.parts or path.suffix == '.pyc' or installation_metadata(path):
                continue
            target = dist.locate_file(path)
            if target.is_file():
                values[str(path)] = sha(target)
        packages[name] = dict(version=dist.version, files=len(values), sha256=digest(values))
    dpkg = subprocess.check_output(['dpkg-query', '-W', '-f=${db:Status-Status} ${Package}:${Architecture} ${Version}\n'], text=True)
    return dict(schema_version=1, runtime=module.installed_runtime('/opt/topogym'),
                packages=packages, dpkg=sorted(dpkg.splitlines()),
                robots=tree('/opt/topogym-assets/robots'), visuals=tree('/opt/topogym-visuals'))


if __name__ == '__main__':
    print(json.dumps(probe(sys.argv[1]), sort_keys=True))
