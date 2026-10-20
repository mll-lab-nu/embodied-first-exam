"""rcb_rfo.py -- RoboOlympics tooling for Embodied First Exam (docs/benchmarks/roboolympics.md).

One module, copied unchanged into every RoboOlympics task: the privileged environment (`Session`), the privileged
verifier (`replay`) and the standard sim service (`Episode`, driven by sim/server.py). The world is the `rfo` package
next to it (the RoboOlympics Unitree G1 or H1-2 in a sports venue, rfo/world.py) with the family's own rules,
`rfo_task.py`.

A control step is 10 ms (10 physics steps of 1 ms). An action is a row of one of the action types
(`Session.action_types`; the widths below are the G1's, 29 joints with a 3-joint waist; the H1-2 has 27 joints, a
1-joint waist and no running policy and no FALCON / AGILE, so no `run` / `run_arms` / `walk_falcon` / `walk_agile`):

    stand     waist 3 + arms 14 joint targets + grips 2                      the platform holds the legs in the stance
    walk      vx, vy, wz + waist 3 + arms 14 + grips 2                       Unitree's walking policy drives the legs
    run       vx, vy, wz + grips 2                                           the running policy drives all 29 joints
    run_arms  vx, vy, wz + arms 14 + grips 2                                 the running policy drives legs and waist
    walk_falcon / walk_agile  the walk row                                 FALCON's / AGILE's walking policy drives the legs
    joints    29 joint targets + grips 2                                     you drive every joint (default PD gains)
    lowcmd    29 x (q, dq, tau, kp, kd) + grips 2                            Unitree's LowCmd for every joint

Joint order (Unitree's SDK; the G1's, the H1-2 has waist yaw only): left leg 6 (hip pitch, roll, yaw, knee, ankle pitch, roll), right leg 6, waist yaw, roll,
pitch, left arm 7 (shoulder pitch, roll, yaw, elbow, wrist roll, pitch, yaw), right arm 7. grip_left / grip_right, per
hand: on a fist pad >= 0.5 closes that hand's grip (it holds an object whose surface is within 3.5 cm of the palm),
< 0.5 opens it; on a gripper (a family's real hand, rfo/realhand.py) it is the jaws' closure command, 0 open to 1 closed.

Python (privileged mode):
    from rcb_rfo import Session
    s = Session()                              # /app/instance.json
    s.action_types                             # name -> {dim, layout, lower, upper, meaning}
    s.hold()                                   # (type, row): keep the command in force, with zero velocity
    s.step("walk", row)                        # one control step; True when the episode is over. Recorded in s.rows
    s.done, s.status()                         # the referee: stages latched, success / failed, metrics, events
    s.world                                    # everything: s.world.m, s.world.d (MuJoCo), s.world.robot, s.world.ref
    s.state()                                  # the pelvis, the joints, the task's objects (privileged)
    s.image("head_left"), s.proprio()          # what the robot's own sensors give (the standard mode's observation)
    s.reset()                                  # back to the frozen start (unlimited); clears s.rows
    s.replay()                                 # what the verifier will do with s.rows, in a fresh world
    s.save_trajectory()                        # /app/output/trajectory.npz (the deliverable): s.rows as sim rows
CLI (the verifiers, make_instances.py):
    python rcb_rfo.py replay --instance instance.json --traj trajectory.npz --out r.json [--video replay.mp4]
    python rcb_rfo.py instance --family <family> --seed <seed> --out instance.json
"""
from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
SESSION_LOG = os.environ.get("RCB_SESSION_LOG", "/app/output/rcb_session_log.jsonl")
MAX_ROWS = 40000                 # a trajectory may hold at most this many rows (no episode is longer than 400 s)
IMAGE_HW = (270, 480)            # the cameras' default image: height, width (16:9, as the G1's head camera)


def load_instance(path) -> dict:
    with open(path) as f:
        return json.load(f)


class Episode:
    """One frozen RoboOlympics instance: the world, the action types, the sensors."""

    def __init__(self, instance: dict):
        from rfo import load_task
        from rfo import world as W

        self.W = W
        self.instance = instance
        self.family, self.seed = instance["family"], int(instance.get("seed", 0))
        self.world = W.World(load_task(self.family), instance)
        self.actions = W.Actions(self.world.robot)
        self.raw_dim = self.world.L.RAW_DIM
        self.control_dt = W.CONTROL_DT
        self.horizon = int(round(self.world.task.time_limit_s / W.CONTROL_DT))
        self.cameras = tuple(self.world.cameras)
        self.proprio_layout = list(self.world.proprio_layout)
        self.t0_sha = self.world.state_sha()

    # ------------------------------------------------------------------ episode
    def reset(self) -> None:
        self.world.reset()

    def instance_check(self, instance: dict) -> dict:
        """Is the world at t = 0 the instance's (the same scene, robot and referee, bit for bit)?"""
        want = instance.get("t0", {}).get("state_sha")
        return {"ok": want is None or want == self.t0_sha, "exact": want == self.t0_sha}

    @property
    def steps(self) -> int:
        return int(self.world.k)

    @property
    def done(self) -> bool:
        return bool(self.world.done)

    def clip(self, typ: str, rows) -> np.ndarray:
        return self.actions.clip(typ, rows)

    def to_raw(self, typ: str, row) -> np.ndarray:
        return self.actions.to_raw(typ, row, self.world)

    def step(self, typ: str, row) -> np.ndarray:
        """One control step of an agent row (clipped into the bounds). Returns the sim row that ran."""
        types = self.actions.types
        if typ not in types:
            raise ValueError(f"unknown action type {typ!r}; one of {list(types)}")
        row = np.asarray(row, dtype=np.float64)
        if row.shape != (types[typ]["dim"],) or not np.all(np.isfinite(row)):
            raise ValueError(f"a {typ} row is {types[typ]['dim']} finite floats ({', '.join(types[typ]['layout'])})")
        row = self.clip(typ, row)
        raw = self.to_raw(typ, row)
        self.step_raw(raw)
        return raw

    def step_raw(self, raw) -> bool:
        return self.world.step(raw)

    def hold(self) -> tuple[str, np.ndarray]:
        return self.actions.hold(self.world)

    def success(self) -> bool:
        return bool(self.world.success)

    def outcome(self) -> str | None:
        ref = self.world.ref
        return None if not ref.done else "success" if ref.success else ref.failed

    def state_sha(self) -> str:
        return self.world.state_sha()

    def verdict(self) -> dict:
        ref = self.world.ref
        return {"success": bool(ref.success), "done": bool(ref.done), "failed": ref.failed, "stages": list(ref.stages),
                "stages_total": len(self.world.task.stages), "progress": round(ref.progress(), 4),
                "metrics": dict(ref.metrics), "steps": self.steps, "time_s": round(self.world.t, 2)}

    # ------------------------------------------------------------------ sensors
    def image(self, camera: str, h: int | None = None, w: int | None = None, depth: bool = False) -> np.ndarray:
        if camera not in self.cameras:
            raise ValueError(f"cameras: {self.cameras}")
        return self.world.render(camera, w or IMAGE_HW[1], h or IMAGE_HW[0], depth=depth)

    def proprio(self) -> np.ndarray:
        return self.world.proprio()

    def camera_facts(self) -> dict:
        """Each camera now: its position and axes in the robot's starting frame (origin on the floor under the pelvis
        at t = 0, x the way it faced, y left, z up), its field of view, what it is mounted on."""
        import mujoco

        w = self.world
        m, d = w.m, w.d
        mujoco.mj_forward(m, d)
        x0, y0, yaw0 = w.task.start
        c, s = np.cos(yaw0), np.sin(yaw0)
        Y = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
        r4 = lambda v: [round(float(x), 4) for x in v]  # noqa: E731
        out = {}
        for cam in self.cameras:
            i = m.camera(cam).id
            R = d.cam_xmat[i].reshape(3, 3)       # MuJoCo camera: looks down -z, +y up, +x right
            out[cam] = {"mounted": "head" if cam.startswith("head") else "venue (fixed)", "fovy_deg": float(m.cam_fovy[i]),
                        "position_m": r4(Y.T @ (d.cam_xpos[i] - [x0, y0, 0.0])), "forward": r4(Y.T @ -R[:, 2]),
                        "up": r4(Y.T @ R[:, 1]), "right": r4(Y.T @ R[:, 0])}
        return out

    def robot_facts(self) -> dict:
        """The robot's own description: the joints (order, range, speed and torque limits, default gains, the stance
        and rest pose), its mass, the control rates."""
        r, W = self.world.robot, self.W
        r4 = lambda v: [round(float(x), 4) for x in v]  # noqa: E731
        L, info = r.L, r.info
        facts = {"name": r.name, "title": info["title"], "revision": r.B.revision,
                 "model": f"{info['title']}, {L.NJ} joints, {info['height_m']:g} m, {r.mass:.0f} kg (RoboOlympics robot "
                          f"library {r.B.revision}: {info['source']})",
                 "joints": [j[:-6] for j in L.JOINTS], "n_legs": 12, "n_waist": L.NW, "n_arms": 14,
                 "range_rad": [r4(x) for x in zip(r.lo, r.hi)],
                 "speed_limit_rad_s": r4(r.speed), "torque_limit_nm": r4(r.tau_max),
                 "default_kp": r4(r.kp0), "default_kd": r4(r.kd0), "kp_max": r4(r.kp_max), "kd_max": r4(r.kd_max),
                 "stance_legs_rad": r4(r.stance), "rest_upper_rad": r4(r.rest[12:]), "mass_kg": round(r.mass, 2),
                 "height_m": info["height_m"], "pelvis_height_standing_m": round(r.stand_z, 3),
                 "control_dt_s": W.CONTROL_DT, "physics_dt_s": W.PHYS_DT, "walk_command_max": r4(r.arb.cmd_max),
                 "run_command_range": [r4(x) for x in W.RUN_CMD] if r.has_run else None,
                 "grip": {"reach_m": W.GRIP_REACH, "max_relative_speed_m_s": W.GRIP_SPEED,
                          "rule": "a closed grip holds the nearest grippable object whose surface is within reach_m of "
                                  "the palm (a point 4.5 cm beyond the wrist flange along the forearm) and that moves "
                                  "no faster than max_relative_speed_m_s relative to it; opening the grip lets it go"}}
        if self.world.hands:                      # a real hand (rfo/realhand.py): only in the families that have one
            facts["real_hands"] = self.world.hands.facts()
            pads = [s for s in ("left", "right") if s not in self.world.real_hands]
            if pads:                              # the weld grip is the pad sides' only
                facts["grip"]["sides"] = pads
            else:
                del facts["grip"]
        return facts

    def close(self) -> None:
        self.world.close()


