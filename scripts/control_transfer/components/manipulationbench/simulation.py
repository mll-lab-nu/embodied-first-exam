"""CPU MuJoCo plant and a controller that only receives noisy observations.
No grasp welds, teleport captures, privileged IK, or force overrides are used.
"""

import os

os.environ.setdefault("MUJOCO_GL", "egl")
import json, hashlib, subprocess, xml.etree.ElementTree as ET
from pathlib import Path
from collections import deque
import numpy as np
import mujoco
from .assets import MODEL, COMMIT, verify
from .contract import validate, BASELINE, TASKS
from .throws import sample_throw, sample_varied_throw

HOME = np.array([0, 1.047, 1.047, 0, 0, 0, 0, 0.0])
DT = 0.01


def model(task):
    root = ET.parse(MODEL).getroot()
    root.remove(root.find("keyframe"))
    root.find("compiler").set("meshdir", str(MODEL.parent / "assets"))
    root.find("option").set("timestep", ".002")
    for b in root.iter("body"):
        b.attrib.pop("gravcomp", None)
    # Original servo force ranges, inertias, meshes and finger coupling retained.
    wb = root.find("worldbody")
    # Grasp frame centered between the original finger pads, not at their tips.
    site = root.find(".//site[@name='grasp_site']")
    site.set("pos", "0 -.03 .11")
    ET.SubElement(wb, "geom", name="floor", type="plane", size="2 2 .05", pos="0 0 -.01", rgba=".12 .18 .23 1")
    ET.SubElement(wb, "light", pos="1 -1 2", diffuse=".8 .8 .8")
    ET.SubElement(wb, "site", name="goal", pos=".42 .12 .4", size=".015", rgba=".2 1 .5 .6")
    if task == "pick_place":
        for name, y in [("source", 0), ("destination", 0.15)]:
            ET.SubElement(
                wb, "geom", name=name, type="cylinder", size=".065 .13", pos=f".42 {y} .13", rgba=".35 .42 .5 1"
            )
    b = ET.SubElement(wb, "body", name="ball", pos=".42 0 .8")
    ET.SubElement(b, "freejoint", name="ball_free")
    ET.SubElement(
        b,
        "geom",
        name="ball_geom",
        type="sphere",
        size=".025",
        mass=".03",
        friction="1 .005 .0001",
        condim="4",
        rgba="1 .32 .08 1",
    )
    visual = ET.SubElement(root, "visual")
    ET.SubElement(visual, "headlight", ambient=".5 .5 .5", diffuse=".8 .8 .8")
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding="unicode"))


