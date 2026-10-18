"""Public nominal model using published mass, propeller and thrust calibration.

Inertia, arm geometry and yaw coefficient remain benchmark assumptions. This is
not a fully identified Intel Aero rigid-body model. No residual is public.
"""

import numpy as np

MASS = 1.47
GRAVITY = 9.81
CLEARANCE = 0.09
DT = 0.01
PHYSICS_DT = 0.002
HORIZON = 16.0
# Released simulator's 20% command blend per 10 ms; not measured motor ID.
MOTOR_TAU = -DT / np.log(0.8)
AIR_DENSITY = 1.225
PROPELLER_DIAMETER = 0.23
THRUST_COEFFICIENT = 0.08937873049125099
CT = THRUST_COEFFICIENT * AIR_DENSITY * PROPELLER_DIAMETER**4 / 60**2  # N / RPM^2
PWM_TO_RPM = (-0.0026, 17.0948, -14834.1065)
AIRFRAME = "intel-aero-partial-v2"
TASK_VERSION = "random-pad-landing/4"
SCORE_VERSION = "oracle-relative-time/1"
ORACLE_TIME_RELAXATION = 0.10
SETTLE_TIME = 1.0
SUCCESS_POINTS = 60.0
TIME_BONUS_POINTS = 40.0
PAD_RADIUS = 0.45
INITIAL_XY_RANGE = (-1.0, 1.0)
INITIAL_HEIGHT_RANGE = (0.8, 1.5)  # body origin: flight-data height convention
PAD_XY_RANGE = (-1.0, 1.0)
MIN_TRAVEL = 0.5
ROTOR_MAX = MASS * GRAVITY * 1.7 / 4  # released simulator limit; not a bench maximum
POSITIONS = [(0.18, 0.18), (-0.18, 0.18), (-0.18, -0.18), (0.18, -0.18)]
YAW_GEARS = [0.015, -0.015, 0.015, -0.015]
ALLOCATION = np.array([[1.0] * 4, [y for x, y in POSITIONS], [-x for x, y in POSITIONS], YAW_GEARS])


def sample_task(rng):
    """Uniform start/pad samples conditioned on >= 0.5 m horizontal separation."""
    while True:
        xy = rng.uniform(*INITIAL_XY_RANGE, 2)
        pad = rng.uniform(*PAD_XY_RANGE, 2)
        if np.linalg.norm(xy - pad) >= MIN_TRAVEL:
            return np.r_[xy, rng.uniform(*INITIAL_HEIGHT_RANGE)], np.r_[pad, 0.0]


def xml(pad_position=(0.0, 0.0, 0.0)):
    pad = np.asarray(pad_position, dtype=float)
    if pad.shape != (3,) or not np.isfinite(pad).all() or pad[2] != 0:
        raise ValueError("Expected a finite ground-plane pad position")
    body = f'''<mujoco model="landing"><compiler angle="radian"/>
<option timestep="0.002" gravity="0 0 -9.81" integrator="RK4"/>
<visual><global offwidth="640" offheight="480"/><headlight ambient=".5 .5 .5"/></visual>
<worldbody><light pos="1 -2 4" diffuse=".8 .8 .8"/>
<geom name="floor" type="plane" size="4 4 .1" rgba=".24 .25 .27 1" friction=".8 .005 .0001"/>
<geom name="pad" type="cylinder" pos="{pad[0]} {pad[1]} .001" size="{PAD_RADIUS} .001" rgba=".22 .48 .45 1" contype="0" conaffinity="0"/>
<geom type="box" pos="{pad[0] - 0.13} {pad[1]} .004" size=".025 .18 .001" rgba=".95 .95 .9 1" contype="0" conaffinity="0"/>
<geom type="box" pos="{pad[0] + 0.13} {pad[1]} .004" size=".025 .18 .001" rgba=".95 .95 .9 1" contype="0" conaffinity="0"/>
<geom type="box" pos="{pad[0]} {pad[1]} .004" size=".13 .025 .001" rgba=".95 .95 .9 1" contype="0" conaffinity="0"/>
<body name="quad" pos="0 0 1.4"><freejoint/>
<inertial pos="0 0 0" mass="1.47" diaginertia=".025 .025 .045"/>
<geom name="fuselage" type="box" size=".09 .065 .025" rgba=".9 .5 .12 1"/>
'''
    for i, (x, y) in enumerate(POSITIONS):
        body += f'''<geom type="capsule" fromto="0 0 0 {x} {y} 0" size=".009" rgba=".12 .12 .13 1"/>
<geom name="rotor{i}" type="cylinder" pos="{x} {y} 0" size="{PROPELLER_DIAMETER / 2} .004" rgba=".17 .22 .25 1"/>
<geom type="capsule" fromto="{x * 0.6} {y * 0.6} -.015 {x * 0.6} {y * 0.6} -.08" size=".005"/>
<geom name="foot{i}" type="sphere" pos="{x * 0.6} {y * 0.6} -.08" size=".01" rgba=".08 .08 .08 1"/>
<site name="thrust{i}" pos="{x} {y} 0" size=".004"/>
'''
    body += "</body></worldbody><actuator>"
    for i, yaw in enumerate(YAW_GEARS):
        body += f'<general site="thrust{i}" gear="0 0 1 0 0 {yaw}" ctrllimited="true" ctrlrange="0 {ROTOR_MAX}"/>'
    return body + "</actuator></mujoco>"


def rotation(quaternion):
    w, x, y, z = np.asarray(quaternion) / np.linalg.norm(quaternion)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )
