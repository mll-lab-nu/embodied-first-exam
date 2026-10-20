"""rcb_bigym2.py -- BiGym 2.0 tooling for Embodied First Exam (docs/benchmarks/bigym2.md).

One module, copied unchanged into every BiGym 2.0 task: the privileged environment (`Session`), the privileged
verifier (`replay`) and the standard / standard-realtime sim service (`Episode`, driven by sim/server.py). Everything
that decides the outcome is upstream code (bigym 1.0.0 at 93ad4b3: MuJoCo 3.8.1 on the CPU, NVIDIA's GR00T-WBC lower
body on onnxruntime, CPU):

- the frozen instance (instance.json) is the task's official configuration, `bigym.loco.make(task)`, reset with the
  instance's seed: upstream's deterministic reset, its 200-step controller warm-up included. Every load checks it
  against instance.json: the same scene exactly, and the same state exactly or, where this CPU's onnxruntime kernels
  round the controller differently, every joint within INSTANCE_TOL (upstream's own golden-test tolerance);
- one control step (50 Hz) = one upstream env step of a physical action, through upstream's own coding-agent action
  contract (`bigym.loco.agent.envtools.EnvTools.step`: physical units, clipped into the action bounds);
- the episode ends where upstream ends it: the task's success held for 1 s, a task failure (an object on the floor,
  a gripper on the sandwich, the pelvis 10 m away), a physics error, or the task's horizon. A fall does not end it;
- success = upstream's `bigym.loco.eval.is_success`: the task reported success and the robot never fell.

Action rows (`layout` in instance.json, 20 or 21 floats): vx, vy (m/s, body frame), height (pelvis height command, m),
wz (rad/s), [pitch (torso lean, rad, + forward): 11 of the 13 tasks], 7 left-arm then 7 right-arm joint targets (rad),
left gripper, right gripper (0 open .. 1 closed).

Python (privileged mode):
    from rcb_bigym2 import Session
    s = Session("/app/instance.json")       # a few seconds: scene build + the controller's warm-up
    s.layout, s.hold_row(), s.step(row)     # the row layout, the row that stands still (the last command, zero
                                            # vx, vy, wz; at t = 0 upstream's hold), one control step
    s.done, s.status()                      # upstream's episode end; success / outcome / steps / horizon / state hash
    s.task                                  # BiGym's task env (s.tools.inner): its props (s.task.cup, ...), s.task.robot
    s.env, s.tools, s.model, s.data         # the env wrapper steps go through, upstream's EnvTools, MuJoCo model and data
    s.tools.ik(left_pos=p, right_pos=q)     # upstream's IK: 14 arm targets (left 7, right 7) putting each gripper's
                                            # *_end_effector site (between its finger pads) at a world point
    s.image(cam, h, w), s.proprio()         # an onboard camera's RGB image (84 px by default, up to 640); upstream's
                                            # low-dimensional observation
    s.held(obj)                             # upstream's "held" of an object, per gripper
    s.reset()                               # back to the frozen instance (unlimited)
    s.replay(rows); s.save_trajectory(rows, "/app/output/trajectory.npz")
CLI (the verifiers, make_instances.py):
    python rcb_bigym2.py replay --instance instance.json --traj trajectory.npz --out r.json [--video replay.mp4]
    python rcb_bigym2.py instance --task <task> --seed <seed> --out instance.json
"""

import argparse
import atexit
import hashlib
import json
import os
import sys
import time

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("HF_HUB_OFFLINE", "1")  # the demonstrations are never part of a task

import numpy as np  # noqa: E402

CAMERAS = ("head", "left_wrist", "right_wrist")  # the robot's own cameras, in the order of upstream's agent CLI
INSTANCE_TOL = 5e-4  # m / rad: upstream's tests/test_substrate_golden.py TOLERANCE ("a stand-in for CPU kernel differences")
VELOCITIES = ("vx", "vy", "wz")
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")


def load_instance(path) -> dict:
    with open(path) as f:
        return json.load(f)


