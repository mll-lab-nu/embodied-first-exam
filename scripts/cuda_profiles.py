"""Explicit CUDA delivery profiles; never infer one from nvidia-smi's CUDA banner."""
import json
from pathlib import Path

PROFILES = ('cu128', 'cu130')


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