def replay(instance: dict, rows, video: str | None = None, camera: str | None = None) -> dict:
    """The sim rows from the frozen start in this process's own fresh world, until the referee ends the episode or
    the rows run out. success = the referee's verdict there (a success is latched the moment it happens and ends the
    episode, so the rows must reach it)."""
    t = time.time()
    ep = Episode(instance)
    check = ep.instance_check(instance)
    rows = np.asarray(rows, dtype=np.float64)
    if rows.ndim != 2 or rows.shape[1] != ep.raw_dim:
        raise ValueError(f"rows must be (T, {ep.raw_dim}), got {list(rows.shape)}")
    frames, every = [], 4
    cam = camera or ("venue" if "venue" in ep.cameras else ep.cameras[0])

    def film():
        if video and ep.steps % every == 0:
            frames.append(ep.image(cam, 360, 640))

    n, bad_row = 0, None
    film()
    for row in rows:
        if ep.done:
            break
        try:
            ep.step_raw(row)
        except ValueError as exc:                  # not a sim row (its mode): the trajectory ends here, as it stands
            bad_row = f"row {n}: {exc}"
            break
        n += 1
        film()
    out = {**ep.verdict(), "state_sha": ep.state_sha(), "instance_ok": check["ok"], "executed_rows": n, "bad_row": bad_row,
           "episode_over": ep.done, "outcome": ep.outcome(), "horizon": ep.horizon, "events": ep.world.ref.events[-200:],
           "replay_s": round(time.time() - t, 2), "video": False}
    if video and frames:
        try:
            import imageio.v2 as imageio

            imageio.mimsave(video, frames, fps=round(1.0 / (every * ep.control_dt)), macro_block_size=1)
            imageio.imwrite(video[: -len(".mp4")] + ".last.png", frames[-1])
            out["video"] = os.path.isfile(video) and os.path.getsize(video) > 0
        except Exception as exc:  # noqa: BLE001 -- the video never decides anything
            out["video_error"] = repr(exc)[:200]
    ep.close()
    return out


