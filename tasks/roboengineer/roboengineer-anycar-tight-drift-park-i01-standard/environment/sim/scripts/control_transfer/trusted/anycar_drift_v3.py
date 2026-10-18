"""Private drift-to-park rollout and adjudication; never install in agent image."""

import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
import numpy as np
from ..components.anycarbench.drift_v3 import DEFAULT_COURSE, DriftVehicle, route
from ..components.anycarbench.model import Diverged, mujoco
from ..control_public.anycar_drift_v3 import Controller, DT, HORIZON, validate, wrap
from .anycar import NOISE, plant_parameters
from ..anycar_drift_v3_spec import make_spec as make_spec


class Video:
    def __init__(self, v, out):
        if os.environ.get("MUJOCO_GL") != "osmesa":
            raise RuntimeError("OSMesa required")
        self.renderer = mujoco.Renderer(v.model, height=540, width=960)
        from OpenGL.GL import glGetString, GL_RENDERER

        self.gl_renderer = glGetString(GL_RENDERER).decode()
        if not any(k in self.gl_renderer.lower() for k in ("llvmpipe", "softpipe")):
            self.renderer.close()
            raise RuntimeError("Software GL required")
        self.camera = mujoco.MjvCamera()
        self.camera.azimuth = 90
        self.camera.elevation = -18
        self.camera.distance = 7.5
        self.camera.lookat[:] = [2, 0, 0.2]
        self.process = subprocess.Popen(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                "1920x540",
                "-r",
                "10",
                "-i",
                "-",
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-preset",
                "fast",
                "-crf",
                "21",
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )
        self.detail = mujoco.MjvCamera()
        self.detail.azimuth = 105
        self.detail.elevation = -20
        self.detail.distance = 1.8

    def frame(self, v, observation):
        self.renderer.update_scene(v.data, camera=self.camera)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
        overview = self.renderer.render().copy()
        self.detail.lookat[:] = [observation[0], observation[1], observation[11] + 0.1]
        self.renderer.update_scene(v.data, camera=self.detail)
        self.renderer.scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = False
        closeup = self.renderer.render().copy()
        self.process.stdin.write(np.concatenate([overview, closeup], axis=1).tobytes())

    def close(self):
        self.process.stdin.close()
        rc = self.process.wait(timeout=60)
        self.renderer.close()
        if rc:
            raise RuntimeError("ffmpeg failed")


class Monitor:
    def __init__(self, v, c):
        self.c = c
        self.path = route(c)
        self.gates = self.path[::5]
        self.gate = 0
        self.prev = v.state()[:2].copy()
        self.sliding = 0.0
        self.longest_slide = 0.0
        self.slip_distance = 0.0
        self.stopped = 0.0
        self.rollover = False
        self.offtrack = False
        self.collision = False
        self.sha = hashlib.sha256()
        self.max_slip = 0.0
        self.last_yaw = None
        self.rotation = 0.0
        self.sliding_rotation = 0.0

    def step(self, v):
        d = v.data
        s = v.state()
        x, y, yaw, vx, vy = s[:5]
        self.sha.update(
            np.asarray(
                np.r_[
                    d.time,
                    d.qpos,
                    d.qvel,
                    v.applied,
                    d.ctrl,
                    v.model.dof_frictionloss[v.rear_dofs],
                ],
                dtype="<f8",
            ).tobytes()
        )
        if (
            self.gate < len(self.gates)
            and np.linalg.norm(s[:2] - self.gates[self.gate]) < 0.28
        ):
            self.gate += 1
        finished = self.gate == len(self.gates)
        delta_yaw = 0.0
        if finished:
            if self.last_yaw is not None:
                delta_yaw = wrap(yaw - self.last_yaw)
                self.rotation += delta_yaw
            self.last_yaw = yaw
        slip = abs(math.atan2(vy, max(abs(vx), 0.01)))
        near = (
            abs(x - self.c["park_x"]) < 2.5
            and self.c["park_y"] - 0.8 < y < self.c["radius"] + 0.4
        )
        sliding = (
            finished
            and near
            and abs(vy) > 0.2
            and np.hypot(vx, vy) > 0.6
            and slip > math.radians(10)
        )
        self.sliding = self.sliding + 0.002 if sliding else 0.0
        self.longest_slide = max(self.longest_slide, self.sliding)
        if sliding:
            self.slip_distance += abs(vy) * 0.002
            self.sliding_rotation += delta_yaw
        if finished and near:
            self.max_slip = max(self.max_slip, slip if np.hypot(vx, vy) > 0.6 else 0.0)
        self.rollover |= bool(d.xmat[1].reshape(3, 3)[2, 2] < 0.5)
        self.collision |= v.collision
        # Approach stays near ordered U-course; parking area allows the lateral slide.
        distance = float(np.min(np.linalg.norm(self.path - s[:2], axis=1)))
        self.offtrack |= bool(
            (not finished and distance > 0.65) or abs(x) > 7 or abs(y) > 5
        )
        ex = abs(x - self.c["park_x"])
        ey = abs(y - self.c["park_y"])
        angle = abs(wrap(yaw - self.c["target_yaw"]))
        inside = (
            ex + 0.245 * abs(math.cos(yaw)) + 0.135 * abs(math.sin(yaw))
            < self.c["slot_length"] / 2
            and ey + 0.245 * abs(math.sin(yaw)) + 0.135 * abs(math.cos(yaw))
            < self.c["slot_width"] / 2
        )
        stopped = (
            finished
            and inside
            and ex < 0.18
            and ey < 0.12
            and angle < 0.14
            and np.hypot(vx, vy) < 0.08
            and abs(s[5]) < 0.1
        )
        self.stopped = self.stopped + 0.002 if stopped else 0.0

    def metrics(self, v):
        s = v.state()
        position = float(np.linalg.norm(s[:2] - [self.c["park_x"], self.c["park_y"]]))
        angle = abs(float(wrap(s[2] - self.c["target_yaw"])))
        rotation_ok = abs(abs(self.rotation) - math.pi) < 0.25
        drift = (
            self.longest_slide >= 0.15
            and self.slip_distance >= 0.06
            and rotation_ok
            and abs(self.sliding_rotation) >= math.radians(120)
        )
        unsafe = self.collision or self.rollover or self.offtrack or v.body_contact
        success = bool(not unsafe and drift and self.stopped >= 0.5)
        return dict(
            success=success,
            score=100 * math.exp(-position / 0.25 - angle / 0.3) if success else 0.0,
            route_complete=self.gate == len(self.gates),
            gate_fraction=self.gate / len(self.gates),
            drift_completed=bool(drift),
            rotation_completed=bool(rotation_ok),
            post_route_rotation_rad=self.rotation,
            drifting_rotation_rad=self.sliding_rotation,
            longest_slide_s=self.longest_slide,
            lateral_slide_m=self.slip_distance,
            max_sideslip_rad=self.max_slip,
            position_error_m=position,
            heading_error_rad=angle,
            stopped_for_s=self.stopped,
            collision=self.collision,
            rollover=self.rollover,
            offtrack=self.offtrack,
            body_contact=bool(v.body_contact),
            final_pose=s[:3].tolist(),
        )


