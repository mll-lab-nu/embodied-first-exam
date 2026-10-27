"""Scene builder of the carrier variant of ``fem_plug_insert`` (pure numpy): the plug hangs from a rigid carrier the gripper holds."""

from __future__ import annotations

from typing import Optional

import numpy as np

from . import dough_metrics as dm
from . import plug_scene as ps
from .dough_task import DoughScene


def plug_spec_from_params(p: dict) -> ps.PlugSpec:
    size = tuple(float(v) for v in p.get("plug_size", (0.018, 0.018, 0.030)))
    interference = float(p.get("interference", 0.0010))
    radius = float(p.get("particle_radius", 0.0005))
    return ps.PlugSpec(
        size=size,
        cell=float(p.get("cell", 0.003)),
        density=float(p.get("density", 1100.0)),
        k_mu=float(p.get("k_mu", 2.0e5)),
        k_lambda=float(p.get("k_lambda", 6.0e5)),
        k_damp=float(p.get("k_damp", 1.0e-3)),
        hole=(
            size[0] - interference + 2 * radius,
            size[1] - interference + 2 * radius,
        ),  # the soft particles' contact radius eats 2 r of the gap: ``interference`` is the real squeeze
        hole_depth=float(p.get("hole_depth", 0.026)),
        wall=float(p.get("wall", 0.012)),
        floor=float(p.get("floor", 0.010)),
        grip_band=float(p.get("grip_band", 0.008)),
        mu=float(p.get("plug_mu", 0.2)),
    )


def make_plug_scene(p: dict, anchor, rng: Optional[np.random.Generator] = None) -> DoughScene:
    """Plug hanging above the hole (anchored frame: hole centre at the origin, hole top face at z = 0)."""
    rng = np.random.default_rng(0) if rng is None else rng
    spec = plug_spec_from_params(p)
    jit = float(p.get("hole_jitter", 0.0))
    off = rng.uniform(-jit, jit, size=2) if jit > 0 else np.zeros(2)
    hover = float(p.get("hover_gap", 0.02))
    pts = ps.plug_particle_grid(spec, (0.0, 0.0), hover)
    cfg = {
        "plug": {
            "size": list(spec.size),
            "cell": spec.cell,
            "density": spec.density,
            "k_mu": spec.k_mu,
            "k_lambda": spec.k_lambda,
            "k_damp": spec.k_damp,
            "hole": list(spec.hole),
            "hole_depth": spec.hole_depth,
            "wall": spec.wall,
            "floor": spec.floor,
            "grip_band": spec.grip_band,
            "mu": spec.mu,
        },  # fmt: skip
        "hole_xy": [0.0, 0.0],
        "top_z": 0.0,
        "fps": int(p.get("fps", 30)),
        "substeps": int(p.get("substeps", 10)),
        "iterations": int(p.get("iterations", 5)),
        "contact_gap": float(p.get("contact_gap", 0.002)),
        "mu_hold": float(p.get("mu_hold", 0.6)),
        "particle_radius": float(
            p.get("particle_radius", 0.0005)
        ),  # contact radius of the soft particles: 2 mm squeezed a 16.5 mm hole to 12.5 mm
    }
    grid = dm.HeightGrid(lo=(-0.05, -0.05), nx=25, ny=25, dx=0.004, z0=0.0)
    return DoughScene(
        kind="plug",
        world_cfg=cfg,
        points=pts,
        pvol=float(np.prod(spec.size) / max(len(pts), 1)),
        anchor=np.asarray(anchor, float),
        grid=grid,
        masks={},
        info={
            "interference": spec.interference,
            "hole_depth": spec.hole_depth,
            "hole_x": float(off[0]),
            "hole_y": float(off[1]),
        },
        extra={"spec": spec},
    )
