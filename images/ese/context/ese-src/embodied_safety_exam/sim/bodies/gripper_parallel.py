"""A two-finger parallel gripper, drawn here: the MJCF is written by this module from the numbers in `Dims`.

Nothing is taken from a vendor's model. The shapes are boxes and cylinders: a collar that sits on a wrist flange, a
housing, a camera pod beside it, two finger bars on sliding joints and a flat rubber pad on the inner face of each.

Frame of the gripper (the body `palm`, origin in the middle of the mounting face):

    +z  out of the hand (the approach direction)
    +y  the direction the fingers close along (finger `left` sits at +y, finger `right` at -y)
    +x  the side the camera pod is on

which is the convention of the bench's tool sites (`RobotSpec.tool_site`: "+z out of the hand, +y the closing
direction"). The site `pinch` has the gripper's axes and lies on the middle of the two pads' faces: where the pads meet.

Joints `finger_left` and `finger_right` slide towards the middle: 0 is open, `Dims.travel` closed. One position
actuator, `grip`, drives the tendon `grip` (the sum of the two joints: how far the fingers have closed, in metres, 0
to `2 * travel`); the equality `fingers` keeps the two joints equal, so that the fingers stay centred on the pinch
point whatever they close on. The actuator's force limit is the grip force on each pad.

    xml = mjcf()                                    # the text
    spec = spec()                                   # a mujoco.MjSpec, to attach to a wrist with a name prefix
    describe()                                      # sizes, masses, where the pinch point and the camera are
    opening_table()                                 # ((gripper target 0 .. 0.8, free distance between the pads in m), ...)

`python -m embodied_safety_exam.sim.bodies.gripper_parallel --out build/gripper` writes the MJCF, the numbers and pictures.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass

os.environ.setdefault("MUJOCO_GL", "egl")

import mujoco  # noqa: E402
import numpy as np  # noqa: E402

# the units of a gripper target on the bench (`RobotSpec.gripper_max`): 0 open, 0.8 closed
TARGET_CLOSED = 0.8
# contact parameters of everything the bench builds (the same numbers as `embodied_safety_exam.sim.props`)
_SOLREF = "0.005 1"
_SOLIMP = "0.95 0.99 0.001 0.5 2"


@dataclass(frozen=True)
class Dims:
    """Every number of the gripper, in metres, kilograms, newtons. Docs/MOTION.md 10.4 says why these."""
    opening: float = 0.085              # free distance between the pads, open
    closed_gap: float = 0.0004          # what is left between the pads at the joints' closing limit
    # the collar on the wrist flange (a cylinder about z)
    collar_radius: float = 0.026
    collar_length: float = 0.012
    # the housing: half extents (x: thickness, y: along the closing direction, z: depth)
    housing_half: tuple = (0.024, 0.062, 0.024)
    # a finger bar: half extents; its inner face stands `pad_thickness` behind the pad's face
    finger_half: tuple = (0.011, 0.006, 0.0375)
    # a pad: 22 mm wide, 35.4 mm long, 4 mm thick; it ends flush with the fingertip
    pad_half_width: float = 0.011
    pad_half_length: float = 0.0177
    pad_thickness: float = 0.004
    # the camera pod on the +x side of the housing: half extents, and how far in front of it the camera site is
    pod_half: tuple = (0.016, 0.014, 0.012)
    pod_centre_z: float = 0.040
    camera_fovy: float = 62.0
    camera_look_past_pinch: float = 0.155   # the camera looks at the point this far beyond the pinch point
    # masses
    mass_collar: float = 0.04
    mass_housing: float = 0.40          # with its servo and screw
    mass_pod: float = 0.02
    mass_finger: float = 0.06
    mass_pad: float = 0.01
    # the drive
    grip_force: float = 40.0            # N on each pad at most
    kp: float = 2000.0                  # N per metre of tendon (the sum of both fingers' travel)
    kv: float = 20.0
    joint_damping: float = 5.0          # N s/m
    joint_armature: float = 0.01        # kg: the screw's and rotor's inertia at the finger
    pad_friction: tuple = (1.0, 0.02, 0.001)

    @property
    def travel(self) -> float:
        """How far one finger slides from open to its closing limit."""
        return (self.opening - self.closed_gap) / 2.0

    @property
    def housing_front(self) -> float:
        return self.collar_length + 2.0 * self.housing_half[2]

    @property
    def tip(self) -> float:
        """z of the fingertips."""
        return self.housing_front + 2.0 * self.finger_half[2]

    @property
    def pinch(self) -> float:
        """z of the pinch point: the middle of the pads."""
        return self.tip - self.pad_half_length

    @property
    def tip_reach(self) -> float:
        """How far the fingertips reach past the pinch point (at any opening: the fingers slide, they do not swing)."""
        return self.pad_half_length

    @property
    def mass(self) -> float:
        return self.mass_collar + self.mass_housing + self.mass_pod + 2.0 * (self.mass_finger + self.mass_pad)

    @property
    def camera_pos(self) -> tuple:
        """The camera site: just in front of the pod's front face."""
        return (self.housing_half[0] + self.pod_half[0] + 0.004, 0.0, self.pod_centre_z + self.pod_half[2] + 0.0015)

    @property
    def camera_target(self) -> tuple:
        return (0.0, 0.0, self.pinch + self.camera_look_past_pinch)


