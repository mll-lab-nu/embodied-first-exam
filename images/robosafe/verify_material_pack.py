"""Verify a downloaded/local immutable v3 pack and install into an absent path.

This chooses no download host. Both independent SHA256 pins are required.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import tarfile


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def install(pack, manifest, destination, pack_sha256, manifest_sha256):
    if sha(pack) != pack_sha256 or sha(manifest) != manifest_sha256:
        raise ValueError('Asset pack or manifest SHA256 differs')
    expected = json.loads(manifest.read_text())
    if not expected or destination.exists() or destination.is_symlink():
        raise ValueError('Manifest must be nonempty and destination must be absent')
    for relative, row in expected.items():
        name = PurePosixPath(relative)
        if (name.is_absolute() or '..' in name.parts or str(name) != relative
                or row.get('kind') != 'file' or not isinstance(row.get('bytes'), int)
                or row['bytes'] < 0 or len(row.get('sha256', '')) != 64):
            raise ValueError('Unexpected asset manifest entry: ' + relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix='.rsb-v3-', dir=str(destination.parent)))
    try:
        seen = set()
        with tarfile.open(str(pack), 'r') as archive:
            for item in archive:
                if (not item.isfile() or item.name not in expected or item.name in seen
                        or item.size != expected[item.name]['bytes']):
                    raise ValueError('Unexpected, duplicate or non-file tar member: ' + item.name)
                seen.add(item.name)
                target = staged / item.name
                target.parent.mkdir(parents=True, exist_ok=True)
                value = hashlib.sha256()
                with archive.extractfile(item) as source, target.open('xb') as output:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        value.update(block)
                        output.write(block)
                if value.hexdigest() != expected[item.name]['sha256']:
                    raise ValueError('Asset member bytes differ: ' + item.name)
        if seen != set(expected) or destination.exists() or destination.is_symlink():
            raise ValueError('Incomplete pack or destination appeared during verification')
        staged.rename(destination)
    finally:
        if staged.exists():
            shutil.rmtree(str(staged))
    return {'verified': True, 'pack_sha256': pack_sha256,
            'manifest_sha256': manifest_sha256, 'files': len(expected),
            'bytes': sum(row['bytes'] for row in expected.values()),
            'destination': str(destination), 'public_host_selected': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pack', type=Path)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--pack-sha256', required=True)
    parser.add_argument('--manifest-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.pack, args.manifest, args.destination,
                             args.pack_sha256, args.manifest_sha256)))