def read_trajectory(path: str, raw_dim: int, max_rows: int = MAX_ROWS) -> tuple[np.ndarray, str | None]:
    """(actions, family) of a trajectory.npz, refusing a file that would unpack to more than max_rows rows (a small
    compressed file can hold gigabytes) or that is not what save_trajectory writes. Raises ValueError."""
    import zipfile

    limit = max_rows * raw_dim * 8 + (1 << 16)
    try:
        with zipfile.ZipFile(path) as z:
            infos = {i.filename: i for i in z.infolist()}
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"not an .npz file: {exc}") from None
    if "actions.npy" not in infos:
        raise ValueError("no `actions` array")
    if sum(i.file_size for i in infos.values()) > limit:
        raise ValueError(f"the file unpacks to more than {limit} bytes ({max_rows} rows of {raw_dim} float64)")
    try:
        with np.load(path, allow_pickle=False) as d:
            acts = np.asarray(d["actions"], dtype=np.float64)
            family = str(d["family"]) if "family" in d.files else None
    except Exception as exc:  # noqa: BLE001 -- any unreadable member
        raise ValueError(f"unreadable .npz: {exc!r}"[:200]) from None
    if acts.ndim != 2 or acts.shape[1] != raw_dim:
        raise ValueError(f"`actions` must be (T, {raw_dim}), got {list(acts.shape)}")
    return acts, family


def save_trajectory(rows, family: str, path: str = "/app/output/trajectory.npz", raw_dim: int | None = None) -> None:
    rows = np.asarray(rows, dtype=np.float64)
    rows = rows.reshape(-1, raw_dim) if raw_dim else np.atleast_2d(rows)
    if len(rows) > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} rows")
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".partial.npz"                  # written whole, then renamed: a killed writer never leaves a broken file
    np.savez(tmp, actions=rows, family=family)
    os.replace(tmp, path)


class Session:
    """Privileged mode: the frozen instance with unlimited resets, logged to /app/output/rcb_session_log.jsonl."""

    def __init__(self, instance: str = "/app/instance.json"):
        self.instance = load_instance(instance)
        self.ep = Episode(self.instance)
        atexit.register(self.close)
        if not self.ep.instance_check(self.instance)["ok"]:
            raise RuntimeError("this environment does not rebuild the frozen instance's starting state")
        self.rows: list[np.ndarray] = []
        self.typed: list[tuple[str, np.ndarray]] = []     # the same steps as (action type, row), where they were typed
        self._log({"ev": "session_start", "family": self.ep.family})

    @property
    def world(self):
        return self.ep.world

    @property
    def action_types(self) -> dict:
        return self.ep.actions.spec()

    @property
    def done(self) -> bool:
        return self.ep.done

    def reset(self) -> None:
        self._log({"ev": "reset", "sim_steps": self.ep.steps})
        self.ep.reset()
        self.rows, self.typed = [], []

    def step(self, typ: str, row) -> bool:
        row = self.ep.clip(typ, np.asarray(row, dtype=np.float64))
        self.rows.append(self.ep.step(typ, row))
        self.typed.append((typ, row))
        return self.ep.done

    def step_raw(self, raw) -> bool:
        raw = np.asarray(raw, dtype=np.float64)
        self.ep.step_raw(raw)
        self.rows.append(raw.copy())
        return self.ep.done

    def hold(self):
        return self.ep.hold()

    def status(self) -> dict:
        return {**self.ep.verdict(), "events": list(self.world.ref.events), "state_sha": self.ep.state_sha()}

    def state(self) -> dict:
        w = self.world
        r = w.robot
        return {"time_s": w.t, "pelvis_xyz_yaw": w.pelvis().tolist(), "com": w.com().tolist(),
                "q": w.d.qpos[r.qadr].tolist(), "dq": w.d.qvel[r.vadr].tolist(), "q_target": r.arb.target().tolist(),
                "held": dict(w.held), "left_palm": w.d.site_xpos[r.palm["left"]].tolist(),
                "right_palm": w.d.site_xpos[r.palm["right"]].tolist(), "task": w.task.privileged(w),
                **({"real_hands": w.hands.state()} if w.hands else {})}

    def image(self, camera: str, h: int | None = None, w: int | None = None, depth: bool = False):
        return self.ep.image(camera, h, w, depth)

    def proprio(self):
        return self.ep.proprio()

    def replay(self, rows=None) -> dict:
        """What the verifier will do with these rows (default: s.rows), here, in a fresh world."""
        rows = self.rows if rows is None else rows
        self._log({"ev": "replay", "rows": int(len(rows))})
        return replay(self.instance, np.asarray(rows, dtype=np.float64).reshape(-1, self.ep.raw_dim))

    def save_trajectory(self, rows=None, path: str = "/app/output/trajectory.npz") -> None:
        save_trajectory(self.rows if rows is None else rows, self.ep.family, path, raw_dim=self.ep.raw_dim)

    def close(self) -> None:
        self.ep.close()

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