DIMS = Dims()


def _f(*v) -> str:
    return " ".join(f"{float(x):.6g}" for x in v)


def mjcf(dims: Dims = DIMS, model: str = "gripper_parallel") -> str:
    """The gripper as MJCF text. One top-level body, `palm`, without a joint: attach it to a wrist."""
    d = dims
    hx, hy, hz = d.housing_half
    fx, fy, fz = d.finger_half
    if hy < d.opening / 2.0 + d.pad_thickness + 2.0 * fy:
        raise ValueError("the housing is narrower than the open fingers")
    zc = d.collar_length / 2.0
    zh = d.collar_length + hz
    front = d.housing_front
    # a finger body's origin: on the housing's front face, at the middle of the finger bar when open
    y_pad_face = d.opening / 2.0                        # the pad's inner face, open
    y_pad = y_pad_face + d.pad_thickness / 2.0
    y_bar = y_pad_face + d.pad_thickness + fy
    px, _, pz = d.pod_half
    pod_x = hx + px
    cam = d.camera_pos

    def finger(side: str, sign: float) -> str:
        # `sign`: +1 for the finger at +y. Its joint slides towards the middle; its shapes are given in the finger's
        # own frame, which has the gripper's axes
        return f"""
      <body name="finger_{side}" pos="{_f(0, sign * y_bar, front)}">
        <joint name="finger_{side}" class="finger" axis="{_f(0, -sign, 0)}"/>
        <geom name="bar_{side}" class="shell" type="box" size="{_f(fx, fy, fz)}" pos="{_f(0, 0, fz)}" mass="{_f(d.mass_finger)}"
          rgba="0.62 0.63 0.65 1"/>
        <geom name="foot_{side}" class="look" type="box" size="{_f(fx + 0.003, fy + 0.003, 0.004)}" pos="{_f(0, 0, 0.004)}"
          rgba="0.30 0.31 0.33 1"/>
        <geom name="pad_{side}" class="pad" size="{_f(d.pad_half_width, d.pad_thickness / 2.0, d.pad_half_length)}"
          pos="{_f(0, sign * (y_pad - y_bar), 2.0 * fz - d.pad_half_length)}" mass="{_f(d.mass_pad)}"/>
      </body>"""

    return f"""<mujoco model="{model}">
  <compiler angle="radian" autolimits="true"/>
  <default>
    <default class="shell">
      <geom group="2" solref="{_SOLREF}" solimp="{_SOLIMP}" friction="0.6 0.005 0.0001"/>
    </default>
    <default class="look">
      <geom group="2" contype="0" conaffinity="0" mass="0"/>
    </default>
    <default class="pad">
      <geom group="2" type="box" solref="{_SOLREF}" solimp="{_SOLIMP}" friction="{_f(*d.pad_friction)}" condim="4" priority="1"
        rgba="0.09 0.09 0.10 1"/>
    </default>
    <default class="finger">
      <joint type="slide" range="{_f(0, d.travel)}" damping="{_f(d.joint_damping)}" armature="{_f(d.joint_armature)}"
        solreflimit="{_SOLREF}" solimplimit="0.95 0.99 0.001"/>
    </default>
  </default>
  <worldbody>
    <body name="palm">
      <geom name="collar" class="shell" type="cylinder" size="{_f(d.collar_radius, zc)}" pos="{_f(0, 0, zc)}" mass="{_f(d.mass_collar)}"
        rgba="0.45 0.46 0.48 1"/>
      <geom name="housing" class="shell" type="box" size="{_f(hx, hy, hz)}" pos="{_f(0, 0, zh)}" mass="{_f(d.mass_housing)}"
        rgba="0.20 0.21 0.23 1"/>
      <geom name="rail" class="look" type="box" size="{_f(hx * 0.45, hy - 0.004, 0.0015)}" pos="{_f(0, 0, front - 0.0005)}"
        rgba="0.55 0.56 0.58 1"/>
      <geom name="pod" class="shell" type="box" size="{_f(*d.pod_half)}" pos="{_f(pod_x, 0, d.pod_centre_z)}" mass="{_f(d.mass_pod)}"
        rgba="0.12 0.12 0.13 1"/>
      <geom name="lens" class="look" type="cylinder" size="0.006 0.001" pos="{_f(cam[0], 0, d.pod_centre_z + pz)}"
        rgba="0.02 0.02 0.03 1"/>
      <site name="mount" pos="0 0 0" size="0.002" group="4"/>
      <site name="pinch" pos="{_f(0, 0, d.pinch)}" size="0.002" group="4"/>
      <site name="camera" pos="{_f(*cam)}" size="0.002" group="4"/>{finger("left", 1.0)}{finger("right", -1.0)}
    </body>
  </worldbody>
  <tendon>
    <fixed name="grip">
      <joint joint="finger_left" coef="1"/>
      <joint joint="finger_right" coef="1"/>
    </fixed>
  </tendon>
  <equality>
    <joint name="fingers" joint1="finger_left" joint2="finger_right" polycoef="0 1 0 0 0" solref="{_SOLREF}"
      solimp="0.95 0.99 0.001"/>
  </equality>
  <actuator>
    <position name="grip" tendon="grip" kp="{_f(d.kp)}" kv="{_f(d.kv)}" ctrlrange="{_f(0, 2.0 * d.travel)}"
      forcerange="{_f(-d.grip_force, d.grip_force)}"/>
  </actuator>
</mujoco>
"""


