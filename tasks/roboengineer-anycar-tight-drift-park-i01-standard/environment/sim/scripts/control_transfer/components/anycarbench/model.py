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


def visual_bodywork():
    """Original GT-style RC bodywork; zero mass and no contact geometry."""
    def loft(name, sections):
        vertices = []
        for x, width, bottom, top in sections:
            # Beveled shoulders and a gently crowned top avoid a box silhouette.
            vertices.extend([(x, -width, bottom), (x, width, bottom),
                             (x, width, top - .008), (x, .72 * width, top),
                             (x, -.72 * width, top), (x, -width, top - .008)])
        faces = []
        for i in range(len(sections) - 1):
            for j in range(6):
                a, b = i * 6 + j, i * 6 + (j + 1) % 6
                c, d = a + 6, b + 6
                faces.extend([(a, b, c), (b, d, c)])
        for j in range(1, 5):
            faces.append((0, j + 1, j))
            k = (len(sections) - 1) * 6
            faces.append((k, k + j, k + j + 1))
        v = " ".join(str(t) for row in vertices for t in row)
        f = " ".join(str(t) for row in faces for t in row)
        return f'<mesh name="{name}" vertex="{v}" face="{f}"/>'

    assets = [
        '<material name="race_paint" rgba=".035 .22 .29 1" specular=".8" shininess=".75"/>',
        '<material name="race_glass" rgba=".025 .045 .065 1" specular="1" shininess=".95"/>',
        '<material name="carbon" rgba=".035 .04 .045 1" specular=".3" shininess=".3"/>',
        '<material name="alloy" rgba=".58 .62 .65 1" specular=".9" shininess=".8"/>',
        loft('gt_body', [(-.235,.065,.082,.102),(-.205,.103,.075,.128),
                        (-.13,.105,.080,.14),(.06,.10,.082,.135),
                        (.17,.105,.078,.115),(.225,.085,.080,.10)]),
        loft('gt_cabin', [(-.14,.077,.13,.14),(-.075,.072,.132,.196),
                         (.012,.066,.13,.194),(.094,.074,.12,.132)]),
        loft('gt_roof', [(-.077,.061,.194,.197),(-.06,.063,.197,.203),
                        (.008,.060,.194,.200),(.02,.056,.189,.193)]),
    ]
    visual = 'mass="0" contype="0" conaffinity="0" group="2"'
    geoms = [f'<geom name="visual_{n}" type="mesh" mesh="{n}" material="{mat}" {visual}/>'
             for n, mat in [('gt_body','race_paint'),('gt_cabin','race_glass'),('gt_roof','race_paint')]]
    def box(name, pos, size, material='carbon', rgba=None):
        color = f'rgba="{rgba}"' if rgba else f'material="{material}"'
        geoms.append(f'<geom name="visual_{name}" type="box" pos="{pos}" size="{size}" {color} {visual}/>')
    box('splitter', '.211 0 .076', '.027 .098 .003')
    box('diffuser', '-.218 0 .074', '.025 .092 .006')
    box('rear_wing', '-.207 0 .181', '.025 .118 .003')
    for side in [-1, 1]:
        box(f'wing_support{side}', f'-.20 {side*.055} .153', '.003 .003 .026')
        box(f'wing_endplate{side}', f'-.207 {side*.119} .181', '.028 .002 .014', 'race_paint')
        box(f'sill{side}', f'-.012 {side*.1} .082', '.115 .005 .008')
        box(f'headlight{side}', f'.224 {side*.061} .098', '.002 .023 .005', rgba='.85 .94 1 1')
        box(f'taillight{side}', f'-.231 {side*.047} .105', '.003 .019 .004', rgba='.85 .025 .018 1')
        box(f'mirror{side}', f'.055 {side*.096} .149', '.012 .015 .006', 'race_paint')
        box(f'roof_stripe{side}', f'-.025 {side*.013} .2035', '.032 .006 .001', rgba='.88 .66 .12 1')
    return assets, "".join(geoms)


