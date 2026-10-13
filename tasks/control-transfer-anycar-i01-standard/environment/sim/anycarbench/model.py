"""CPU contact vehicle with four driven wheels, suspension and Ackermann constraints.

Public nominal parameters only. Hidden plant draws belong to the trusted family.
"""

from collections import deque
import os

# Must precede MuJoCo import. Evaluation never silently falls back to GPU rendering.
os.environ.setdefault("MUJOCO_GL", "osmesa")
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "1")
os.environ.setdefault("GALLIUM_DRIVER", "llvmpipe")
for _key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "LP_NUM_THREADS"):
    os.environ.setdefault(_key, "1")
import numpy as np
import mujoco

NOMINAL = dict(
    mass_scale=1.0,
    inertia_scale=1.0,
    com_x=0.0,
    com_y=0.0,
    motor_gain=1.0,
    steering_gain=1.0,
    steering_bias=0.0,
    motor_tau=0.04,
    steering_tau=0.04,
    delay_steps=0,
)
WHEELS = ("fl", "fr", "bl", "br")


def xml_model(plant, surfaces, command):
    """Procedural chassis; wheel/joint/tendon mechanism retains source numeric settings."""
    a, b = command["a"], command["b"]
    road = []
    for i, surface in enumerate(surfaces):
        left, right, mu = surface
        road.append(
            f'<geom name="surface{i}" type="box" pos="{(left + right) / 2} 0 -0.10" size="{(right - left) / 2} 12 .10" friction="{mu} .005 .0001" priority="2" condim="3" rgba="{0.53 + 0.03 * (i % 2)} {0.43 + 0.03 * (i % 2)} .30 1"/>'
        )
    # Solid outer/inner track barriers; contacts are actual physics, not rendered decorations.
    for i, angle in enumerate(np.linspace(0, 2 * np.pi, 48, endpoint=False)):
        for side in (-1, 1):
            x, y = (a + side * 0.9) * np.cos(angle), (b + side * 0.9) * np.sin(angle)
            road.append(
                f'<geom name="barrier_{i}_{side}" type="cylinder" size=".035 .13" pos="{x} {y} .13" mass="0" rgba=".85 .42 .12 1"/>'
            )
    wheels = []
    for name, x, y in (("fl", 0.1385, 0.115), ("fr", 0.1385, -0.115), ("bl", -0.158, 0.115), ("br", -0.158, -0.115)):
        steering = f'<joint name="{name}_steering" class="steering"/>' if name.startswith("f") else ""
        wheels.append(f'''<body name="wheel_{name}" pos="{x} {y} .0488">
          <joint name="{name}_suspension" type="slide" axis="0 0 1" limited="true" range="-.05 0" springdamper=".1 .1"/>
          {steering}<joint name="{name}_spin" class="spin"/>
          <geom name="tire_{name}" type="cylinder" size=".04 .02" euler="1.5707963267948966 0 0" mass=".997904" friction="2 .005 .0001" contype="1" conaffinity="0" rgba=".09 .10 .11 1"/>
          <geom type="cylinder" size=".023 .021" euler="1.5707963267948966 0 0" mass="0" contype="0" conaffinity="0" rgba=".65 .68 .70 1"/>
          </body>''')
    tendon = "".join(f'<joint joint="{n}_spin" coef=".25"/>' for n in WHEELS)
    return f"""<mujoco model="contact_vehicle"><compiler angle="radian"/><option timestep=".002" integrator="implicitfast" cone="elliptic" iterations="50"/><size njmax="2000" nconmax="300"/>
    <visual><global offwidth="640" offheight="480"/><quality shadowsize="1024" offsamples="0"/><headlight ambient=".5 .5 .5" diffuse=".65 .65 .65"/></visual>
    <default><geom solref=".01 1"/><default class="steering"><joint type="hinge" axis="0 0 1" limited="true" range="-.38 .38" frictionloss=".01" damping=".001" armature=".0002"/></default><default class="spin"><joint type="hinge" axis="0 1 0" frictionloss=".001" damping=".01" armature=".01"/></default></default>
    <worldbody><light pos="0 0 10" dir="0 0 -1" directional="true"/>{"".join(road)}
    <body name="car" pos="0 0 .08"><freejoint/>
    <geom name="chassis" type="box" pos="-.01 0 .094655" size=".20 .09 .035" mass="3.542137" rgba=".12 .38 .51 1"/>
    <geom type="box" pos=".0123949 0 .162178" size=".012525 .045 .0125" mass=".072" rgba=".12 .12 .13 1"/>
    <geom type="cylinder" pos="-.035325 0 .202405" size=".035 .015" mass=".180" rgba=".15 .15 .16 1"/>
    <body name="steering_link" pos=".1385 0 .0488"><joint name="steering" class="steering"/><geom type="sphere" size=".015" mass=".01" contype="0" conaffinity="0" rgba="0 0 0 0"/></body>
    {"".join(wheels)}</body></worldbody>
    <tendon><fixed name="drive">{tendon}</fixed></tendon>
    <actuator><position name="steer" kp="25" joint="steering" ctrllimited="true" ctrlrange="-.36 .36"/><velocity name="drive" kv="100" gear=".04" forcelimited="true" forcerange="-500 500" tendon="drive"/></actuator>
    <equality><joint joint1="fl_steering" joint2="steering" polycoef="0 1 .375 .140625 -.0722656"/><joint joint1="fr_steering" joint2="steering" polycoef="0 1 -.375 .140625 .0722656"/></equality></mujoco>"""