def make_instance(family: str, seed: int = 0, params: dict | None = None) -> dict:
    """instance.json for a family: what the tasks rebuild, the texts and the numbers they quote."""
    import mujoco
    from rfo import load_task
    from rfo import world as W

    task = load_task(family)
    task.configure(params or {})
    inst = {"family": family, "seed": int(seed), "params": dict(task.p)}
    ep = Episode(inst)
    w = ep.world
    fill = {**task.p, "time_limit_s": f"{task.time_limit_s:g}"}
    typ, row = ep.hold()
    inst.update({
        "title": task.title, "category": task.category, "time_limit_s": task.time_limit_s, "stages": list(task.stages),
        "rulebook": task.rulebook.format(**fill), "deviations": [d.format(**fill) for d in task.deviations],
        "texts": {"sentence": task.sentence.format(**fill), "rules": task.rules.format(**fill),
                  "venue": task.venue.format(**fill), "difficulty": task.difficulty.format(**fill)},
        "robot": w.robot.name,
        "sim": {"robot": f"{w.robot.name}@{w.robot.B.revision}", "mujoco": mujoco.__version__},
        "t0": {"state_sha": ep.t0_sha, "control_dt": ep.control_dt, "horizon_steps": ep.horizon, "raw_dim": ep.raw_dim,
               "action_types": ep.actions.spec(), "hold": {"type": typ, "row": [round(float(x), 4) for x in row]},
               "proprio_layout": ep.proprio_layout, "cameras": ep.camera_facts(), "robot": ep.robot_facts(),
               "grippable": sorted(w.grippables), "pelvis": [round(float(x), 4) for x in w.pelvis()]},
    })
    ep.close()
    return inst


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="RoboOlympics tooling: replay a trajectory, or write a frozen instance")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay")
    r.add_argument("--instance", required=True)
    r.add_argument("--traj", required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--video")
    i = sub.add_parser("instance")
    i.add_argument("--family", required=True)
    i.add_argument("--seed", type=int, default=0)
    i.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "instance":
        with open(a.out, "w") as f:
            json.dump(make_instance(a.family, a.seed), f, indent=1)
            f.write("\n")
        return 0
    inst = load_instance(a.instance)
    acts, _ = read_trajectory(a.traj, int(inst["t0"]["raw_dim"]))
    acts = acts[: int(inst["t0"]["horizon_steps"])]            # rows past the episode's length are never used
    Session._log({"ev": "replay", "rows": int(len(acts)), "cli": True})   # off in the verifiers (RCB_SESSION_LOG="")
    result = replay(inst, acts, a.video)
    with open(a.out, "w") as f:
        json.dump(result, f)
    print(json.dumps({k: v for k, v in result.items() if k != "events"}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
