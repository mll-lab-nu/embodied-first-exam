"""CPU MuJoCo landing evaluator. Private records and public observations stay separate."""

import os

os.environ.setdefault("MUJOCO_GL", "egl")
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
import mujoco
from ..public.model import (
    AIRFRAME,
    TASK_VERSION,
    SCORE_VERSION,
    CLEARANCE,
    CT,
    DT,
    GRAVITY,
    HORIZON,
    MASS,
    MOTOR_TAU,
    ROTOR_MAX,
    PAD_RADIUS,
    sample_task,
    xml,
)
from ..public.policy import Controller, DEFAULT, validate
from .residual import Residual
from .scoring import SettlingTimer, score_metrics


def observation(data, rng, rotor_forces, t, pad_position):
    q = data.qpos[3:7].copy() + rng.normal(0, 0.0005, 4)
    q /= np.linalg.norm(q)
    r = data.xmat[1].reshape(3, 3)
    return {
        "t": round(t, 4),
        "pad_position": pad_position.tolist(),  # public commanded goal; not robot ground truth
        "position": (data.qpos[:3] + rng.normal(0, 0.002, 3)).tolist(),
        "velocity": (data.qvel[:3] + rng.normal(0, 0.008, 3)).tolist(),
        "quaternion": q.tolist(),
        "omega": (data.qvel[3:] + rng.normal(0, 0.003, 3)).tolist(),
        "specific_force": (r.T @ (data.qacc[:3] - [0, 0, -GRAVITY]) + rng.normal(0, 0.12, 3)).tolist(),
        "rotor_rpm": np.maximum(0, np.sqrt(rotor_forces / CT) + rng.normal(0, 15, 4)).tolist(),
    }