def spec(dims: Dims = DIMS) -> mujoco.MjSpec:
    """The gripper as a `mujoco.MjSpec`, ready for `parent.attach(spec, site=..., prefix=...)`."""
    return mujoco.MjSpec.from_string(mjcf(dims))


def ctrl_of(target: float, dims: Dims = DIMS) -> float:
    """The actuator's control value for a gripper target in the bench's units (0 open, 0.8 closed)."""
    return min(max(float(target), 0.0), TARGET_CLOSED) / TARGET_CLOSED * 2.0 * dims.travel


def wrist_camera(dims: Dims = DIMS) -> dict:
    """The wrist camera in the frame of `palm`, as `RobotSpec.wrist_camera` gives one: beside the housing, looking
    past the fingertips at a point on the tool axis; the image's upper edge is on the side away from the fingers."""
    return {"pos": [round(v, 6) for v in dims.camera_pos], "target": [round(v, 6) for v in dims.camera_target],
            "up": [1.0, 0.0, 0.0], "fovy": dims.camera_fovy}


def free_distance(m: mujoco.MjModel, d: mujoco.MjData, prefix: str = "") -> float:
    """Free distance between the two pads' faces along the closing direction (m), as `World.gripper_opening` reads it."""
    a, b = m.geom(prefix + "pad_left").id, m.geom(prefix + "pad_right").id
    y = d.site_xmat[m.site(prefix + "pinch").id].reshape(3, 3)[:, 1]
    return float(abs(np.dot(d.geom_xpos[a] - d.geom_xpos[b], y)) - 2.0 * m.geom_size[a][1])


def opening_table(dims: Dims = DIMS, targets=(0.0, 0.2, 0.4, 0.6, 0.8), seconds: float = 1.0) -> tuple:
    """((gripper target, free distance between the pads), ...), measured on the model: the gripper alone, each target
    held for `seconds` by its actuator."""
    m = spec(dims).compile()
    d = mujoco.MjData(m)
    out = []
    for t in targets:
        d.ctrl[0] = ctrl_of(t, dims)
        for _ in range(int(round(seconds / m.opt.timestep))):
            mujoco.mj_step(m, d)
        out.append((float(t), round(free_distance(m, d), 5)))
    return tuple(out)


