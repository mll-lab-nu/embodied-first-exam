"""On-demand Nyx via the shared SensorSuite; diagnostic crops stay separate."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np

from topogym.sensors.observation import SensorSuite
from .contracts import UnsupportedCapability


class DevelopmentSensors(SensorSuite):
    """Build the regular camera rig but don't request RGB during control steps."""
    def __init__(self, world, robot, **kwargs):
        kwargs.update(enable_rgb=False, enable_depth=False)
        super().__init__(world, robot, **kwargs)


class SelectedWorld:
    def __init__(self, world, camera):
        self._world = world
        self.cameras = {camera: world.cameras[camera]}

    def __getattr__(self, name):
        return getattr(self._world, name)


def capture(env, output, camera, *, near=None, overlays=(), record_video=False):
    if not env.config.enable_rgb or camera not in env._world.cameras:
        raise UnsupportedCapability("Nyx cameras must be built with enable_rgb=True and CUDA; no renderer fallback")
    if set(overlays) - {"contacts", "targets"}:
        raise UnsupportedCapability("Supported overlays are textual contacts and targets; exact contact points are unavailable")
    from PIL import Image, ImageDraw
    from topogym.utils.io import write_json_atomic, to_jsonable
    from .inspection import contact_summary
    view = SensorSuite(SelectedWorld(env._world, camera), env._robot, enable_rgb=True)
    _, frame = view.sample(episode_id=env._episode_id, branch_id=env._branch_id,
                           state_id=env._state_id, task=env._task)
    folder = Path(output) / uuid4().hex
    folder.mkdir(parents=True, exist_ok=False)
    pixels = np.asarray(frame.rgb[camera])
    raw = Image.fromarray(pixels)
    raw.save(folder / "raw.png")
    diagnostic = raw.copy()
    crop = None
    world = env._world.read_state()
    metadata = frame.camera_metadata[camera]
    if near is not None:
        if near in world["bodies"]:
            center = world["bodies"][near]["position_m"]
        elif near in env._robot.groups:
            center = env._robot.observe()[near]["tcp_position_world_m"]
        else:
            raise ValueError("near must name a rigid entity or robot group")
        cv = np.asarray(metadata["T_camera_cv_from_world"]) @ np.r_[center, 1.]
        if cv[2] <= 0:
            raise ValueError("Requested near target is behind this camera")
        uv = np.asarray(metadata["K_px"]) @ cv[:3]
        x, y = uv[:2]/uv[2]
        width, height = raw.size
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError("Requested near target is outside this camera")
        crop = [max(0, int(x)-128), max(0, int(y)-128), min(width, int(x)+128), min(height, int(y)+128)]
        diagnostic = diagnostic.crop(crop).resize((512, 512))
    if overlays:
        draw = ImageDraw.Draw(diagnostic)
        lines = [f"DIAGNOSTIC tick={frame.physics_step} (text only)"]
        if "contacts" in overlays:
            contacts = contact_summary(world, env._world.entities)
            lines.extend(f"{c['a'].get('link', '?')} / {c['b'].get('link', '?')}: {c['force_norm_n']:.3g}N"
                         for c in contacts["contacts"][:12])
            lines.append("Contact positions unavailable")
        if "targets" in overlays:
            for side, target in env._robot.capture_state().targets.items():
                lines.append(f"{side}: {target}")
        draw.multiline_text((8, 8), "\n".join(lines), fill=(255, 70, 70), stroke_width=1, stroke_fill=(0, 0, 0))
    if near is not None or overlays:
        diagnostic.save(folder / "diagnostic.png")
    video = None
    if record_video:
        from topogym.recording.session import RecordingSession
        with RecordingSession(folder / "recording", metadata=dict(scope="single development keyframe")) as recording:
            recording.append(frame)
            recording.finish(dict(status="keyframe_only", task_success=False))
        video = str(folder / "recording")
    result = dict(raw=str(folder / "raw.png"),
                  diagnostic=str(folder / "diagnostic.png") if near is not None or overlays else None,
                  crop_px=crop, camera=camera, camera_metadata=to_jsonable(metadata), recording=video,
                  state_ref=dict(episode_id=frame.episode_id, state_id=frame.state_id),
                  branch_id=frame.branch_id, physics_step=frame.physics_step,
                  sim_time_s=frame.sim_time_s, physics_steps_advanced=0,
                  rendering_scope="one requested view; Nyx may internally batch its camera rig",
                  near_scope="pixel crop of real Nyx frame; no new camera viewpoint")
    write_json_atomic(folder / "frame.json", result)
    return result
