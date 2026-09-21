"""Fixed family templates and a small, explicit appearance configuration."""
from pathlib import Path

import numpy as np
from omegaconf import OmegaConf, open_dict

from .geometry import FAMILY_KNOTS


ROOT = Path(__file__).resolve().parents[3]
VARIANTS = {'overhand_trefoil': 'trefoil_open_v1',
            'figure_eight': 'figure_eight_open_v1',
            'double_overhand': 'double_overhand_open_v1'}
ROUTE_PROFILES = {
    'figure8_pitched_regrasp_v6': ('figure_eight', 'figure_eight_local_support_v2'),
    'double_overhand_pitched_regrasp_v8': ('double_overhand', 'double_overhand_open_v1'),
    'double_overhand_support_shift_checked_v7': ('double_overhand', 'double_overhand_open_v1'),
    'figure8_support_spread_checked_v5': ('figure_eight', 'figure_eight_local_support_v2'),
    'double_overhand_anchored_tracking_v6': ('double_overhand', 'double_overhand_open_v1'),
    'double_overhand_anchored_clearance_v5': ('double_overhand', 'double_overhand_open_v1'),
    'double_overhand_anchored_adaptive_v4': ('double_overhand', 'double_overhand_open_v1'),
    'double_overhand_anchored_open_v3': ('double_overhand', 'double_overhand_open_v1'),
    'double_overhand_narrow_v2': ('double_overhand', 'double_overhand_open_v1'),
    'figure8_local_curve_v2': ('figure_eight', 'figure_eight_local_support_v2'),
    'figure8_local_curve_narrow_v3': ('figure_eight', 'figure_eight_local_support_v2'),
    'figure8_local_curve_tracking_v4': ('figure_eight', 'figure_eight_local_support_v2'),
}
PALETTE = {'orange': [0.86, 0.43, 0.12], 'blue': [0.12, 0.38, 0.72],
           'teal': [0.10, 0.58, 0.48]}


def template_variant(family, route_profile=None):
    if route_profile is None:
        return VARIANTS[family]
    if route_profile not in ROUTE_PROFILES or ROUTE_PROFILES[route_profile][0] != family:
        raise ValueError(f'Route profile {route_profile!r} is not registered for {family}')
    return ROUTE_PROFILES[route_profile][1]


def template_config(family, route_profile=None):
    template_variant(family, route_profile)
    folder = ROOT/'configs/task_variants/knot_untying'
    template = OmegaConf.load(folder/f'{family}.yaml')
    if route_profile is not None:
        template = OmegaConf.merge(template, OmegaConf.load(folder/'profiles'/f'{route_profile}.yaml'))
    return template


def apply_family(cfg, family='overhand_trefoil', *, appearance_seed=None, route_profile=None):
    """Apply an authored template; random appearance is optional and reproducible.

    Scale and yaw change geometry/robot placement and require fresh execution
    checks. A palette change affects only rendering. No rope material sampling.
    """
    if family not in FAMILY_KNOTS:
        raise ValueError(f'Unknown knot family: {family}')
    template = template_config(family, route_profile)
    with open_dict(cfg.task):
        # Switching templates must not retain an earlier family's action
        # overrides or the seed label of an earlier randomized instance.
        for name in ('route_profile', 'route_settings', 'appearance'):
            if name in cfg.task:
                del cfg.task[name]
        cfg.task.merge_with(template.task)
    if appearance_seed is not None:
        rng = np.random.default_rng(appearance_seed)
        with open_dict(cfg.task):
            cfg.task.appearance = dict(shape_scale=float(rng.uniform(.95, 1.05)),
                                       yaw_deg=float(rng.uniform(-4., 4.)),
                                       rope_color=list(PALETTE)[int(rng.integers(len(PALETTE)))],
                                       seed=int(appearance_seed))
    appearance = cfg.task.appearance
    scale, yaw = float(appearance.shape_scale), float(appearance.yaw_deg)
    if not np.isfinite([scale, yaw]).all() or not .95 <= scale <= 1.05 or abs(yaw) > 4:
        raise ValueError('Candidate appearance range: scale [0.95,1.05], yaw [-4,4] degrees')
    color = str(appearance.rope_color)
    if color not in PALETTE:
        raise ValueError(f'Unknown rope color: {color}')
    for name in ('planar_scale_m', 'crossing_height_m', 'tail_length_m'):
        cfg.task.geometry[name] *= scale
    with open_dict(cfg.task):
        cfg.task.family_id = family
        cfg.task.yaw_deg = float(cfg.task.reference_yaw_deg)+yaw
        cfg.task.rope_color_rgb = PALETTE[color]
    return cfg