class Controller:
    """Nominal model only: no reference to target model/data or randomization."""

    def __init__(self, task, config):
        self.m = model(task)
        self.d = mujoco.MjData(self.m)
        self.c = config
        self.task = task
        self.d.qpos[:8] = HOME
        mujoco.mj_forward(self.m, self.d)
        self.rot = self.d.site("grasp_site").xmat.reshape(3, 3).copy()
        self.moving = False
        self.closed = False
        self.last_ball = None
        self.velocity = np.zeros(3)
        self.filtered = None
        self.command = HOME[:6].copy()

    def act(self, t, obs, goal):
        q = np.array(obs[:8])
        ball = np.array(obs[8:])
        c = self.c
        if self.last_ball is not None:
            self.velocity = 0.8 * self.velocity + 0.2 * (ball - self.last_ball) / DT
        self.last_ball = ball.copy()
        self.filtered = (
            ball.copy() if self.filtered is None else c["filter_alpha"] * ball + (1 - c["filter_alpha"]) * self.filtered
        )
        grip = c["grip_open"]
        if self.task == "reach":
            target = goal
        elif self.task == "pick_place":
            # Public timed state machine; all grasp coordinates come from sensor data.
            if t < 1.8:
                target = self.filtered.copy()
            elif t < 3.0:
                target = np.array([0.42, 0, 0.40])
                grip = 0.0
            elif t < 5.0:
                target = np.array([goal[0], goal[1], 0.40])
                grip = 0.0
            elif t < 6.5:
                target = goal
                grip = 0.0
            else:
                target = goal + np.array([0, 0, 0.06])
        else:
            z = 0.3926
            v = self.velocity[2]
            if self.task == "catch_varied":
                # Predict a workspace crossing from noisy position differences only.
                # Neither the launcher target nor its true velocity is available here.
                planar = self.velocity[:2]
                speed2 = float(planar @ planar)
                arrival = np.clip(np.dot(np.array([0.42, 0]) - self.filtered[:2], planar) / max(speed2, 0.01), 0, 0.65)
                z = float(np.clip(self.filtered[2] + v * arrival - 0.5 * 9.81 * arrival**2, 0.35, 0.48))
            h = max(0, self.filtered[2] - z)
            cross = (v + np.sqrt(v * v + 2 * 9.81 * h)) / 9.81
            lead = min(0.35, max(0, cross - c["catch_lead"]))
            target = np.array([*(self.filtered[:2] + self.velocity[:2] * lead), z])
            target[:2] = np.clip(target[:2], [0.30, -0.15], [0.52, 0.15])
            if self.task in ("catch_throw", "catch_varied"):
                # Release is inferred from noisy motion, never from private launch metadata.
                if np.linalg.norm(self.velocity) > 0.25:
                    self.moving = True
                if self.moving and v < -0.15 and cross < c["catch_lead"] - c["close_delay"]:
                    self.closed = True
                if self.closed:
                    grip = 0.0
            else:
                if t > 1.5 and cross < c["catch_lead"] - c["close_delay"]:
                    grip = 0.0
                if t > 1.85:
                    grip = 0.0
        self.d.qpos[:8] = q
        self.d.qvel[:] = 0
        mujoco.mj_forward(self.m, self.d)
        pos = self.d.site("grasp_site").xpos.copy()
        rot = self.d.site("grasp_site").xmat.reshape(3, 3)
        jp = np.zeros((3, self.m.nv))
        jr = jp.copy()
        mujoco.mj_jacSite(self.m, self.d, jp, jr, self.m.site("grasp_site").id)
        orient = sum(np.cross(rot[:, i], self.rot[:, i]) for i in range(3)) * 0.5
        err = np.r_[np.clip(target - pos, -0.05, 0.05), 0.3 * orient]
        j = np.vstack([jp[:, :6], 0.3 * jr[:, :6]])
        dq = j.T @ np.linalg.solve(j @ j.T + np.eye(6) * 0.002, err) * c["ik_gain"]
        desired = np.clip(q[:6] + dq, self.m.jnt_range[:6, 0] + 0.02, self.m.jnt_range[:6, 1] - 0.02)
        self.command += np.clip(desired - self.command, -c["speed"] * DT, c["speed"] * DT)
        # Nominal gravity compensation uses noisy joint configuration, never target masses.
        gravity = self.d.qfrc_bias[:6].copy()
        kp = self.m.actuator_gainprm[:6, 0] * c["kp_scale"]
        return np.r_[self.command + gravity / kp, grip]