def episode_parameters(seed):
    rng = np.random.default_rng(seed)
    c = dict(
        DEFAULT_COURSE,
        slot_length=float(rng.uniform(0.65, 0.73)),
        park_x=float(rng.uniform(-1.8, -1.6)),
        park_y=float(rng.uniform(1.05, 1.15)),
    )
    return c, float(rng.uniform(-0.02, 0.02)), float(rng.uniform(-0.01, 0.01))


def run(
    policy,
    course,
    plant,
    friction,
    brake_torque,
    out,
    noise_seed=123,
    render=False,
    start_y=0.0,
    start_yaw=0.0,
):
    canonical = validate(policy)
    v = DriftVehicle(course, plant, friction, brake_torque)
    v.reset(course.get("start_x", -3.0), -course["radius"] + start_y, start_yaw)
    monitor = Monitor(v, course)
    controller = Controller(policy, course)
    rng = np.random.default_rng(noise_seed)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    video = None
    if render:
        video = Video(v, out)
        video.camera.lookat[:] = [-0.8, 0, 0]
        video.camera.distance = 8.0
        video.camera.azimuth = 90
        video.camera.elevation = -70
        video.detail.distance = 2.0
        video.detail.elevation = -55
    rows = []
    monitor.step(v)
    try:
        diverged = False
        for i in range(round(HORIZON / DT) + 1):
            obs = v.state() + rng.normal(0, NOISE)
            action = controller.step(obs)
            if i % 5 == 0:
                rows.append(dict(t=i * DT, values=[*obs.tolist(), *action]))
                if video:
                    video.frame(v, np.r_[obs, 0.05])
            if i < round(HORIZON / DT):
                try:
                    v.advance(action, monitor.step)
                except Diverged:   # the policy's failure: the episode ends at the last finite state
                    diverged = True
                    break
    finally:
        if video:
            video.close()
    record = dict(
        state_sha256=monitor.sha.hexdigest(),
        metrics={**monitor.metrics(v), **({"success": False, "score": 0.0, "diverged": True} if diverged else {})},
        feedback=dict(command=course, telemetry=rows),
        dynamics=dict(plant=plant, friction=friction, brake_torque=brake_torque),
        policy_sha256=hashlib.sha256(canonical).hexdigest(),
        backend=dict(
            physics="mujoco-cpu",
            mujoco_version=mujoco.__version__,
            renderer="osmesa" if render else "none",
            gl_renderer=video.gl_renderer if video else None,
        ),
    )
    (out / "record.json").write_text(
        json.dumps(record, sort_keys=True, allow_nan=False)
    )
    (out / "feedback.json").write_text(
        json.dumps(record["feedback"], sort_keys=True, allow_nan=False)
    )
    (out / "policy.json").write_bytes(canonical)
    return record


def rollout(policy_path, case, out, render=True):
    p = json.loads(Path(policy_path).read_text())
    c, y, yaw = episode_parameters(case["episode_seed"])
    rng = np.random.default_rng(case["plant_seed"] + 520000)
    return run(
        p,
        c,
        plant_parameters(case["plant_seed"]),
        float(rng.uniform(0.55, 0.7)),
        float(rng.uniform(2.5, 3.5)),
        out,
        case["episode_seed"] + 300000,
        render,
        y,
        yaw,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--plant-seed", type=int, default=10100)
    parser.add_argument("--episode-seed", type=int, default=10000)
    parser.add_argument("--nominal", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    args = parser.parse_args()
    if args.nominal:
        from ..components.anycarbench.model import NOMINAL

        record = run(
            json.loads(args.policy.read_text()),
            DEFAULT_COURSE,
            NOMINAL,
            0.65,
            3.0,
            args.out,
            render=not args.no_render,
        )
    else:
        record = rollout(
            args.policy,
            dict(plant_seed=args.plant_seed, episode_seed=args.episode_seed),
            args.out,
            not args.no_render,
        )
    print(json.dumps(record["metrics"]))


if __name__ == "__main__":
    main()
