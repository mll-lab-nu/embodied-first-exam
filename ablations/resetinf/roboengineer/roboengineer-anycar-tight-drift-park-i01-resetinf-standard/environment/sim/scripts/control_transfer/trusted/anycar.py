"""Private multi-surface deployment family. Never install in the agent image."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from ..control_public.anycar import DT, HORIZON, Controller, reference, validate, wrap
from .anycar_spec import make_spec as make_spec
from ..components.anycarbench.model import Diverged, Vehicle, mujoco

NOISE = np.array([0.008, 0.008, 0.005, 0.035, 0.02, 0.012, 0.15, 0.15, 0.15, 0.15, 0.002])


def plant_parameters(seed):
    rng = np.random.default_rng(seed)
    return dict(
        mass_scale=float(rng.uniform(0.85, 1.15)),
        inertia_scale=float(rng.uniform(0.85, 1.15)),
        com_x=float(rng.uniform(-0.015, 0.015)),
        com_y=float(rng.uniform(-0.008, 0.008)),
        motor_gain=float(rng.uniform(0.8, 1.15)),
        steering_gain=float(rng.uniform(0.85, 1.15)),
        steering_bias=float(rng.uniform(-0.025, 0.025)),
        motor_tau=float(rng.uniform(0.03, 0.09)),
        steering_tau=float(rng.uniform(0.025, 0.065)),
        delay_steps=int(rng.integers(1, 5)),
    )


def episode_parameters(seed, track_id=None, full_lap=False, route_revision=None):
    rng = np.random.default_rng(seed)
    command = dict(
        a=float(rng.uniform(4.2, 4.8)),
        b=float(rng.uniform(3.2, 3.7)),
        phase=float(rng.uniform(-np.pi, np.pi)),
        direction=int(rng.choice([-1, 1])),
    )
    boundaries = [-12, float(rng.uniform(-2.7, -1.3)), float(rng.uniform(-0.4, 0.4)), float(rng.uniform(1.3, 2.7)), 12]
    mus = rng.permutation(
        [
            float(rng.uniform(0.32, 0.42)),
            float(rng.uniform(0.5, 0.65)),
            float(rng.uniform(0.75, 0.9)),
            float(rng.uniform(0.95, 1.05)),
        ]
    )
    surfaces = [(boundaries[i], boundaries[i + 1], float(mus[i])) for i in range(4)]
    offset = rng.uniform(-0.08, 0.08, 2)
    if track_id is not None:
        from ..components.anycarbench.tracks import get_route

        route = get_route(track_id, route_revision or "circuit-sector/1")
        command = dict(track_id=route.name, start_fraction=float(rng.uniform(0, 1)), speed=0.85)
        if route_revision == "compact-30s/1":
            if not full_lap:
                raise ValueError("Compact routes require full_lap")
            command.update(route_revision=route_revision, speed=route.length / 27.5)
        extent = route.half_extent
        sector = route.at(command["start_fraction"] * route.length + np.linspace(0, 0.85 * (HORIZON - 0.5), 241))
        if full_lap:
            sector = route.points
            command["full_lap"] = True
        low, high = float(sector[:, 0].min()), float(sector[:, 0].max())
        center, span = (low + high) / 2, max(high - low, 0.5)
        boundaries = [-extent, center - 0.25 * span, center, center + 0.25 * span, extent]
        surfaces = [(boundaries[i], boundaries[i + 1], float(mus[i])) for i in range(4)]
    return command, surfaces, offset, float(rng.uniform(-0.05, 0.05))


class Video:
    def __init__(self, vehicle, out):
        if os.environ.get("MUJOCO_GL") != "osmesa":
            raise RuntimeError("Evaluation video requires OSMesa")
        self.renderer = mujoco.Renderer(vehicle.model, height=480, width=640, max_geom=max(10000, vehicle.model.ngeom + 4096))
        self.render_shadows = "track_id" not in vehicle.command
        from OpenGL.GL import glGetString, GL_RENDERER, GL_VENDOR

        self.gl_renderer = glGetString(GL_RENDERER).decode()
        self.gl_vendor = glGetString(GL_VENDOR).decode()
        if not any(name in self.gl_renderer.lower() for name in ("llvmpipe", "softpipe")):
            self.renderer.close()
            raise RuntimeError("A software OpenGL renderer is required")
        self.camera = mujoco.MjvCamera()
        self.camera.lookat[:] = [0, 0, 0]
        self.camera.distance = 13
        if "track_id" in vehicle.command:
            from ..components.anycarbench.tracks import get_route

            self.camera.distance = get_route(vehicle.command["track_id"], vehicle.command.get("route_revision", "circuit-sector/1")).half_extent * 3.1
        # The line is derived only from the public command, never robot state.
        if "track_id" in vehicle.command:
            route = get_route(vehicle.command["track_id"], vehicle.command.get("route_revision", "circuit-sector/1"))
            xy = route.at(np.linspace(0, route.length, max(257, int(route.length / .04) + 1)))[:, :2]
        else:
            command = vehicle.command
            phase = command["phase"] + command["direction"] * np.linspace(0, 2 * np.pi, 257)
            xy = np.column_stack((command["a"] * np.cos(phase), command["b"] * np.sin(phase)))
        # Fixed spatial dash pattern from public route arc length, independent of state.
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(xy, axis=0), axis=1))]
        pitch = max(.60, arc[-1] / 900)
        starts = np.arange(0, arc[-1], pitch)
        ends = np.minimum(starts + .58 * pitch, arc[-1])
        self.reference_dashes = []
        for start, end in zip(starts, ends):
            distances = np.linspace(start, end, 4)
            points = np.column_stack((np.interp(distances, arc, xy[:, 0]),
                                      np.interp(distances, arc, xy[:, 1]), np.full(4, .018)))
            self.reference_dashes.extend(zip(points[:-1], points[1:]))
        self.camera.azimuth = 90
        self.camera.elevation = -70
        # Fixed orientation; center uses the already-delivered noisy position only.
        self.detail_camera = mujoco.MjvCamera()
        self.detail_camera.distance = 1.65
        self.detail_camera.azimuth = 90
        self.detail_camera.elevation = -55
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
                "1280x480",
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
                "23",
                "-pix_fmt",
                "yuv420p",
                str(out / "video.mp4"),
            ],
            stdin=subprocess.PIPE,
        )

    def view(self, v, target, camera):
        self.renderer.update_scene(v.data, camera=camera)
        scene = self.renderer.scene
        # A single whole-circuit shadow map produces meter-sized artifacts in the
        # RC close-up; disable it for this public visual profile.
        scene.flags[mujoco.mjtRndFlag.mjRND_SHADOW] = self.render_shadows
        # Render the public commanded centerline in both views, without a target dot.
        for start, end in self.reference_dashes:
            geom = scene.geoms[scene.ngeom]
            mujoco.mjv_initGeom(
                geom, mujoco.mjtGeom.mjGEOM_LINE, np.zeros(3), np.zeros(3),
                np.eye(3).ravel(), np.array([0.15, 0.95, 0.85, 1.0]),
            )
            mujoco.mjv_connector(geom, mujoco.mjtGeom.mjGEOM_LINE, 3.0, start, end)
            scene.ngeom += 1
        return self.renderer.render().copy()

    def frame(self, v, target, observation):
        overview = self.view(v, target, self.camera)
        self.detail_camera.lookat[:] = [observation[0], observation[1], 0.10]
        detail = self.view(v, target, self.detail_camera)
        # Both views are encoded in the single agent-visible stream; no private overlay.
        self.process.stdin.write(np.concatenate((overview, detail), axis=1).tobytes())

    def close(self):
        self.process.stdin.close()
        rc = self.process.wait(timeout=60)
        self.renderer.close()
        if rc:
            raise RuntimeError("Video encoding failed")


def score_trajectory(states, targets, command, collision=False, body_contact=False, rollover=False):
    states, targets = np.asarray(states), np.asarray(targets)
    errors = np.linalg.norm(states[:, :2] - targets[:, :2], axis=1)
    heading = np.abs(wrap(states[:, 2] - targets[:, 2]))
    speed = np.abs(states[:, 3] - targets[:, 3])
    lap_time = None
    full_lap = command.get("full_lap", False)
    if "track_id" in command:
        from ..components.anycarbench.tracks import get_route

        route = get_route(command["track_id"], command.get("route_revision", "circuit-sector/1"))
        start = command.get("start_fraction", 0.0) * route.length
        distance = command.get("speed", 0.85) * (HORIZON - 0.5)
        if full_lap:
            distance = route.length
        gate_count = max(24, int(np.ceil(distance / 0.5))) if full_lap else 24
        gates = route.at(start + np.linspace(distance / gate_count, distance, gate_count))
        gate = 0
        # Cross each prescribed gate plane forward, near its center, in order.
        # A global nearest-waypoint jump cannot skip a bend or crossover.
        for step, (previous, current) in enumerate(zip(states[:-1], states[1:])):
            if gate == gate_count:
                break
            x, y, yaw, _ = gates[gate]
            normal = np.array([np.cos(yaw), np.sin(yaw)])
            tangent = np.array([-normal[1], normal[0]])
            before, after = (np.dot(p[:2] - [x, y], normal) for p in (previous, current))
            if before < 0 and after >= -1e-10:
                alpha = -before / (after - before)
                crossing = previous[:2] + alpha * (current[:2] - previous[:2])
                if abs(np.dot(crossing - [x, y], tangent)) < 0.45:
                    gate += 1
                    if full_lap and gate == gate_count:
                        lap_time = float((step + alpha) * DT)
        completion = gate / gate_count
        offtrack = bool(np.max(route.distance(states[:, :2])) > 0.70)
    else:
        phase = np.unwrap(np.arctan2(states[:, 1] / command["b"], states[:, 0] / command["a"]))
        progress = command["direction"] * (phase - phase[0])
        # Gates must be crossed in order and near the center line, not via chord shortcuts.
        radial = np.abs(np.sqrt((states[:, 0] / command["a"]) ** 2 + (states[:, 1] / command["b"]) ** 2) - 1) * min(
            command["a"], command["b"]
        )
        gate = 1
        for angle, err in zip(progress, radial):
            if gate <= 24 and angle >= gate * 2 * np.pi / 24 and err < 0.45:
                gate += 1
        completion = min((gate - 1) / 24, 1.0)
        offtrack = bool(np.max(radial) > 0.70)
    rmse = float(np.sqrt(np.mean(errors**2)))
    mae_heading = float(np.mean(heading))
    mae_speed = float(np.mean(speed))
    unsafe = bool(collision or body_contact or rollover or offtrack)
    success = bool(
        not unsafe
        and completion >= (1.0 if full_lap else 23 / 24)
        and rmse < 0.30
        and mae_heading < 0.18
        and mae_speed < 0.25
        and errors[-1] < 0.35
    )
    quality = float(np.exp(-rmse / 0.35 - mae_heading / 0.3 - mae_speed / 0.4))
    score = 0.0 if unsafe else 100 * completion * quality
    result = dict(
        success=success,
        score=score,
        tracking_rmse_m=rmse,
        heading_mae_rad=mae_heading,
        speed_mae_m_s=mae_speed,
        ordered_gate_fraction=completion,
        offtrack=offtrack,
        collision=bool(collision),
        body_contact=bool(body_contact),
        rollover=bool(rollover),
    )

    if full_lap:
        result.update(lap_time_s=lap_time, full_lap_completed=bool(completion == 1.0))
    return result


def rollout(policy_path, case, out, render=True):
    policy = json.loads(Path(policy_path).read_text())
    raw = validate(policy)
    plant = plant_parameters(case["plant_seed"])
    command, surfaces, offset, angle = episode_parameters(case["episode_seed"], case.get("track_id"), case.get("full_lap", False), case.get("route_revision"))
    if "start_fraction" in case:
        command["start_fraction"] = float(case["start_fraction"])
    horizon = HORIZON
    if command.get("full_lap"):
        from ..components.anycarbench.tracks import get_route

        # A bounded two-second allowance lets a lagging car cross the finish gate.
        horizon = np.ceil((get_route(command["track_id"], command.get("route_revision", "circuit-sector/1")).length / command["speed"] + 2.5) / DT) * DT
    if command.get("route_revision") == "compact-30s/1":
        horizon = 30.0
    rng = np.random.default_rng(case["episode_seed"] + 300000)
    v = Vehicle(plant, surfaces, command)
    start = reference(0, command)
    v.reset(start[0] + offset[0], start[1] + offset[1], start[2] + angle)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    video = Video(v, out) if render else None
    controller = Controller(policy)
    telemetry = []
    states = []
    targets = []
    sha = hashlib.sha256()
    rollover = False
    try:
        diverged = False
        for i in range(round(horizon / DT) + 1):
            t = i * DT
            state = v.state()
            target = reference(t, command)
            observation = state + rng.normal(0, NOISE)
            action = controller.step(observation, reference(min(t + policy["preview"], horizon), command))
            states.append(state)
            targets.append(target)
            sha.update(np.asarray(np.r_[t, v.data.qpos, v.data.qvel, v.data.act, v.applied], dtype="<f8").tobytes())
            rollover |= bool(v.data.xmat[1].reshape(3, 3)[2, 2] < 0.5)
            if i % 5 == 0:
                telemetry.append(dict(t=t, values=[*observation.tolist(), *target.tolist(), *action.tolist()]))
                if video:
                    video.frame(v, target, observation)
            if i < round(horizon / DT):
                try:
                    v.advance(action)
                except Diverged:   # the policy's failure: the episode ends at the last finite state
                    diverged = True
                    break
    finally:
        if video:
            video.close()
    metrics = score_trajectory(states, targets, command, v.collision, v.body_contact, rollover)
    if diverged:
        metrics.update(success=False, score=0.0, diverged=True)
    metrics["surface_contacts"] = len(v.contacts_seen)
    record = dict(
        state_sha256=sha.hexdigest(),
        metrics=metrics,
        feedback=dict(telemetry=telemetry),
        dynamics=dict(plant=plant, surfaces=surfaces, command=command),
        policy_sha256=hashlib.sha256(raw).hexdigest(),
        backend=dict(
            physics="mujoco-cpu",
            mujoco_version=mujoco.__version__,
            inference="numpy-cpu",
            renderer="osmesa" if render else "none",
            gl_renderer=video.gl_renderer if video else None,
            gl_vendor=video.gl_vendor if video else None,
        ),
    )
    (out / "record.json").write_text(json.dumps(record, sort_keys=True, allow_nan=False))
    # Exact telemetry bytes for operator audit; adapter separately retains delivered images/response.
    (out / "feedback.json").write_text(json.dumps(record["feedback"], sort_keys=True, allow_nan=False))
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--plant-seed", type=int, default=10100)
    parser.add_argument("--episode-seed", type=int, default=10300)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--compact-30s", action="store_true", help="Smoothed F1-inspired full lap in a 30-second episode")
    parser.add_argument("--full-lap", action="store_true", help="Complete circuit lap with measured finish crossing")
    parser.add_argument("--track", help="Historical layout ID, circuit alias (latest raced layout), or zigzag")
    parser.add_argument("--start-fraction", type=float, help="Operator-only public route start override for previews")
    a = parser.parse_args()
    case = dict(plant_seed=a.plant_seed, episode_seed=a.episode_seed)
    if (a.full_lap or a.compact_30s) and not a.track:
        parser.error("--full-lap requires --track")
    if a.track:
        case["track_id"] = a.track
        if a.full_lap or a.compact_30s:
            case["full_lap"] = True
        if a.compact_30s:
            case["route_revision"] = "compact-30s/1"
    if a.start_fraction is not None:
        if not a.track or not 0 <= a.start_fraction < 1:
            parser.error("--start-fraction requires --track and a value in [0,1)")
        case["start_fraction"] = a.start_fraction
    r = rollout(a.policy, case, a.out, not a.no_render)
    print(json.dumps(dict(state_sha256=r["state_sha256"], metrics=r["metrics"])))


if __name__ == "__main__":
    main()