def describe(dims: Dims = DIMS) -> dict:
    """What a robot spec has to say about this hand, read off the compiled model where it can be."""
    m = spec(dims).compile()
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    palm = m.body("palm").id
    com = d.subtree_com[palm] - d.xpos[palm]
    pads = {s: m.geom(f"pad_{s}").id for s in ("left", "right")}
    # the rotational inertia of the whole gripper about its centre of mass, in the palm's frame
    inertia = np.zeros((3, 3))
    for b in range(1, m.nbody):
        rot = d.ximat[b].reshape(3, 3)
        r = d.xipos[b] - d.subtree_com[palm]
        inertia += rot @ np.diag(m.body_inertia[b]) @ rot.T + m.body_mass[b] * (np.dot(r, r) * np.eye(3) - np.outer(r, r))
    table = opening_table(dims)
    return {
        "frame": "palm: origin in the middle of the mounting face; +z out of the hand, +y the closing direction, +x the camera side",
        "bodies": ["palm", "finger_left", "finger_right"], "joints": ["finger_left", "finger_right"],
        "actuator": "grip", "tendon": "grip", "equality": "fingers",
        "pads": {"left": ["pad_left"], "right": ["pad_right"]}, "sites": {"mount": [0.0, 0.0, 0.0],
                                                                         "pinch": [0.0, 0.0, round(dims.pinch, 5)],
                                                                         "camera": [round(v, 5) for v in dims.camera_pos]},
        "mass_kg": round(float(m.body_subtreemass[palm]), 4),
        "mass_parts_kg": {"palm": round(float(m.body_mass[palm]), 4), "finger": round(float(m.body_mass[m.body('finger_left').id]), 4)},
        "centre_of_mass_in_palm": [round(float(v), 5) for v in com],
        "inertia_about_com_kg_m2": [round(float(v), 7) for v in np.diag(inertia)],
        "length_to_fingertips_m": round(dims.tip, 5), "pinch_from_mount_m": round(dims.pinch, 5), "tip_reach_m": round(dims.tip_reach, 5),
        "housing_m": [round(2 * v, 4) for v in dims.housing_half],
        "width_across_open_fingers_m": round(2.0 * (dims.opening / 2.0 + dims.pad_thickness + 2.0 * dims.finger_half[1]), 4),
        "pad_face_m": [round(2 * dims.pad_half_width, 4), round(2 * dims.pad_half_length, 4)],
        "pad_half_thickness_m": round(float(m.geom_size[pads["left"]][1]), 5),
        "pad_friction": list(dims.pad_friction),
        "finger_travel_m": round(dims.travel, 5), "ctrl_open": 0.0, "ctrl_closed": round(2.0 * dims.travel, 5),
        "driver_map": [[round(TARGET_CLOSED / dims.travel, 4), 0.0]] * 2,
        "opening_table": [list(r) for r in table],
        "grip_force_N": dims.grip_force, "kp_N_per_m": dims.kp, "kv_N_s_per_m": dims.kv,
        "wrist_camera": wrist_camera(dims),
    }


def bench_options(s: mujoco.MjSpec) -> None:
    """The physics options the bench world runs with (`embodied_safety_exam.sim.world.World._build`): 2 ms steps, the implicit-fast
    integrator, elliptic friction cones with `impratio` 10 (which is what keeps a thing held between two pads from
    creeping), Newton's solver. A model that is meant to behave as it will in the world is compiled with these."""
    s.option.timestep = 0.002
    s.option.integrator = mujoco.mjtIntegrator.mjINT_IMPLICITFAST
    s.option.cone = mujoco.mjtCone.mjCONE_ELLIPTIC
    s.option.impratio = 10.0
    s.option.solver = mujoco.mjtSolver.mjSOL_NEWTON
    s.option.iterations = 100
    s.option.tolerance = 1e-8


# ---- pictures ---------------------------------------------------------------------------------------------------------------
def _look_at(pos, target, up=(0.0, 0.0, 1.0)) -> np.ndarray:
    pos, target, up = (np.asarray(v, dtype=np.float64) for v in (pos, target, up))
    f = (target - pos) / np.linalg.norm(target - pos)
    r = np.cross(f, up)
    r /= np.linalg.norm(r)
    quat = np.zeros(4)
    mujoco.mju_mat2Quat(quat, np.stack([r, np.cross(r, f), -f], axis=1).flatten())
    return quat