def _sha(arrays) -> str:
    h = hashlib.sha1()
    for a in arrays:
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


class Episode:
    """One frozen BiGym 2.0 instance, stepped through upstream's EnvTools. `image_hw` caps onboard images."""

    def __init__(self, instance: dict, image_hw: int = 84, image_cap: int | None = None):
        from bigym.loco.agent.cli import EnvToolsConfig
        from bigym.loco.agent.envtools import EnvTools

        self.instance = instance
        self.task, self.seed = instance["task"], int(instance["seed"])
        # interface="tools" only unlocks upstream's helper methods (camera calibration, IK) on this wrapper; the env,
        # its observations and its physics are the same official configuration either way.
        cap = int(image_cap or image_hw)  # the largest onboard image image() may return
        self.tools = EnvTools(self.task, EnvToolsConfig(interface="tools", image_cap=f"{cap}x{cap}"))
        self.env = self.tools.env
        self.image_hw = int(image_hw)
        slot = self.tools._slot
        base = sorted(slot, key=slot.get)
        self.layout = base + list(self.tools.limb_names) + ["left_gripper", "right_gripper"]
        self.action_dim = len(self.layout)
        if self.action_dim != self.tools.action_dim:
            raise RuntimeError(f"action layout {self.layout} does not match upstream's {self.tools.action_dim} slots")
        self.lo = np.asarray(self.tools.raw_low, dtype=np.float64)
        self.hi = np.asarray(self.tools.raw_high, dtype=np.float64)
        self.control_dt = float(self.tools.control_dt)
        self.horizon = int(self.tools.time_limit)
        self.reset()
        self.proprio_layout = self._proprio_layout()

    # ------------------------------------------------------------------ episode
    def reset(self) -> None:
        self.ts = self.tools.reset(self.seed)
        self.last_row = None  # the last command executed (clipped), for hold_row()
        self.t0_sha = self.state_sha()
        self.t0_scene_sha = self.scene_sha()
        self.t0_qpos = np.asarray(self.data.qpos, dtype=np.float64).copy()

    def instance_check(self, instance: dict) -> dict:
        """Is the state just after reset the instance's? exact: bit for bit; ok: exact, or the same scene with every
        joint within INSTANCE_TOL (another CPU's kernels; replays on this host are still bit-exact among themselves)."""
        t0 = instance["t0"]
        exact = self.t0_sha == t0["state_sha"]
        dev = float(np.max(np.abs(self.t0_qpos - np.asarray(t0["qpos"])))) if len(t0.get("qpos", [])) == len(self.t0_qpos) else np.inf
        ok = exact or (self.t0_scene_sha == t0.get("scene_sha") and dev <= INSTANCE_TOL)
        return {"ok": bool(ok), "exact": bool(exact), "max_joint_dev": dev}

    @property
    def model(self):
        return self.tools.model

    @property
    def data(self):
        return self.tools.data

    @property
    def steps(self) -> int:
        return int(self.tools.step_count)

    @property
    def done(self) -> bool:
        return bool(self.ts.last())

    def step(self, row) -> bool:
        """One control step of a physical action row (clipped into the bounds, as upstream does); True when upstream
        ended the episode."""
        if self.done:
            raise RuntimeError("the episode is over")
        row = np.asarray(row, dtype=np.float64)
        if row.shape != (self.action_dim,) or not np.all(np.isfinite(row)):
            raise ValueError(f"a row is {self.action_dim} finite floats ({', '.join(self.layout)})")
        row = self.clip(row).astype(np.float32)
        self.ts = self.tools.step(row)
        self.last_row = row.astype(np.float64)
        return self.done

    def success(self) -> bool:
        from bigym.loco.eval import is_success

        return bool(is_success(self.env))

    def outcome(self) -> str | None:
        """upstream's label of a finished episode: success, fell, timeout, terminated or physics_error."""
        return self.env.episode_termination() if self.done else None

    def fell(self) -> bool:
        return bool(self.env.episode_fell())

    def scene_sha(self) -> str:
        """Where reset put the scene's props (racks, targets, the robot's spawn): the model's poses, which the seed
        alone decides."""
        m, d = self.model, self.data
        return _sha([m.body_pos, m.body_quat, d.mocap_pos, d.mocap_quat])

    def state_sha(self) -> str:
        """Every MuJoCo state array, the props reset places on the model (racks, targets), and the lower-body
        controller's mutable state (its observation history, last actions, gait clock)."""
        d, m = self.data, self.model
        lb = self.env.get_lowerbody_state()
        return _sha(
            [d.qpos, d.qvel, d.act, d.ctrl, d.mocap_pos, d.mocap_quat, m.body_pos, m.body_quat]
            + [np.asarray(lb[k]) for k in sorted(lb)]
        )

    def hold_row(self) -> np.ndarray:
        """Stand still: the last command with zero walking and turning velocity (its height, lean, arm and gripper
        targets kept); before any command, upstream's hold action."""
        if self.last_row is None:
            return np.asarray(self.tools.hold_action(), dtype=np.float64)
        row = self.last_row.copy()
        for name in VELOCITIES:
            row[self.layout.index(name)] = 0.0
        return row

    def clip(self, row) -> np.ndarray:
        return np.clip(np.asarray(row, dtype=np.float64), self.lo, self.hi)

    # ------------------------------------------------------------------ sensors
    def image(self, camera: str, h: int | None = None, w: int | None = None) -> np.ndarray:
        if camera not in CAMERAS:
            raise ValueError(f"cameras: {CAMERAS}")
        return self.tools.image(camera, w or self.image_hw, h or self.image_hw)

    def proprio(self) -> np.ndarray:
        """upstream's low-dimensional observation (the learned policies' and upstream agents' proprioception)."""
        return np.asarray(self.ts.low_dim_obs, dtype=np.float32)

    def _proprio_layout(self) -> list[str]:
        outer, robot = self.tools.outer, self.tools.robot
        names = [j.name.removeprefix(robot.namespace) for j in robot.joints]
        keep = getattr(outer, "_proprio_keep_qpos_idx", None)
        joints = [names[i] for i in keep] if keep is not None else names
        layout = [f"{j}_pos" for j in joints] + [f"{j}_vel" for j in joints]
        layout += ["left_gripper_state", "right_gripper_state"]
        layout += ["pelvis_x", "pelvis_y", "pelvis_z", "pelvis_yaw"]
        n = len(self.proprio())
        if len(layout) != n:
            raise RuntimeError(f"proprio layout has {len(layout)} names for {n} values")
        return layout

    def camera_mounts(self) -> dict:
        """Each onboard camera's pose in the pelvis frame now (x forward, y left, z up), and its field of view."""
        info = self.tools.camera_info()
        pos, quat = self.tools.pelvis_pose()
        yaw = float(np.arctan2(2 * (quat[0] * quat[3] + quat[1] * quat[2]), 1 - 2 * (quat[2] ** 2 + quat[3] ** 2)))
        c, s = np.cos(yaw), np.sin(yaw)
        Y = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        r3 = lambda v: [round(float(x), 4) for x in v]  # noqa: E731
        out = {}
        for cam in CAMERAS:
            R = np.asarray(info[cam]["rot"], dtype=np.float64)  # MuJoCo camera: looks down -z, +y up, +x right
            out[cam] = {
                "fovy_deg": float(info[cam]["fovy_deg"]),
                "position_m": r3(Y.T @ (np.asarray(info[cam]["pos"]) - [pos[0], pos[1], 0.0])),
                "forward": r3(Y.T @ -R[:, 2]),
                "up": r3(Y.T @ R[:, 1]),
                "right": r3(Y.T @ R[:, 0]),
            }
        return out

    def robot_facts(self) -> dict:
        """What the robot's own description (its URDF) gives, read off the model with every joint at 0, in the pelvis
        frame (x forward, y left, z up): each arm, waist and finger joint's axis, a point on it and its range, and each
        onboard camera's mount on its link. The scene's props are not part of the robot: none of them is here."""
        import mujoco

        m, ns = self.model, self.tools.robot.namespace
        d = mujoco.MjData(m)
        d.qpos[:] = m.qpos0  # a scratch copy at the zero pose: the pelvis frame is the world frame there
        mujoco.mj_forward(m, d)
        r3 = lambda v: [round(float(x), 4) for x in v]  # noqa: E731
        names = [n[: -len("_pos")] for n in self.proprio_layout if n.endswith("_pos") and not n.startswith("pelvis_")]
        joints = {}
        for n in names:
            j = m.joint(ns + n).id
            joints[n] = {"type": "slide" if m.jnt_type[j] == mujoco.mjtJoint.mjJNT_SLIDE else "hinge",
                         "axis": r3(d.xaxis[j]), "position_m": r3(d.xanchor[j]), "range": r3(m.jnt_range[j]),
                         "link": m.body(int(m.jnt_bodyid[j])).name.removeprefix(ns)}
        cams = {}
        for c in CAMERAS:
            i = self.tools._cam_id(c)
            R = np.zeros(9)
            mujoco.mju_quat2Mat(R, m.cam_quat[i])
            R = R.reshape(3, 3)  # camera axes in its link's frame: it looks down -z, +y up, +x right
            cams[c] = {"link": m.body(int(m.cam_bodyid[i])).name.removeprefix(ns), "position_m": r3(m.cam_pos[i]),
                       "forward": r3(-R[:, 2]), "up": r3(R[:, 1]), "right": r3(R[:, 0]),
                       "fovy_deg": float(m.cam_fovy[i])}
        tcp = {}
        for side in ("left", "right"):  # the point between the finger pads (upstream's *_end_effector site)
            i = m.site(f"{ns}{side}_end_effector").id
            tcp[side] = {"link": m.body(int(m.site_bodyid[i])).name.removeprefix(ns), "position_m": r3(m.site_pos[i])}
        return {"frame": "the pelvis with every joint at 0: x forward, y left, z up (m)", "joints": joints,
                "grippers": tcp, "gripper_point": "each gripper's point between its finger pads, in its link's frame",
                "joint_sign": "a positive angle turns a hinge's child link about its axis by the right-hand rule (about an "
                              "axis near +y, left, a link hanging below the joint swings backward); a positive slide "
                              "moves its link along its axis",
                "camera_mounts": cams, "camera_mount_frame": "each camera's pose in its link's frame"}

    def close(self) -> None:
        for r in list(getattr(self.tools, "_img_renderers", {}).values()):  # the onboard images' own renderers
            try:
                r.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.tools.close()
        except Exception:  # noqa: BLE001
            pass


