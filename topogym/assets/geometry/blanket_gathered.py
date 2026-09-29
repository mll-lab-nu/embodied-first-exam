"""Continuous longitudinal pleats and whole-bundle torsion for a soft target.

The material width is integrated by arc length. Cross sections remain ordered
because their lateral tangent is positive. Torsion can still stretch material
along the length, so the actual mesh metric and PBD execution must be checked;
these targets never redefine the material rest shape.
"""
import numpy as np
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class GatheredProfile:
    """Candidate targets; released shape and difficulty require qualification."""
    panel_fractions: tuple = (.10, .14, .11, .16, .12, .09, .14, .14)
    crease_band_m: float = .012
    pleat_angle_deg: float = 72.
    end_opening_deg: float = 10.
    flare_fraction: float = .15
    twist_angle_deg: float = 0.
    axial_scale: float = .92
    centerline_sway_m: float = .006
    placement_roll_deg: float = 0.

    def __post_init__(self):
        values = [v for k, v in asdict(self).items() if k != "panel_fractions"]
        if not np.isfinite(values).all() or not 0 < self.axial_scale <= 1:
            raise ValueError("Invalid gathered profile")
        if min(self.crease_band_m, self.flare_fraction) <= 0 or not 0 < self.pleat_angle_deg < 90:
            raise ValueError("Invalid crease band or pleat angle")
        if not 0 <= self.end_opening_deg <= self.pleat_angle_deg or not 0 <= self.twist_angle_deg <= 360:
            raise ValueError("Invalid opening or twist angle")
        if not 0 <= self.placement_roll_deg <= 180:
            raise ValueError("Invalid placement roll")
        if len(self.panel_fractions) < 2 or min(self.panel_fractions) <= 0 or not np.isclose(sum(self.panel_fractions), 1):
            raise ValueError("Panel fractions must be positive and sum to one")


def preparation_target(uv, length, width, gather, twist, profile):
    """Use equal final axial compression for all twist-angle candidates."""
    result = gathered_target(uv, length, width, gather, twist, profile)
    result[:, 0] = uv[:, 0]*(1+(profile.axial_scale-1)*gather)
    angle = np.radians(profile.placement_roll_deg)*gather
    y, z = result[:, 1].copy(), result[:, 2].copy()
    result[:, 1] = np.cos(angle)*y-np.sin(angle)*z
    result[:, 2] = np.sin(angle)*y+np.cos(angle)*z
    return result


def gathered_target(uv, length, width, gather, twist, cfg):
    fractions = np.asarray(cfg.panel_fractions, dtype=float)
    if (fractions <= 0).any() or not np.isclose(fractions.sum(), 1.):
        raise ValueError('Positive panel fractions must sum to one')
    if not 0 <= gather <= 1 or not 0 <= twist <= 1:
        raise ValueError('Preparation fractions must lie in [0, 1]')
    # A regular material grid makes the target independent of remeshing order.
    xs = np.linspace(-length/2, length/2, 121)
    ys = np.linspace(-width/2, width/2, 1201)
    creases = width*(np.cumsum(fractions)[:-1]-.5)
    half_band = float(cfg.crease_band_m)/2
    wave = np.ones_like(ys)
    for i, crease in enumerate(creases):
        t = np.clip((ys-crease+half_band)/(2*half_band), 0., 1.)
        t = t*t*(3-2*t)
        wave += 2*(-1.)**(i+1)*t
    s = xs/length+.5
    flare = np.exp(-(s/float(cfg.flare_fraction))**2)+np.exp(-((1-s)/float(cfg.flare_fraction))**2)
    amplitude = np.radians(float(cfg.pleat_angle_deg)-float(cfg.end_opening_deg)*flare)*gather
    phi = amplitude[:, None]*wave
    dy, dz = np.cos(phi), np.sin(phi)
    step = ys[1]-ys[0]
    lateral = np.c_[np.zeros(len(xs)), np.cumsum((dy[:, 1:]+dy[:, :-1])*(step/2), axis=1)]
    vertical = np.c_[np.zeros(len(xs)), np.cumsum((dz[:, 1:]+dz[:, :-1])*(step/2), axis=1)]
    lateral -= lateral.mean(axis=1, keepdims=True)
    vertical -= vertical.mean(axis=1, keepdims=True)
    # End sections rotate less rapidly; more of the turn occurs in the waist.
    phase = s*s*(3-2*s)-.5
    angle = np.radians(float(cfg.twist_angle_deg))*twist*phase
    y = np.cos(angle[:, None])*lateral-np.sin(angle[:, None])*vertical
    z = np.sin(angle[:, None])*lateral+np.cos(angle[:, None])*vertical
    y += float(cfg.centerline_sway_m)*gather*np.sin(2*np.pi*s)[:, None]
    scale = 1+(float(cfg.axial_scale)-1)*twist
    # Bilinear interpolation from the same material coordinates at every stage.
    from scipy.ndimage import map_coordinates
    coords = np.array([(uv[:, 0]/length+.5)*(len(xs)-1),
                       (uv[:, 1]/width+.5)*(len(ys)-1)])
    return np.column_stack((uv[:, 0]*scale,
        map_coordinates(y, coords, order=1, mode='nearest'),
        map_coordinates(z, coords, order=1, mode='nearest')))