class Vehicle:
    def __init__(self, plant=None, surfaces=None, command=None):
        self.plant = dict(NOMINAL if plant is None else plant)
        self.command = command or dict(a=4.5, b=3.5, phase=0.0, direction=1)
        self.surfaces = surfaces or [(-12, 12, 0.8)]
        self.model = mujoco.MjModel.from_xml_string(xml_model(self.plant, self.surfaces, self.command))
        self.data = mujoco.MjData(self.model)
        p = self.plant
        self.model.body_mass[1:] *= p["mass_scale"]
        self.model.body_inertia[1:] *= p["mass_scale"] * p["inertia_scale"]
        self.model.body_ipos[1, :2] += [p["com_x"], p["com_y"]]
        mujoco.mj_setConst(self.model, self.data)
        self.buffer = deque([np.zeros(2) for _ in range(p["delay_steps"])])
        self.applied = np.zeros(2)
        self.tire_ids = {self.model.geom("tire_" + n).id for n in WHEELS}
        self.surface_ids = {self.model.geom("surface" + str(i)).id for i in range(len(self.surfaces))}
        self.barrier_ids = {i for i in range(self.model.ngeom) if self.model.geom(i).name.startswith("barrier_")}
        self.body_ids = {i for i in range(self.model.ngeom) if self.model.geom_bodyid[i] == 1}
        self.collision = False
        self.body_contact = False
        self.contacts_seen = set()

    def reset(self, x, y, yaw):
        mujoco.mj_resetData(self.model, self.data)
        self.data.qpos[:3] = [x, y, 0.055]
        self.data.qpos[3:7] = [np.cos(yaw / 2), 0, 0, np.sin(yaw / 2)]
        for _ in range(500):
            mujoco.mj_step(self.model, self.data)
        self.data.time = 0
        self.buffer = deque([np.zeros(2) for _ in range(self.plant["delay_steps"])])
        self.applied[:] = 0
        self.collision = self.body_contact = False
        self.contacts_seen = set()

    def advance(self, action):
        self.buffer.append(np.asarray(action, dtype=float).copy())
        command = self.buffer.popleft()
        p = self.plant
        desired = [
            command[0] * p["motor_gain"],
            np.clip(command[1] * p["steering_gain"] + p["steering_bias"], -0.36, 0.36),
        ]
        for _ in range(10):
            self.applied += (1 - np.exp(-0.002 / np.array([p["motor_tau"], p["steering_tau"]]))) * (
                desired - self.applied
            )
            self.data.ctrl[:] = [self.applied[1], self.applied[0]]
            mujoco.mj_step(self.model, self.data)
            for contact in self.data.contact:
                pair = {int(contact.geom1), int(contact.geom2)}
                if pair & self.tire_ids and pair & self.surface_ids:
                    self.contacts_seen.update(pair & self.surface_ids)
                if pair & self.barrier_ids and pair & (self.tire_ids | self.body_ids):
                    self.collision = True
                if pair & self.body_ids and pair & self.surface_ids:
                    self.body_contact = True

    def state(self):
        d = self.data
        rotation = d.xmat[1].reshape(3, 3)
        yaw = np.arctan2(rotation[1, 0], rotation[0, 0])
        velocity = rotation.T @ d.qvel[:3]
        wheels = [float(d.joint(n + "_spin").qvel[0]) for n in WHEELS]
        return np.array([*d.qpos[:2], yaw, *velocity[:2], d.qvel[5], *wheels, float(d.joint("steering").qpos[0])])

    def contact_friction(self):
        return [
            float(c.friction[0])
            for c in self.data.contact
            if {int(c.geom1), int(c.geom2)} & self.tire_ids and {int(c.geom1), int(c.geom2)} & self.surface_ids
        ]