def replay(instance: dict, rows, video: str | None = None) -> dict:
    """The rows from the frozen instance in this process's own fresh environment, until upstream ends the episode
    or the rows run out. success = upstream's is_success at that point."""
    t = time.time()
    ep = Episode(instance)
    check = ep.instance_check(instance)
    rows = np.asarray(rows, dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] != ep.action_dim:
        raise ValueError(f"rows must be (T, {ep.action_dim}), got {list(rows.shape)}")
    if video:
        ep.tools.start_recording(video, every=2, fps=25)
    n = 0
    try:
        for row in rows:
            if ep.done:
                break
            ep.step(row)
            n += 1
    finally:
        if video:
            ep.tools.stop_recording()
    out = {
        "success": ep.success(),
        "state_sha": ep.state_sha(),
        "instance_ok": check["ok"],
        "instance_exact": check["exact"],
        "executed_rows": n,
        "episode_over": ep.done,
        "outcome": ep.outcome(),
        "fell": ep.fell(),
        "horizon": ep.horizon,
        "replay_s": round(time.time() - t, 2),
        "video": bool(video and os.path.isfile(video) and os.path.getsize(video) > 0),
    }
    ep.close()
    return out


def save_trajectory(rows, layout, task: str, path: str = "/app/output/trajectory.npz") -> None:
    rows = np.asarray(rows, dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] != len(layout):
        raise ValueError(f"rows must be (T, {len(layout)}), got {list(rows.shape)}")
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".partial.npz"  # written whole, then renamed: a killed writer never leaves a broken deliverable
    np.savez(tmp, actions=rows, layout=np.array(layout), task=task)
    os.replace(tmp, path)


