"""Capsule-chain rope parameters for the RopeThreading port (asset builder + task cfg).

Adapted from knot_untying_lib/rope_params.py (knot_untying agent, 2026-10-12). Old rope (RoboTangle
rope_threading release profile contact_relaxed_v16, STL package layout.json): 8 mm diameter, 1100 mm,
FEM stable neo-Hookean E 5 MPa, nu 0.3, rho 650 kg/m3, mu 0.3, elastic rest shape = the initial U
(rope_reference_shape "initial": no pre-stress at the start).

Port: one PhysX articulation of 110 capsules (r 4 mm, d = 10 mm), spherical joints with implicit PD
drives (generic D6 joints, translations locked; SphericalJoint drives are inactive in an articulation, found
by knot_untying) whose targets are the joint coordinates of the start shape (= the rest shape).
Measured (probes/probe_stiff.py, clamped cantilevers): tip droop 12 links 6.9 mm vs E-B 7.0 mm, 20 links
56 mm vs 58 mm (small-deflection theory) -> the bend stiffness is right.
  bend  k_b = E I / d,  I = pi r^4 / 4          -> 0.1005 N m/rad at d = 10 mm
  twist k_t = G J / d,  J = pi r^4 / 2, G = E/(2(1+nu)) -> 0.0773 N m/rad
  mass per link rho pi r^2 d = 0.327 g (whole rope 35.9 g)
"""
import math

E, NU, RHO, MU = 5.0e6, 0.3, 650.0, 0.3
RADIUS = 0.004
LENGTH = 1.1
N_LINKS = 110


def bend_stiffness(d):
    return E * math.pi * RADIUS ** 4 / 4.0 / d


def twist_stiffness(d):
    G = E / (2 * (1 + NU))
    return G * math.pi * RADIUS ** 4 / 2.0 / d


def critical_damping(d, armature):
    """2 sqrt(k I) for one bend DOF; I = link inertia about its end + armature."""
    m = RHO * math.pi * RADIUS ** 2 * d
    i_end = m * d * d / 3.0
    return 2.0 * math.sqrt(bend_stiffness(d) * (i_end + armature))


ROPE = dict(
    friction=MU,                 # rope material static = dynamic, combine "average"
    joint_damping=1e-2,          # N m s/rad, all three rotational DOFs (probes/probe_stiff.py: 2e-4 rings for
                                 # seconds, 2e-3 leaves 1-4 mm/s on a 20-link cantilever, 1e-2 is quiet at once)
    armature=1e-5,               # kg m^2 per DOF (required: no armature -> NaN; knot_untying: 1e-5 survives hard pulls)
    linear_damping=0.0,          # PhysX body damping (1/s)
    angular_damping=0.0,
    solver_position_iterations=32,
    solver_velocity_iterations=4,
    contact_offset=0.002,
    rest_offset=0.0,
    max_depenetration_velocity=0.5,
)
