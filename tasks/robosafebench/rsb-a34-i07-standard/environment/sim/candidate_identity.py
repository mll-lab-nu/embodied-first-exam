"""Immutable source, installed image and visual identity for new task freezes.

Historical task records have no candidate_identity; they cannot satisfy a new
registry that declares one. This module uses only the standard library and is
copied into the sim sidecar with each task.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

VISUAL_FIELDS = ('asset_profile', 'visual_revision', 'asset_manifest_sha256', 'physics_catalog_version')
KEY_FIELDS = ('family', 'robot', 'member', 'seed', 'evidence', 'cameras', 'interface', 'clock', 'variant', 'movers', 'think_s')
DEFAULTS = {'interface': 'control', 'clock': 'paused', 'movers': 'scripted'}


def valid(identity):
    if not isinstance(identity, dict) or identity.get('schema') != 1:
        return False
    if not re.fullmatch(r'[0-9a-f]{40}', identity.get('source_commit') or ''):
        return False
    if any(not re.fullmatch(r'[0-9a-f]{64}', identity.get(k) or '')
           for k in ('image_id', 'source_digest_sha256')):
        return False
    visual = identity.get('visual_assets')
    return (isinstance(visual, dict) and set(visual) == set(VISUAL_FIELDS)
            and visual.get('asset_profile') == 'realism_v3'
            and isinstance(visual.get('visual_revision'), str) and bool(visual['visual_revision'])
            and re.fullmatch(r'[0-9a-f]{64}', visual.get('asset_manifest_sha256') or '') is not None
            and type(visual.get('physics_catalog_version')) is int and visual['physics_catalog_version'] > 0)


def load(path):
    identity = json.loads(Path(path).read_text())
    if not valid(identity):
        raise ValueError('candidate identity requires full source/image/digest and realism_v3 visual manifest identity')
    return identity


def frozen_fields(value):
    """Read historical public names without rewriting frozen bytes or granting admission."""
    if not isinstance(value, dict):
        return value
    parsed = dict(value)
    for suffix in ('commit', 'version', 'image_id'):
        old, current = 'robosafe_'+suffix, 'robosafebench_'+suffix
        if old in value and current in value and (type(value[old]) is not type(value[current]) or value[old] != value[current]):
            raise ValueError('Conflicting historical/current frozen identity fields: '+suffix)
        if old in value and current not in value:
            parsed[current] = value[old]
    return parsed


def key_identity(key):
    out = {name: key.get(name, DEFAULTS.get(name)) for name in KEY_FIELDS}
    if 'think_s' not in key:
        out['think_s'] = 2.0 if out['clock'] == 'realtime' else None
    return out


def key_admitted(entry, key):
    return key_identity(key) in entry.get('admitted_keys', ())


def native_matches(native, identity):
    return (valid(identity) and native.get('source_commit') == identity['source_commit']
            and native.get('image_id', '').removeprefix('sha256:') == identity['image_id']
            and native.get('visual_assets') == identity['visual_assets']
            and native.get('visual_record_coverage_matches') is True
            and native.get('visual_record_count', 0) > 0
            and native.get('source_overlay') is False and native.get('isolated_python') is True
            and native.get('native_assets_package_only') is True
            and native.get('native_asset_path') == str(Path(native.get('package_path', '')).parent/'assets/data/third_party')
            and native.get('process_environment', {}).get('ROBOSAFE_THIRD_PARTY') is None
            and native.get('process_environment', {}).get('ROBOSAFEBENCH_THIRD_PARTY') == ''
            and native.get('process_environment', {}).get('ROBOSAFEBENCH_ASSET_PROFILE')
                == identity['visual_assets']['asset_profile'])


def assert_runtime(identity):
    """Reject a frozen task before starting physics if the installed assets changed."""
    if not valid(identity):
        raise RuntimeError('Invalid frozen candidate identity')
    import os
    import robosafebench
    from robosafebench.assets.catalog import visual_provenance
    from robosafebench.assets.paths import third_party_dir
    package = Path(robosafebench.__file__).resolve().parent
    if ('ROBOSAFE_THIRD_PARTY' in os.environ or os.environ.get('ROBOSAFEBENCH_THIRD_PARTY')
            or third_party_dir().resolve() != package/'assets/data/third_party'):
        raise RuntimeError('Runtime native assets differ from the image-installed package data')
    if os.environ.get('ROBOSAFEBENCH_ASSET_PROFILE') != identity['visual_assets']['asset_profile']:
        raise RuntimeError('Runtime asset profile differs from the frozen task')
    if visual_provenance() != identity['visual_assets']:
        raise RuntimeError('Runtime visual revision or manifest differs from the frozen task')


def from_receipts(frozen, image):
    """Join two actual receipts; this does not claim task admission."""
    if frozen.get('source_commit') != image.get('source_commit'):
        raise ValueError('Frozen source and actual image commits differ')
    identity = {'schema': 1, 'source_commit': frozen.get('source_commit'),
                'image_id': image.get('image_id', '').removeprefix('sha256:'),
                'source_digest_sha256': frozen.get('tracked_bytes_sha256'),
                'visual_assets': frozen.get('visual_assets')}
    if not valid(identity):
        raise ValueError('Receipts do not contain a complete source/image/digest/visual identity')
    return identity


if __name__ == '__main__':
    import argparse
    import hashlib
    parser = argparse.ArgumentParser(description='Join immutable frozen-source and actual-image receipts; no admission is granted.')
    parser.add_argument('--frozen', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--installed-audit', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    image = json.loads(args.image.read_text())
    audit = json.loads(args.installed_audit.read_text())
    identity = from_receipts(json.loads(args.frozen.read_text()), image)
    if (image.get('frozen_candidate_sha256') != hashlib.sha256(args.frozen.read_bytes()).hexdigest()
            or image.get('source_overlay') is not False
            or audit.get('passed') is not True or audit.get('installed_only') is not True
            or audit.get('native_assets_package_only') is not True
            or audit.get('source_commit') != identity['source_commit']
            or audit.get('image_id', '').removeprefix('sha256:') != identity['image_id']
            or audit.get('source_manifest_sha256') != image.get('source_manifest_sha256')
            or audit.get('visual_assets') != identity['visual_assets']):
        raise SystemExit('Actual installed-image audit does not match these exact frozen-source and image receipts')
    with args.out.open('x') as stream:
        json.dump(identity, stream, indent=2)
        stream.write('\n')