class Session:
    """Privileged mode: the frozen instance with unlimited resets, logged to /app/output/rcb_session_log.jsonl."""

    def __init__(self, instance: str = "/app/instance.json", image_hw: int = 84, image_cap: int = 640):
        self.instance = load_instance(instance)
        self.ep = Episode(self.instance, image_hw=image_hw, image_cap=image_cap)
        atexit.register(self.close)  # free the GL contexts before the interpreter tears down
        if not self.ep.instance_check(self.instance)["ok"]:
            raise RuntimeError("this environment does not rebuild the frozen instance's starting state")
        self._log({"ev": "session_start", "task": self.ep.task})

    def reset(self) -> None:
        self._log({"ev": "reset", "sim_steps": self.ep.steps})
        self.ep.reset()

    def step(self, row) -> bool:
        return self.ep.step(row)

    @property
    def done(self) -> bool:
        return self.ep.done

    def status(self) -> dict:
        return {
            "success": self.ep.success(),
            "done": self.ep.done,
            "outcome": self.ep.outcome(),
            "fell": self.ep.fell(),
            "steps": self.ep.steps,
            "horizon": self.ep.horizon,
            "state_sha": self.ep.state_sha(),
        }

    def replay(self, rows) -> dict:
        """What the verifier will do with these rows, here, in a fresh environment."""
        self._log({"ev": "replay", "rows": int(len(rows))})
        return replay(self.instance, rows)

    def save_trajectory(self, rows, path: str = "/app/output/trajectory.npz") -> None:
        save_trajectory(rows, self.ep.layout, self.ep.task, path)

    def close(self) -> None:
        self.ep.close()

    def held(self, obj) -> dict:
        """Upstream's "held" for both grippers: {"left": bool, "right": bool} (a finger of that gripper touching obj)."""
        robot = self.ep.tools.inner.robot
        return {side.name.lower(): bool(robot.is_gripper_holding_object(obj, side)) for side in robot.grippers}

    @property
    def task(self):
        """BiGym's task env behind the wrapper (its props and robot)."""
        return self.ep.tools.inner

    def __getattr__(self, name):  # layout, hold_row, image, proprio, tools, env, model, data, ...
        if name == "ep":
            raise AttributeError(name)
        return getattr(self.ep, name)

    @staticmethod
    def _log(ev: dict) -> None:
        if not SESSION_LOG:
            return
        try:
            os.makedirs(os.path.dirname(SESSION_LOG), exist_ok=True)
            with open(SESSION_LOG, "a") as f:
                f.write(json.dumps({"t": round(time.time(), 2), **ev}) + "\n")
        except OSError:
            pass