def rollout(
    policy=DEFAULT,
    *,
    residual_path=None,
    scale=1.0,
    seed=0,
    out=None,
    oracle=False,
    render=False,
    initial_position=None,
    pad_position=None,
    reference_time_s=None,
):
    policy = validate(policy)
    rng = np.random.default_rng(seed)
    sampled_initial, sampled_pad = sample_task(rng)
    initial_position = np.asarray(sampled_initial if initial_position is None else initial_position, dtype=float)
    pad_position = np.asarray(sampled_pad if pad_position is None else pad_position, dtype=float)
    if initial_position.shape != (3,) or not np.isfinite(initial_position).all() or initial_position[2] <= CLEARANCE:
        raise ValueError("Invalid initial position")
    m = mujoco.MjModel.from_xml_string(xml(pad_position))
    d = mujoco.MjData(m)
    d.qpos[:3] = initial_position
    d.qpos[3:7] = [1, 0, 0, 0]
    mujoco.mj_forward(m, d)
    plant = Residual(residual_path, scale) if residual_path else None
    if oracle and plant is None:
        raise ValueError("Oracle requires a residual model")
    controller = Controller(policy)
    motors = np.full(4, MASS * GRAVITY / 4)
    d.ctrl[:] = motors
    observations, history, frames = [], [], []
    foot_ids = {m.geom(f"foot{i}").id for i in range(4)}
    floor = m.geom("floor").id
    first_touch = None
    impact = None
    lateral_impact = None
    bad_contact = False
    off_pad_contact = False
    settling = SettlingTimer()
    crash = False
    diverged = False
    bad_warnings = (mujoco.mjtWarning.mjWARN_BADQPOS, mujoco.mjtWarning.mjWARN_BADQVEL, mujoco.mjtWarning.mjWARN_BADQACC)
    warning_base = [d.warning[w].number for w in bad_warnings]   # cumulative counters: only new warnings count
    renderer = None
    writer = None
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=False)
    if render:
        if out is None:
            raise ValueError("Rendering requires an output directory")
        from .rendering import FPS, HEIGHT, WIDTH, STYLE, StudioRenderer

        renderer = StudioRenderer(pad_position)
        (out / "rendering.json").write_text(
            json.dumps(
                {
                    "style": STYLE,
                    "width": WIDTH,
                    "height": HEIGHT,
                    "fps": FPS,
                    "camera": "fixed world camera",
                    "overlays": False,
                },
                indent=2,
            )
        )
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
                f"{WIDTH}x{HEIGHT}",
                "-r",
                str(FPS),
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-preset",
                "fast",
                "-threads",
                "1",
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )
    try:
        for k in range(round(HORIZON / DT)):
            t = k * DT
            force = plant.force(d.qpos[:3], d.qvel[:3], d.qpos[3:7], np.sqrt(motors / CT)) if plant else np.zeros(3)
            d.xfrc_applied[1, :3] = force
            d.ctrl[:] = motors
            mujoco.mj_forward(m, d)
            obs = observation(d, rng, motors, t, pad_position)
            # Only operator-side calibration may use exact state and residual.
            # Still generate the normal noisy observation stream for recording;
            # agent deployments always take the non-oracle branch.
            control_obs = obs
            if oracle:
                control_obs = {
                    **obs,
                    "position": d.qpos[:3].tolist(),
                    "velocity": d.qvel[:3].tolist(),
                    "quaternion": d.qpos[3:7].tolist(),
                    "omega": d.qvel[3:].tolist(),
                    "rotor_rpm": np.sqrt(motors / CT).tolist(),
                }
            command = controller.act(control_obs, oracle_force=force if oracle else None)
            if k % 5 == 0:
                observations.append({**obs, "rotor_command": command.tolist()})
            if renderer and k % round(1 / (FPS * DT)) == 0:
                pixels = renderer.render(d, obs)
                writer.stdin.write(pixels.tobytes())
                # Fixed public sampling schedule, independent of hidden contact/launch state.
                if k % 100 == 0:
                    from PIL import Image

                    frame = f"frame-{k // 100:02d}.jpg"
                    Image.fromarray(pixels).save(out / frame, quality=90)
                    frames.append({"time_s": round(t, 2), "name": frame})
            for _ in range(5):
                motors += (1 - np.exp(-m.opt.timestep / MOTOR_TAU)) * (command - motors)
                d.ctrl[:] = np.clip(motors, 0, ROTOR_MAX)
                d.xfrc_applied[1, :3] = (
                    plant.force(d.qpos[:3], d.qvel[:3], d.qpos[3:7], np.sqrt(motors / CT)) if plant else np.zeros(3)
                )
                pre_v = d.qvel[:3].copy()
                last = (d.time, d.qpos.copy(), d.qvel.copy())
                mujoco.mj_step(m, d)
                if (not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all()
                        or any(d.warning[w].number > b for w, b in zip(bad_warnings, warning_base))):
                    # the policy made the simulation diverge: a crash (the agent's failure, never an evaluator
                    # error); back to the last finite state so the record stays finite
                    d.time, d.qpos[:], d.qvel[:] = last
                    mujoco.mj_forward(m, d)
                    diverged = True
                    break
                touching = False
                for contact in d.contact:
                    if floor in (contact.geom1, contact.geom2):
                        other = contact.geom2 if contact.geom1 == floor else contact.geom1
                        touching |= other in foot_ids
                        if other in foot_ids and np.linalg.norm(contact.pos[:2] - pad_position[:2]) > PAD_RADIUS:
                            off_pad_contact = True
                        bad_contact |= other not in foot_ids
                if touching and first_touch is None:
                    first_touch = float(d.time)
                    impact = abs(float(pre_v[2]))
                    lateral_impact = float(np.linalg.norm(pre_v[:2]))
            if diverged:
                crash = True
                break
            tilt = float(np.arccos(np.clip(d.xmat[1].reshape(3, 3)[2, 2], -1, 1)))
            crash |= bad_contact or tilt > 0.8 or np.max(np.abs(d.qpos[:2])) > 3 or d.qpos[2] > 3.0
            settled = (
                touching
                and np.linalg.norm(d.qpos[:2] - pad_position[:2]) < 0.15
                and tilt < 0.15
                and np.linalg.norm(d.qvel[:3]) < 0.08
            )
            settling.update(settled)
            history.append(
                {
                    "t": round(float(d.time), 4),
                    "position": d.qpos[:3].tolist(),
                    "velocity": d.qvel[:3].tolist(),
                    "quaternion": d.qpos[3:7].tolist(),
                    "residual_force_world_N": force.tolist(),
                    "motor_forces": motors.tolist(),
                    "contact": touching,
                    "tilt": tilt,
                }
            )
        success = (
            not crash
            and not off_pad_contact
            and settling.completion_time_s is not None
            and impact is not None
            and impact < 0.4
            and lateral_impact < 0.25
        )
        metrics = {
            "success": bool(success),
            "touchdown_time_s": first_touch,
            "impact_speed_m_s": impact,
            "lateral_impact_m_s": lateral_impact,
            "settled_duration_s": settling.duration_s,
            "crash": bool(crash),
            "diverged": bool(diverged),
            "off_pad_contact": bool(off_pad_contact),
            "final_clearance_m": float(d.qpos[2] - CLEARANCE),
            "final_xy_error_m": float(np.linalg.norm(d.qpos[:2] - pad_position[:2])),
            "completion_time_s": settling.completion_time_s if success else None,
            # Diagnostic/oracle search rollouts are explicitly ungraded.
            "score": None,
            "scoring_status": "ungraded_without_reference",
        }
        if reference_time_s is not None:
            metrics.update(score_metrics(success, settling.completion_time_s, reference_time_s))
            metrics["scoring_status"] = "graded_with_frozen_oracle"
    finally:
        if renderer:
            renderer.close()
        if writer:
            writer.stdin.close()
            if writer.wait(timeout=60):
                raise RuntimeError("Video encoder failed")
    public = {"schema": "landing-feedback/2", "observations": observations, "frames": frames}
    private = {
        "task_version": TASK_VERSION,
        "score_version": SCORE_VERSION,
        "airframe": AIRFRAME,
        "initial_position": initial_position.tolist(),
        "pad_position": pad_position.tolist(),
        "policy": policy,
        "seed": seed,
        "residual_scale": scale,
        "residual_sha256": hashlib.sha256(Path(residual_path).read_bytes()).hexdigest() if residual_path else None,
        "oracle": oracle,
        "metrics": metrics,
        "trajectory": history,
    }
    if out:
        (out / "feedback.json").write_text(json.dumps(public, allow_nan=False))
        (out / "record.json").write_text(json.dumps(private, allow_nan=False))
    return public, private