def rollout(task, config=BASELINE, *, plant_seed=0, episode_seed=0, nominal=False, render=False, out=None):
    if task not in TASKS:
        raise ValueError("Unknown task")
    config = validate(config)
    source_hash = verify()
    m = model(task)
    d = mujoco.MjData(m)
    plant = np.random.default_rng(plant_seed)
    rng = np.random.default_rng(episode_seed)
    dynamics = {
        "mass_scale": 1.0 if nominal else float(plant.uniform(0.85, 1.15)),
        "strength": 1.0 if nominal else float(plant.uniform(0.8, 1.2)),
        "friction": 1.0 if nominal else float(plant.uniform(0.6, 1.4)),
        "delay_steps": 0 if nominal else int(plant.integers(0, 4)),
        "angle_sigma": 0.001 if nominal else float(plant.uniform(0.002, 0.008)),
        "vision_sigma": 0.001 if nominal else float(plant.uniform(0.002, 0.006)),
    }
    m.body_mass[1:] *= dynamics["mass_scale"]
    m.body_inertia[1:] *= dynamics["mass_scale"]
    m.geom_friction[:, 0] *= dynamics["friction"]
    m.actuator_gainprm[:6, 0] *= config["kp_scale"]
    m.actuator_biasprm[:6, 1] *= config["kp_scale"]
    m.actuator_biasprm[:6, 2] *= config["kd_scale"]
    m.actuator_forcerange[:6] *= dynamics["strength"]
    # Gripper force capped explicitly: upstream finger actuator has no force limit.
    m.actuator_forcelimited[6] = 1
    m.actuator_forcerange[6] = [-15, 15]
    mujoco.mj_setConst(m, d)
    d.qpos[:8] = HOME
    d.ctrl[:6] = HOME[:6]
    start = np.array([0.42, 0, 0.285 if task == "pick_place" else 0.76])
    start[:2] += rng.uniform(-0.015, 0.015, 2)
    if task == "reach":
        start = np.array([0.9, 0.3, 0.025])
    goal = (
        np.array([0.42, 0.15, 0.285])
        if task == "pick_place"
        else np.array([0.42, 0, 0.3926])
        if task == "catch"
        else np.array([0.42, 0.10, 0.43])
    )
    goal += rng.uniform(-0.015, 0.015, 3) if task == "reach" else 0
    launch = (
        sample_varied_throw(episode_seed)
        if task == "catch_varied"
        else sample_throw(episode_seed)
        if task == "catch_throw"
        else None
    )
    if launch:
        start = np.array(launch["position"])
        goal = np.array([0.42, 0, 0.3926])
    m.site_pos[m.site("goal").id] = goal
    if task == "catch_varied":
        m.site_rgba[m.site("goal").id, 3] = 0
    d.qpos[8:11] = start
    d.qpos[11:15] = [1, 0, 0, 0]
    mujoco.mj_forward(m, d)
    controller = Controller(task, config)
    delay = deque([d.ctrl.copy()] * (dynamics["delay_steps"] + 1), maxlen=dynamics["delay_steps"] + 1)
    bias = rng.normal(0, dynamics["angle_sigma"] / 2, 8)
    bias[6:] *= 0.1
    renderer = None
    writer = None
    states = []
    telemetry = []
    history = []
    hold = 0.0
    best_hold = 0.0
    lift = 0.0
    peak_force = 0.0
    bilateral = False
    if render:
        if out is None:
            raise ValueError("Rendered runs need an output directory")
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
        renderer = mujoco.Renderer(m, 240, 320)
        cam = mujoco.MjvCamera()
        cam.lookat[:] = [0.45, 0, 0.65] if task in ("catch_throw", "catch_varied") else [0.30, 0, 0.32]
        cam.distance = 2.6 if task in ("catch_throw", "catch_varied") else 1.5
        cam.azimuth = 135
        cam.elevation = -22
        writer = subprocess.Popen(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-s",
                "320x240",
                "-r",
                "10",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )
    left = {i for i in range(m.ngeom) if m.body(m.geom_bodyid[i]).name in ("link_left_finger", "lf_rot", "lf_down")}
    right = {i for i in range(m.ngeom) if m.body(m.geom_bodyid[i]).name in ("link_right_finger", "rf_rot", "rf_down")}
    ballgeom = m.geom("ball_geom").id
    try:
        for k in range(800):
            t = k * DT
            if task == "catch" and t < 1.5:
                d.qpos[8:11] = start
                d.qvel[8:14] = 0
                mujoco.mj_forward(m, d)
            if launch and k <= launch["release_step"]:
                d.qpos[8:11] = start
                d.qpos[11:15] = [1, 0, 0, 0]
                d.qvel[8:14] = 0
                if k == launch["release_step"]:
                    d.qvel[8:11] = launch["velocity"]
                mujoco.mj_forward(m, d)
            q = d.qpos[:8] + bias + rng.normal(0, dynamics["angle_sigma"], 8) * np.array([1] * 6 + [0.1, 0.1])
            sensed = d.qpos[8:11] + rng.normal(0, dynamics["vision_sigma"], 3)
            obs = np.r_[q, sensed]
            # Video and noisy telemetry share the same pre-control sampling time.
            if renderer and k % 10 == 0:
                renderer.update_scene(d, camera=cam)
                writer.stdin.write(renderer.render().tobytes())
            delay.append(controller.act(t, obs, goal))
            d.ctrl[:] = delay[0]
            for _ in range(5):
                mujoco.mj_step(m, d)
            touches = set()
            for contact in d.contact:
                if ballgeom in (contact.geom1, contact.geom2):
                    touches.add(contact.geom2 if contact.geom1 == ballgeom else contact.geom1)
            bilateral = bool(touches & left and touches & right)
            speed = float(np.linalg.norm(d.qvel[8:11]))
            height = float(d.qpos[10])
            lift = max(lift, height - start[2])
            retained = (
                bilateral and height > 0.32 and speed < 0.25 and (t > launch["release_time_s"] if launch else t > 1.6)
            )
            hold = hold + DT if retained else 0.0
            best_hold = max(best_hold, hold)
            peak_force = max(peak_force, float(np.max(np.abs(d.actuator_force))))
            if not np.isfinite(d.qpos).all():
                raise RuntimeError("Nonfinite simulation")
            history.append(
                {
                    "t": round(t, 2),
                    "ball": d.qpos[8:11].tolist(),
                    "grasp": d.site("grasp_site").xpos.tolist(),
                    "bilateral_contact": bilateral,
                    "ball_speed": speed,
                }
            )
            if k % 10 == 0:
                states.append([*d.qpos, *d.qvel])
                telemetry.append({"t": round(t, 2), "values": obs.tolist()})
    finally:
        if renderer:
            renderer.close()
        if writer:
            writer.stdin.close()
            code = writer.wait(timeout=60)
    if render and code:
        raise RuntimeError("Video encoding failed")
    reach_error = float(np.mean([np.linalg.norm(np.array(h["grasp"]) - goal) for h in history[-100:]]))
    place_error = float(np.linalg.norm(d.qpos[8:11] - goal))
    if task == "reach":
        success = reach_error < 0.025
        score = 100 * np.exp(-reach_error / 0.08)
    elif task == "pick_place":
        success = lift > 0.06 and best_hold >= 0.2 and place_error < 0.045 and speed < 0.1 and not bilateral
        score = 100 * (0.25 * min(1, lift / 0.08) + 0.75 * np.exp(-place_error / 0.08))
    else:
        success = hold >= 0.5
        score = 100.0 if success else min(49.0, 100 * best_hold / 0.5)
    record = {
        "state_sha256": hashlib.sha256(np.asarray(states).tobytes()).hexdigest(),
        "task": task,
        "kind": "simulation_episode",
        "config": config,
        "upstream_commit": COMMIT,
        "model_sha256": source_hash,
        "plant_seed": plant_seed,
        "episode_seed": episode_seed,
        "nominal": nominal,
        "dynamics": dynamics,
        "goal": goal.tolist(),
        "metrics": {
            "score": float(score),
            "success": bool(success),
            "reach_error_m": reach_error,
            "placement_error_m": place_error,
            "max_lift_m": lift,
            "sustained_catch_s": best_hold,
            "final_retention_s": hold,
            "peak_actuator_force": peak_force,
            "duration_s": 8.0,
        },
        "feedback": {"telemetry": telemetry},
        "operator_trajectory": history,
    }
    if launch:
        record["launch"] = launch
    if out:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        if render:
            record["video_sha256"] = hashlib.sha256((out / "video.mp4").read_bytes()).hexdigest()
        (out / "record.json").write_text(json.dumps(record, allow_nan=False))
    return record


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--task", choices=TASKS, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--seed", type=int, default=0)
    a = p.parse_args()
    r = rollout(a.task, render=True, out=a.out, episode_seed=a.seed)
    print(json.dumps(r["metrics"]))