def where(ep: "Episode", ref: str) -> str:
    """One object's place at t = 0, as a person would tell the robot: distance from the pelvis (horizontal), bearing
    from the robot's heading, height above the floor. ref: an attribute of BiGym's task env (`box`, `targets[0]`,
    `target_collider`), or for a fixture's part `body:`, `handle:`, `panel:` or `front:` + the body's name suffix."""
    env, m, d = ep.tools.inner, ep.model, ep.data
    kind, _, rest = ref.partition(":")
    if rest:
        b = next(i for i in range(m.nbody) if m.body(i).name.endswith(rest))
        geoms = [g for g in range(m.ngeom) if m.geom_bodyid[g] == b]
        if kind == "body":      # a part's own frame
            p = np.asarray(d.xpos[b])
        elif kind == "handle":  # a door's or drawer's handle: its (unnamed) child body
            p = np.asarray(d.xpos[next(i for i in range(m.nbody) if m.body_parentid[i] == b and i != b)])
        elif kind == "panel":   # the middle of a part's geometry (a door panel)
            p = np.mean([d.geom_xpos[g] for g in geoms], axis=0)
        elif kind == "front":   # a slab's top surface at its front edge (box geoms: a counter top), the robot facing +x
            corners = np.array([d.geom_xpos[g] + d.geom_xmat[g].reshape(3, 3) @ (m.geom_size[g] * c) for g in geoms
                                for c in ((sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1))])
            p = np.array([corners[:, 0].min(), float(d.xpos[b][1]), corners[:, 2].max()])
        else:
            raise ValueError(f"unknown place reference {ref!r}")
    else:
        attr, _, idx = ref.partition("[")
        obj = getattr(env, attr)
        obj = obj[int(idx.rstrip("]"))] if idx else obj
        p = np.asarray(obj.get_position() if hasattr(obj, "get_position") else d.bind(obj).xpos)
    pos, quat = ep.tools.pelvis_pose()
    yaw = float(np.arctan2(2 * (quat[0] * quat[3] + quat[1] * quat[2]), 1 - 2 * (quat[2] ** 2 + quat[3] ** 2)))
    dx, dy = p[0] - pos[0], p[1] - pos[1]
    fwd, left = dx * np.cos(yaw) + dy * np.sin(yaw), -dx * np.sin(yaw) + dy * np.cos(yaw)
    bearing = float(np.degrees(np.arctan2(left, fwd)))
    side = "straight ahead" if abs(bearing) < 10 else f"{abs(bearing):.0f}° to your {'left' if bearing > 0 else 'right'}"
    return f"about {np.hypot(fwd, left):.1f} m away, {side}, {p[2]:.2f} m above the floor"


