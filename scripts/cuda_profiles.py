"""Explicit CUDA delivery profiles; never infer one from nvidia-smi's CUDA banner."""
import json
import os
from pathlib import Path

PROFILES = ('cu128', 'cu130')


def image_tag(source, profile=None):
    profile = profile or os.environ.get('TOPOGYM_CUDA_FLAVOR', 'cu128')
    if profile not in PROFILES:
        raise ValueError(f'unsupported CUDA profile: {profile}')
    version = (Path(source)/'images/topogym/VERSION').read_text().strip()
    registry = os.environ.get('RCB_IMAGE_REGISTRY', 'ghcr.io/luigivamper')
    return f'{registry}/rcb-topogym:{version}-{profile}'


def build_args(source, profile):
    if profile not in PROFILES:
        raise ValueError(f'unsupported CUDA profile: {profile}')
    suffix = '' if profile == 'cu128' else '-cu130'
    recipe = f'uipc-build{suffix}.json'
    config = json.loads((Path(source)/'images/topogym'/recipe).read_text())
    return dict(UIPC_BUILDER=config['builder_image'], UIPC_CONFIG=recipe,
                RUNTIME_LOCK=f'difficulty-eval-runtime{suffix}.lock', CUDA_FLAVOR=profile)


def check_driver(profile, version):
    if profile == 'cu130' and int(version.split('.')[0]) < 580:
        raise ValueError(f'cu130 requires host NVIDIA driver R580 or newer; found {version}. '
                         'Use cu128 or update the host driver before this experiment.')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--profile', choices=PROFILES, default=os.environ.get('TOPOGYM_CUDA_FLAVOR', 'cu128'))
    args = parser.parse_args()
    print(image_tag(args.source, args.profile))
    for key, value in build_args(args.source, args.profile).items():
        print(f'{key}={value}')
