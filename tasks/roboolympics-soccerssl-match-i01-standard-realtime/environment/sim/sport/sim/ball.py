"""The ball: a standard orange golf ball on the SSL carpet (proposal §4.1-4.2; checked with
olympiad_review/screening/soccer_ssl_data/ball_roll.py and sports/soccer_ssl/tests/test_ball.py).

Shared by the world (B) and the overhead cameras (C): `add_ball(spec)` puts the ball into a mujoco.MjSpec,
`BallState` reads and writes it in a compiled model.

Parameters (every number with its source; "ESTIMATE" = no published value):
- radius 0.0215 m, mass 0.046 kg: rulebook 2026-09-19 §2.2 ("approximately 0.046 kilograms ... diameter 0.043 meters").
- sliding friction 0.35 (sliding deceleration mu g = 3.4 m/s^2): TIGERs Sumatra geom.xml accSlide -3400 mm/s^2 (fitted
  to match vision data, the RoboCup field setting); the ER-Force simulator uses 0.35 too.
- rolling friction 0.00138 m: rolling deceleration a = mu_roll g / (1.4 R) = 0.45 m/s^2, TIGERs Sumatra accRoll
  -450 mm/s^2. MuJoCo condim 6 reproduces a = mu_roll g / (1.4 R) to 1 % (proposal appendix B).
- torsional friction 0.005 m: ESTIMATE (ball_roll.py; it only damps spin about the vertical).
- carpet / wall contact: solref (-20000, -60), a velocity-independent restitution of 0.54 at 1 ms steps
  (test_ball.py); TIGERs chipDampingZ 0.54 [config, fitted to vision data], ER-Force simulator 0.56. A hard contact
  (solref 0.002) makes a 6.5 m/s flat kick hop 2 cm; this one hops about 1.4 mm.
- elliptic friction cone, impratio 10 (set on the model by field.build_scene): a pyramidal cone leaves 0.6 m/s of
  slip in rolling, the elliptic one about 0.1 m/s.
- the ball's geom has priority 1, so its parameters decide its contacts with the carpet, the walls and robot hulls; a
  part that owns its ball contact (the goals' foam, a dribbler) takes priority 2.
- no air drag: at 6.5 m/s the drag of a golf ball is about 2 % of its weight (Cd 0.25, ESTIMATE; proposal §4.2).
- solid sphere inertia (2/5 m R^2): sliding turns into rolling at 5/7 of the launch speed; the real SSL ball measures
  about 0.6 (ER-Force 2016 ETDP, TIGERs 2026 ETDP §2.1, cause unknown), declared in sport.toml (S8).
"""

from __future__ import annotations

import numpy as np

RADIUS = 0.0215
MASS = 0.046
MU_SLIDE = 0.35
MU_TORSION = 0.005
MU_ROLL = 0.00138
SOLREF = (-20000.0, -60.0)
RGBA = (1.0, 0.45, 0.0, 1.0)  # orange (rulebook §2.2)
G = 9.81
ROLL_DECEL = MU_ROLL * G / (1.4 * RADIUS)  # 0.45 m/s^2
SLIDE_DECEL = MU_SLIDE * G  # 3.43 m/s^2
BALL_BODY, BALL_GEOM, BALL_JOINT = "ball", "ball", "ball_free"


def add_ball(spec, pos=(0.0, 0.0)):
    """Add the ball (body `ball`, free joint `ball_free`, geom `ball`) to a mujoco.MjSpec; returns its names."""
    import mujoco

    body = spec.worldbody.add_body(name=BALL_BODY, pos=[pos[0], pos[1], RADIUS])
    body.add_freejoint(name=BALL_JOINT)
    body.add_geom(
        name=BALL_GEOM,
        type=mujoco.mjtGeom.mjGEOM_SPHERE,
        size=[RADIUS, 0, 0],
        mass=MASS,
        condim=6,
        priority=1,
        friction=[MU_SLIDE, MU_TORSION, MU_ROLL],
        solref=list(SOLREF),
        rgba=list(RGBA),
    )
    return dict(body=BALL_BODY, geom=BALL_GEOM, joint=BALL_JOINT)


class BallState:
    """Read / write the ball in a compiled model (truth; the referee and the recorder use it, never a player)."""

    def __init__(self, model, data):
        import mujoco

        self.m, self.d = model, data
        j = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, BALL_JOINT)
        self.qa, self.va = int(model.jnt_qposadr[j]), int(model.jnt_dofadr[j])
        self.geom = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, BALL_GEOM)
        self.body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, BALL_BODY)

    @property
    def pos(self) -> np.ndarray:
        return self.d.qpos[self.qa : self.qa + 3]

    @property
    def vel(self) -> np.ndarray:
        return self.d.qvel[self.va : self.va + 3]

    @property
    def spin(self) -> np.ndarray:
        return self.d.qvel[self.va + 3 : self.va + 6]

    def place(self, x: float, y: float, z: float = RADIUS, vel=(0.0, 0.0, 0.0)):
        """put the ball at (x, y, z) with linear velocity `vel` and no spin (the referee's ball placement, S3)."""
        self.d.qpos[self.qa : self.qa + 3] = (x, y, z)
        self.d.qpos[self.qa + 3 : self.qa + 7] = (1.0, 0.0, 0.0, 0.0)
        self.d.qvel[self.va : self.va + 3] = vel
        self.d.qvel[self.va + 3 : self.va + 6] = 0.0

    def set_velocity(self, vel, spin=None):
        self.d.qvel[self.va : self.va + 3] = vel
        if spin is not None:
            self.d.qvel[self.va + 3 : self.va + 6] = spin
