"""Capsule-chain rope model parameters (shared by the asset builder and the task cfg).

Old rope (RoboTangle knot_untying): 8 mm diameter, FEM stable neo-Hookean E 50 kPa, nu 0.3,
rho 650 kg/m3, mu 0.3. Port: one PhysX articulation of N capsules (r 4 mm, ~10 mm long), spherical
joints with implicit PD drives towards the straight rest shape.

Bend stiffness per joint k_b = E*I/d with I = pi r^4 / 4  -> 1.0e-3 N m/rad at d = 10 mm.
Twist stiffness per joint k_t = G*J/d with G = E/(2(1+nu)), J = pi r^4 / 2 -> 7.7e-4 N m/rad.
Mass per link = rho * pi r^2 * d (0.33 g at d = 10 mm; whole very_easy rope 32 g).
"""
import math

E, NU, RHO, MU = 50e3, 0.3, 650.0, 0.3
RADIUS = 0.004
LINK_LENGTH_NOMINAL = 0.010


def bend_stiffness(d):
    return E * math.pi * RADIUS ** 4 / 4.0 / d


def twist_stiffness(d):
    G = E / (2 * (1 + NU))
    return G * math.pi * RADIUS ** 4 / 2.0 / d


ROPE = dict(
    friction=MU,                 # rope material static = dynamic, combine "average"
    joint_damping=1e-3,          # N m s/rad, all three rotational DOFs (bend modes ~critically damped)
    armature=1e-6,               # kg m^2 per DOF (stabilises the 0.33 g links; see STATUS.md)
    linear_damping=0.0,          # PhysX body damping (1/s)
    angular_damping=0.0,
    solver_position_iterations=32,
    solver_velocity_iterations=4,
    contact_offset=0.002,
    rest_offset=0.0,
    max_depenetration_velocity=0.5,
)

N_LINKS = {"very_easy": 99, "easier": 111, "easy": 110, "medium": 107}


# Experiment-only override (never set in normal runs): KNOT_ROPE_OVERRIDES='{"joint_damping": 1e-3}'
import json as _json, os as _os
if _os.environ.get("KNOT_ROPE_OVERRIDES"):
    ROPE.update(_json.loads(_os.environ["KNOT_ROPE_OVERRIDES"]))
    print("[KnotUntying] rope parameter overrides:", _os.environ["KNOT_ROPE_OVERRIDES"])