def traffic_cone_assets():
    """Shared tapered, striped cone meshes; render-only, no contact or mass."""
    assets = []
    levels = (.016, .09, .135, .18, .22, .26)
    for band, (low, high) in enumerate(zip(levels[:-1], levels[1:])):
        vertices = []
        for z in (low, high):
            radius = .063 - (z - .016) / .244 * .054
            vertices.extend((radius * np.cos(t), radius * np.sin(t), z)
                            for t in np.linspace(0, 2*np.pi, 16, endpoint=False))
        faces = []
        for j in range(16):
            k = (j+1) % 16
            faces.extend([(j,k,j+16),(k,k+16,j+16)])
        for j in range(1,15):
            faces.extend([(0,j+1,j),(16,16+j,17+j)])
        v = " ".join(str(float(x)) for row in vertices for x in row)
        f = " ".join(str(x) for row in faces for x in row)
        assets.append(f'<mesh name="traffic_cone_{band}" vertex="{v}" face="{f}"/>')
    return assets


def traffic_cone(x, y):
    visual = 'mass="0" contype="0" conaffinity="0"'
    result = [f'<geom type="box" pos="{x} {y} .008" size=".078 .078 .008" rgba=".035 .035 .035 1" {visual}/>']
    for band in range(5):
        color = '.96 .96 .92 1' if band % 2 else '1 .23 .025 1'
        result.append(f'<geom type="mesh" mesh="traffic_cone_{band}" pos="{x} {y} 0" rgba="{color}" {visual}/>')
    return "".join(result)