def picture_model(dims: Dims = DIMS, with_block: bool = False) -> mujoco.MjModel:
    """The gripper hanging fingers down over a floor (its mounting face 0.30 m up), with cameras round it; with
    `with_block` a free 40 mm cube of 0.2 kg stands on a post between the pads (the post sinks away on `post` = 1)."""
    s = mujoco.MjSpec()
    bench_options(s)
    s.visual.global_.offwidth, s.visual.global_.offheight = 1280, 960
    s.visual.headlight.ambient = [0.35, 0.35, 0.35]
    s.visual.headlight.diffuse = [0.5, 0.5, 0.5]
    wb = s.worldbody
    wb.add_geom(name="floor", type=mujoco.mjtGeom.mjGEOM_PLANE, size=[1, 1, 0.1], rgba=[0.74, 0.72, 0.68, 1])
    wb.add_light(pos=[0.3, -0.5, 1.0], dir=[-0.3, 0.5, -1.0], diffuse=[0.5, 0.5, 0.5])
    # fingers down: the gripper's +z is the world's -z, its +y the world's +y
    frame = wb.add_frame(pos=[0.0, 0.0, 0.30], quat=[0.0, 0.0, 1.0, 0.0])
    s.attach(spec(dims), frame=frame, prefix="g/")
    cam = wrist_camera(dims)
    s.body("g/palm").add_camera(name="wrist", pos=cam["pos"], quat=_look_at(cam["pos"], cam["target"], cam["up"]), fovy=cam["fovy"])
    mid = [0.0, 0.0, 0.30 - dims.tip / 2.0]
    for name, pos in (("side", [0.34, 0.0, 0.26]), ("front", [0.0, -0.34, 0.26]), ("below", [0.16, -0.20, 0.04]), ("above", [0.20, -0.16, 0.48])):
        wb.add_camera(name=name, pos=pos, quat=_look_at(pos, mid), fovy=38.0)
    if with_block:
        z = 0.30 - dims.pinch
        block = wb.add_body(name="block", pos=[0.0, 0.0, z])
        block.add_freejoint(name="block")
        block.add_geom(name="block", type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.02, 0.02, 0.02], mass=0.2, rgba=[0.80, 0.35, 0.15, 1],
                       friction=[0.8, 0.005, 0.0001])
        post = wb.add_body(name="post", pos=[0.0, 0.0, z - 0.02 - 0.05])
        post.add_joint(name="post", type=mujoco.mjtJoint.mjJNT_SLIDE, axis=[0, 0, -1], range=[0, 0.1])
        post.add_geom(name="post", type=mujoco.mjtGeom.mjGEOM_BOX, size=[0.03, 0.03, 0.05], mass=0.5, rgba=[0.5, 0.5, 0.5, 1])
        s.add_actuator(name="post", target="post", trntype=mujoco.mjtTrn.mjTRN_JOINT, gaintype=mujoco.mjtGain.mjGAIN_FIXED,
                       biastype=mujoco.mjtBias.mjBIAS_AFFINE, gainprm=[2000.0] + [0.0] * 9, biasprm=[0.0, -2000.0, -100.0] + [0.0] * 7)
    return s.compile()


def pictures(out, dims: Dims = DIMS) -> list[str]:
    """Open and closed from four sides and from its own camera; and holding a cube by friction alone."""
    from pathlib import Path

    from PIL import Image
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    m = picture_model(dims)
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, 480, 640)
    rows = []
    for target in (0.0, 0.4, 0.8):
        d.ctrl[m.actuator("g/grip").id] = ctrl_of(target, dims)
        for _ in range(500):
            mujoco.mj_step(m, d)
        tiles = []
        for c in ("side", "front", "below", "above", "wrist"):
            r.update_scene(d, camera=c)
            tiles.append(r.render().copy())
        rows.append(np.concatenate(tiles, axis=1))
    Image.fromarray(np.concatenate(rows, axis=0)).save(out / "gripper_views.png")
    files.append(str(out / "gripper_views.png"))
    r.close()
    m = picture_model(dims, with_block=True)
    d = mujoco.MjData(m)
    r = mujoco.Renderer(m, 480, 640)
    tiles = []
    for phase, grip, post, steps in (("open", 0.0, 0.0, 250), ("closed", 0.8, 0.0, 500), ("post gone", 0.8, 0.1, 1500)):
        d.ctrl[m.actuator("g/grip").id] = ctrl_of(grip, dims)
        d.ctrl[m.actuator("post").id] = post
        for _ in range(steps):
            mujoco.mj_step(m, d)
        r.update_scene(d, camera="front")
        tiles.append(r.render().copy())
        r.update_scene(d, camera="wrist")
        tiles.append(r.render().copy())
    Image.fromarray(np.concatenate(tiles, axis=1)).save(out / "gripper_holds.png")
    files.append(str(out / "gripper_holds.png"))
    r.close()
    return files


def main() -> None:
    import argparse
    import json
    from pathlib import Path
    ap = argparse.ArgumentParser(description="The drawn parallel gripper: its MJCF, its numbers, pictures.")
    ap.add_argument("--out", type=Path, default=Path("build/gripper"))
    ap.add_argument("--no-pictures", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "gripper_parallel.xml").write_text(mjcf())
    info = {"dims": asdict(DIMS), **describe()}
    if not args.no_pictures:
        info["pictures"] = pictures(args.out)
    (args.out / "gripper_parallel.json").write_text(json.dumps(info, indent=1) + "\n")
    print(json.dumps(info, indent=1))


if __name__ == "__main__":
    main()
