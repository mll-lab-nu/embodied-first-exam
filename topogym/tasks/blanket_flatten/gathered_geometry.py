"""Continuous longitudinal pleats and whole-bundle torsion for a soft target.

The material width is integrated by arc length. Cross sections remain ordered
because their lateral tangent is positive. Torsion can still stretch material
along the length, so the actual mesh metric and PBD execution must be checked;
these targets never redefine the material rest shape.
"""
import numpy as np


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