def xml_model(plant, surfaces, command):
    """Procedural chassis; wheel/joint/tendon mechanism retains source numeric settings."""
    circuit = "track_id" in command
    if circuit:
        from .tracks import get_route

        route = get_route(command["track_id"], command.get("route_revision", "circuit-sector/1"))
        extent = route.half_extent
    else:
        a, b = command["a"], command["b"]
        extent = 12
    road = []
    assets, bodywork = visual_bodywork()
    assets.extend(traffic_cone_assets())
    for i, surface in enumerate(surfaces):
        left, right, mu = surface
        road.append(
            f'<geom name="surface{i}" type="box" pos="{(left + right) / 2} 0 -0.10" size="{(right - left) / 2} {extent} .10" friction="{mu} .005 .0001" priority="2" condim="3" rgba="{0.53 + 0.03 * (i % 2)} {0.43 + 0.03 * (i % 2)} .30 1"/>'
        )
    if circuit:
        samples = route.at(np.linspace(0, route.length, min(1500, max(128, int(route.length / 0.7))), endpoint=False))
        # One non-overlapping visual ribbon, split into surface-colored meshes.
        # The physics floor above is unchanged and is the only tire-contact road.
        normals = np.column_stack((-np.sin(samples[:, 2]), np.cos(samples[:, 2])))
        vertices = np.empty((2 * len(samples), 3))
        vertices[0::2, :2] = samples[:, :2] + 0.8 * normals
        vertices[1::2, :2] = samples[:, :2] - 0.8 * normals
        vertices[:, 2] = 0.004
        faces = [[] for _ in surfaces]
        for i, (x, y, yaw, _) in enumerate(samples):
            j = (i + 1) % len(samples)
            surface_index = next((k for k, (lo, hi, _) in enumerate(surfaces) if lo <= x < hi), 0)
            faces[surface_index].extend([(2 * i, 2 * i + 1, 2 * j), (2 * i + 1, 2 * j + 1, 2 * j)])
        for index, triangles in enumerate(faces):
            if not triangles:
                continue
            vertex_text = " ".join(str(float(v)) for v in vertices.ravel())
            face_text = " ".join(str(v) for triangle in triangles for v in triangle)
            assets.append(f'<mesh name="road{index}" inertia="shell" vertex="{vertex_text}" face="{face_text}"/>')
            shade = 0.17 + 0.035 * index
            road.append(
                f'<geom type="mesh" mesh="road{index}" contype="0" conaffinity="0" rgba="{shade} {shade + 0.01} {shade + 0.03} 1"/>'
            )
        road.append(
            '<geom type="plane" size="0 0 .1" pos="0 0 -.11" contype="0" conaffinity="0" rgba=".53 .46 .34 1"/>'
        )
        for i, (x, y, yaw, _) in enumerate(samples):
            for side in (-1, 1):
                bx, by = x - side * 0.9 * np.sin(yaw), y + side * 0.9 * np.cos(yaw)
                # Avoid placing barriers inside another route branch at crossovers.
                if route.distance([[bx, by]])[0] < 0.82:
                    continue
                road.append(
                    f'<geom name="barrier_{i}_{side}" type="cylinder" size=".035 .13" pos="{bx} {by} .13" mass="0" rgba="0 0 0 0"/>{traffic_cone(bx, by)}'
                )
    else:
        # Solid outer/inner track barriers; contacts are actual physics, not rendered decorations.
        for i, angle in enumerate(np.linspace(0, 2 * np.pi, 48, endpoint=False)):
            for side in (-1, 1):
                x, y = (a + side * 0.9) * np.cos(angle), (b + side * 0.9) * np.sin(angle)
                road.append(
                    f'<geom name="barrier_{i}_{side}" type="cylinder" size=".035 .13" pos="{x} {y} .13" mass="0" rgba="0 0 0 0"/>{traffic_cone(x, y)}'
                )
    wheels = []
    for name, x, y in (("fl", 0.1385, 0.115), ("fr", 0.1385, -0.115), ("bl", -0.158, 0.115), ("br", -0.158, -0.115)):
        steering = f'<joint name="{name}_steering" class="steering"/>' if name.startswith("f") else ""
        wheel_visuals = []
        for side in (-1, 1):
            yside = side * .021
            wheel_visuals.append(f'<geom type="cylinder" size=".027 .001" pos="0 {yside} 0" euler="1.5707963267948966 0 0" mass="0" contype="0" conaffinity="0" material="carbon"/>')
            for theta in np.linspace(0, 2*np.pi, 10, endpoint=False):
                x1, z1 = .008*np.cos(theta), .008*np.sin(theta)
                x2, z2 = .025*np.cos(theta+.12), .025*np.sin(theta+.12)
                wheel_visuals.append(f'<geom type="capsule" size=".002" fromto="{x1} {yside*1.06} {z1} {x2} {yside*1.06} {z2}" mass="0" contype="0" conaffinity="0" material="alloy"/>')
        wheels.append(f'''<body name="wheel_{name}" pos="{x} {y} .0488">
          <joint name="{name}_suspension" type="slide" axis="0 0 1" limited="true" range="-.05 0" springdamper=".1 .1"/>
          {steering}<joint name="{name}_spin" class="spin"/>
          <geom name="tire_{name}" type="cylinder" size=".04 .02" euler="1.5707963267948966 0 0" mass=".997904" friction="2 .005 .0001" contype="1" conaffinity="0" rgba=".022 .025 .028 1"/>
          {"".join(wheel_visuals)}
          <geom type="cylinder" size=".008 .024" euler="1.5707963267948966 0 0" mass="0" contype="0" conaffinity="0" rgba=".65 .68 .70 1"/>
          </body>''')
    tendon = "".join(f'<joint joint="{n}_spin" coef=".25"/>' for n in WHEELS)
    return f"""<mujoco model="contact_vehicle"><compiler angle="radian"/><option timestep=".002" integrator="implicitfast" cone="elliptic" iterations="50"/><size njmax="2000" nconmax="300"/>
    <visual>{'<map znear=".0001" zfar="5"/>' if circuit else ""}<global offwidth="640" offheight="480"/><quality shadowsize="1024" offsamples="0"/><headlight ambient=".5 .5 .5" diffuse=".65 .65 .65"/></visual>
    <default><geom solref=".01 1"/><default class="steering"><joint type="hinge" axis="0 0 1" limited="true" range="-.38 .38" frictionloss=".01" damping=".001" armature=".0002"/></default><default class="spin"><joint type="hinge" axis="0 1 0" frictionloss=".001" damping=".01" armature=".01"/></default></default>
    <asset>{"".join(assets)}</asset>
    <worldbody><light pos="0 0 10" dir="0 0 -1" directional="true"/>{"".join(road)}
    <body name="car" pos="0 0 .08"><freejoint/>
    <geom name="chassis" type="box" pos="-.01 0 .094655" size=".20 .09 .035" mass="3.542137" rgba="0 0 0 0"/>
    <geom type="box" pos=".0123949 0 .162178" size=".012525 .045 .0125" mass=".072" rgba="0 0 0 0"/>
    <geom type="cylinder" pos="-.035325 0 .202405" size=".035 .015" mass=".180" rgba="0 0 0 0"/>
    {bodywork}
    <body name="steering_link" pos=".1385 0 .0488"><joint name="steering" class="steering"/><geom type="sphere" size=".015" mass=".01" contype="0" conaffinity="0" rgba="0 0 0 0"/></body>
    {"".join(wheels)}</body></worldbody>
    <tendon><fixed name="drive">{tendon}</fixed></tendon>
    <actuator><position name="steer" kp="25" joint="steering" ctrllimited="true" ctrlrange="-.36 .36"/><velocity name="drive" kv="100" gear=".04" forcelimited="true" forcerange="-500 500" tendon="drive"/></actuator>
    <equality><joint joint1="fl_steering" joint2="steering" polycoef="0 1 .375 .140625 -.0722656"/><joint joint1="fr_steering" joint2="steering" polycoef="0 1 -.375 .140625 .0722656"/></equality></mujoco>"""



