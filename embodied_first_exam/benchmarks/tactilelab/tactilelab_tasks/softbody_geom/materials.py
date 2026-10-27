"""Named MPM material presets (pure Python, importable on both sides of the Newton bridge).

Fields map onto the per-particle attributes of Newton's ``SolverImplicitMPM`` (``mpm:*``) plus the grain density and the
Coulomb friction of the collider shapes.  Units: SI.

``dough``: a cohesive plastic paste (bread / play dough): von-Mises yield (friction 0, deviatoric ``yield_stress``),
cohesive (tensile cap = compressive cap), stiff elastic core so a press leaves its dent (E = 3e4 springs back by ~30 %).
The MPM paste is compressible by ~30 % under a press, so the success predicates read column tops, not volumes.  The tasks
override ``yield_stress`` per scene (the ridge-pinch scenes use 2500 Pa).
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Union

#: attributes copied to the per-particle ``mpm:*`` arrays of the model (name in the preset == custom attribute name)
PARTICLE_ATTRS = (
    "young_modulus",
    "poisson_ratio",
    "damping",
    "hardening",
    "friction",
    "yield_pressure",
    "tensile_yield_ratio",
    "yield_stress",
    "viscosity",
)

PRESETS: Dict[str, Dict[str, float]] = {
    "dough": {
        "density": 1100.0,
        "young_modulus": 1.0e6,  # stiff elastic core: a press leaves the dent
        "poisson_ratio": 0.45,
        "friction": 0.0,  # pressure-independent (von Mises) yield, like a paste
        "yield_stress": 400.0,  # Pa: flows under a press head, keeps its shape under its own weight (rho g h = 270 Pa)
        "yield_pressure": 1.0e10,  # compressive cap far away
        "tensile_yield_ratio": 1.0,  # cohesive: the lump does not fall apart when pulled
        "hardening": 0.0,
        "viscosity": 0.0,
        "damping": 0.0,
        # contact of the dough with the colliders (plate, tool): Coulomb mu of the collider shapes
        "collider_friction": 0.6,
    },
    # a dry granular material, for tests
    "sand": {
        "density": 1600.0,
        "young_modulus": 1.0e15,
        "poisson_ratio": 0.3,
        "friction": 0.6,
        "yield_stress": 0.0,
        "yield_pressure": 1.0e15,
        "tensile_yield_ratio": 0.0,
        "hardening": 0.0,
        "viscosity": 0.0,
        "damping": 0.0,
        "collider_friction": 0.3,
    },
}


def preset_names() -> list:
    return sorted(PRESETS)


def load_material(spec: Union[str, Mapping[str, Any], None] = "dough") -> Dict[str, Any]:
    """A material as a plain dict of floats.

    ``spec``: a preset name (``"dough"``), or a mapping ``{preset: "dough", <field>: <override>, ...}`` / just overrides
    on top of the dough preset.  Unknown fields are an error (a typo in a config must not silently do nothing)."""
    if spec is None:
        spec = "dough"
    if isinstance(spec, str):
        base_name, overrides = spec, {}
    else:
        overrides = {k: v for k, v in dict(spec).items()}
        base_name = str(overrides.pop("preset", "dough"))
    if base_name not in PRESETS:
        raise KeyError(f"unknown MPM material preset {base_name!r}; have {preset_names()}")
    mat = {k: float(v) for k, v in PRESETS[base_name].items()}
    for k, v in overrides.items():
        if k not in mat:
            raise KeyError(f"unknown MPM material field {k!r}; fields of {base_name!r}: {sorted(mat)}")
        mat[k] = float(v)
    return mat