def scene_text(ep: "Episode", scene: dict) -> str:
    return scene["text"].format(**{k: where(ep, ref) for k, ref in scene["objects"].items()})


def make_instance(task: str, seed: int, scene: dict | None = None) -> dict:
    """instance.json for (task, seed): what the tasks rebuild, and the numbers their texts quote."""
    import bigym

    ep = Episode({"task": task, "seed": seed})
    fp = ep.env.substrate_fingerprint()
    return {
        "task": task,
        "seed": int(seed),
        "scene": scene_text(ep, scene) if scene else "",
        "upstream": {"package": "bigym", "version": getattr(bigym, "__version__", "1.0.0"), "commit": "93ad4b3"},
        "substrate": {k: fp[k] for k in ("substrate_version", "mujoco_version") if k in fp},
        "t0": {
            "state_sha": ep.t0_sha,
            "scene_sha": ep.t0_scene_sha,
            "qpos": [float(x) for x in ep.t0_qpos],
            "layout": ep.layout,
            "action_dim": ep.action_dim,
            "lower": [round(float(x), 4) for x in ep.lo],
            "upper": [round(float(x), 4) for x in ep.hi],
            "hold": [round(float(x), 4) for x in ep.hold_row()],
            "horizon_steps": ep.horizon,
            "control_dt": ep.control_dt,
            "proprio_layout": ep.proprio_layout,
            "cameras": ep.camera_mounts(),
            "robot": ep.robot_facts(),
        },
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="BiGym 2.0 tooling: replay a trajectory, or write a frozen instance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--video")
    i = sub.add_parser("instance")
    i.add_argument("--task", required=True)
    i.add_argument("--seed", type=int, default=0)
    i.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "instance":
        with open(a.out, "w") as f:
            json.dump(make_instance(a.task, a.seed), f, indent=1)
            f.write("\n")
        return 0
    inst = load_instance(a.instance)
    d = np.load(a.traj, allow_pickle=False)
    Session._log({"ev": "replay", "rows": int(len(d["actions"])), "cli": True})  # off in the verifiers (RCB_SESSION_LOG="")
    result = replay(inst, d["actions"], a.video)
    with open(a.out, "w") as f:
        json.dump(result, f)
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