class Diverged(RuntimeError):
    """The simulation left the finite state space (or MuJoCo reset an unstable state): the rollout's episode fails as
    the policy's failure, never as an evaluator error."""


BAD_WARNINGS = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)

class Vehicle:
    def __init__(self, plant=None, surfaces=None, command=None, *, model_xml=None):
        self.plant = dict(NOMINAL if plant is None else plant)
        self.command = command or dict(a=4.5, b=3.5, phase=0.0, direction=1)
        self.surfaces = surfaces or [(-12, 12, 0.8)]
        self.model = mujoco.MjModel.from_xml_string(
            model_xml if model_xml is not None else xml_model(self.plant, self.surfaces, self.command)
        )
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
        # MuJoCo's warning counters are cumulative: a divergence is a new bad-state warning after the reset
        self.warning_base = [self.data.warning[w].number for w in BAD_WARNINGS]

    def advance(self, action, substep_callback=None):
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
            last = (self.data.time, self.data.qpos.copy(), self.data.qvel.copy(), self.data.act.copy())
            mujoco.mj_step(self.model, self.data)
            if (not np.isfinite(self.data.qpos).all() or not np.isfinite(self.data.qvel).all()
                    or any(self.data.warning[w].number > b
                           for w, b in zip(BAD_WARNINGS, getattr(self, "warning_base", [0] * len(BAD_WARNINGS))))):
                # back to the last finite state, before any callback reads it; the rollout ends the episode there
                self.data.time, self.data.qpos[:], self.data.qvel[:], self.data.act[:] = last
                mujoco.mj_forward(self.model, self.data)
                raise Diverged("the simulation diverged")
            for contact in self.data.contact:
                pair = {int(contact.geom1), int(contact.geom2)}
                if pair & self.tire_ids and pair & self.surface_ids:
                    self.contacts_seen.update(pair & self.surface_ids)
                if pair & self.barrier_ids and pair & (self.tire_ids | self.body_ids):
                    self.collision = True
                if pair & self.body_ids and pair & self.surface_ids:
                    self.body_contact = True

            if substep_callback is not None:
                substep_callback(self)

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
