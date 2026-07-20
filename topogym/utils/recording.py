from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

from omegaconf import OmegaConf

from .hud import HudSource, draw_hud_overlay, hud_lines


DEFAULT_RECORDING_CONFIG = {
    "enabled": False,
    "path": None,
    "camera": "oblique",
    "fps": 30,
    "res": None,
    "antialiasing": False,
    "every_n_steps": 1,
}


def _default_recording_config(*, default_fps: int, default_camera: str) -> dict:
    config = dict(DEFAULT_RECORDING_CONFIG)
    config["fps"] = int(default_fps)
    config["camera"] = str(default_camera)
    return config


def add_recording_args(parser, *, default_fps: int = 30, default_camera: str = "oblique") -> None:
    """Add legacy argparse flags that map cleanly onto ``cfg.recording``."""
    parser.set_defaults(_recording_default_fps=default_fps, _recording_default_camera=default_camera)
    group = parser.add_argument_group("recording")
    group.add_argument("--record-video", type=Path, default=None, help="Save an offscreen mp4 to this path.")
    group.add_argument("--record-fps", type=int, default=None, help="Playback FPS for the saved video.")
    group.add_argument(
        "--record-camera",
        default=None,
        help="Camera name from env.cameras. Use comma-separated names or 'all' for multi-view recording.",
    )
    group.add_argument(
        "--record-every-n-steps",
        type=int,
        default=None,
        help="Capture one video frame every N scene.step() calls.",
    )
    group.add_argument(
        "--record-res",
        type=int,
        nargs=2,
        metavar=("WIDTH", "HEIGHT"),
        default=None,
        help="Override the selected recording camera resolution.",
    )
    group.add_argument(
        "--record-aa",
        action="store_true",
        default=None,
        help="Enable antialiasing for recorded frames.",
    )


def recording_config_from_args(args) -> dict:
    """Translate current argparse recording flags into a Hydra-friendly config section."""
    updates = {}
    path = getattr(args, "record_video", None)
    if path is not None:
        updates["enabled"] = True
        updates["path"] = str(path)

    camera = getattr(args, "record_camera", None)
    if camera is not None:
        updates["camera"] = str(camera)

    fps = getattr(args, "record_fps", None)
    if fps is not None:
        updates["fps"] = int(fps)

    every_n_steps = getattr(args, "record_every_n_steps", None)
    if every_n_steps is not None:
        updates["every_n_steps"] = int(every_n_steps)

    res = getattr(args, "record_res", None)
    if res is not None:
        updates["res"] = [int(res[0]), int(res[1])]

    antialiasing = getattr(args, "record_aa", None)
    if antialiasing is not None:
        updates["antialiasing"] = bool(antialiasing)
    return updates


def merge_recording_config(cfg, args):
    """Merge argparse recording flags into ``cfg.recording`` and apply camera overrides."""
    defaults = _default_recording_config(
        default_fps=getattr(args, "_recording_default_fps", DEFAULT_RECORDING_CONFIG["fps"]),
        default_camera=getattr(args, "_recording_default_camera", DEFAULT_RECORDING_CONFIG["camera"]),
    )
    cfg = OmegaConf.merge({"recording": defaults}, cfg)
    updates = recording_config_from_args(args)
    if updates:
        cfg = OmegaConf.merge(cfg, {"recording": updates})
    return apply_recording_camera_overrides(cfg)


def apply_recording_camera_overrides(cfg):
    """Apply ``cfg.recording.res`` to selected env cameras before scene build."""
    if cfg.recording.res is None:
        return cfg

    if not hasattr(cfg, "env") or not hasattr(cfg.env, "cameras"):
        raise SystemExit("cfg.recording.res requires cfg.env.cameras to exist.")

    width, height = [int(value) for value in cfg.recording.res]
    if width <= 0 or height <= 0:
        raise SystemExit("recording.res values must be positive integers.")

    selected = _recording_camera_names(cfg.env.cameras, cfg.recording.camera)
    return OmegaConf.merge(
        cfg,
        {"env": {"cameras": {camera: {"res": [width, height]} for camera in selected}}},
    )


def _recording_camera_names(cameras: dict, camera_spec) -> list[str]:
    camera = str(camera_spec)
    available_names = sorted(str(name) for name in cameras.keys())
    if camera == "all":
        return available_names

    selected = [name.strip() for name in camera.split(",") if name.strip()]
    if not selected:
        raise SystemExit("recording.camera must name at least one camera.")

    missing = [name for name in selected if name not in cameras]
    if missing:
        available = ", ".join(available_names) or "<none>"
        raise SystemExit(f"Unknown recording camera(s) {missing}; available: {available}")
    return selected


def select_recording_cameras(cameras: dict, recording_cfg) -> list:
    """Return the selected camera list, or an empty list when recording is disabled."""
    if not bool(recording_cfg.enabled):
        return []

    return [cameras[name] for name in _recording_camera_names(cameras, recording_cfg.camera)]


def select_recording_camera_items(cameras: dict, recording_cfg) -> list[tuple[str, object]]:
    """Return selected ``(name, camera)`` pairs for recording."""
    if not bool(recording_cfg.enabled):
        return []
    return [(name, cameras[name]) for name in _recording_camera_names(cameras, recording_cfg.camera)]


def recording_session_from_config(scene, cameras: dict, recording_cfg, *, hud: HudSource = None):
    """Open a recording session using the normalized ``cfg.recording`` section."""
    return recording_session(
        scene,
        select_recording_camera_items(cameras, recording_cfg),
        save_to=recording_cfg.path,
        fps=int(recording_cfg.fps),
        antialiasing=bool(recording_cfg.antialiasing),
        every_n_steps=int(recording_cfg.every_n_steps),
        hud=hud,
    )


def print_recording_saved(recording_cfg) -> None:
    if bool(recording_cfg.enabled):
        camera = str(recording_cfg.camera)
        if "," in camera or camera == "all":
            print(f"saved multi-camera video set -> {recording_cfg.path}")
        else:
            print(f"saved video -> {recording_cfg.path}")


@contextmanager
def recording_session(
    scene,
    cameras: Iterable,
    *,
    save_to=None,
    fps: int = 30,
    antialiasing: bool = False,
    every_n_steps: int = 1,
    hud: HudSource = None,
):
    """Capture one frame per ``scene.step()`` from each camera, save on exit.

    The hook is installed by temporarily replacing ``scene.step`` so any caller
    (controllers, primitives, the demo's own loop) drives recording uniformly
    without knowing about it.

    If ``cameras`` is empty the context is a no-op (``save_to`` may be ``None``),
    which lets callers pass an empty list to disable recording without branching.
    ``antialiasing`` trades render speed for cleaner recorded edges.
    """
    camera_items = [_normalize_camera_entry(entry) for entry in cameras]
    if not camera_items:
        yield
        return

    if save_to is None:
        raise ValueError("save_to must be provided when cameras is non-empty.")

    every_n_steps = int(every_n_steps)
    if every_n_steps <= 0:
        raise ValueError("every_n_steps must be a positive integer.")

    for _name, cam in camera_items:
        cam.start_recording()

    original_step = scene.step
    step_counter = 0

    def wrapped_step(*args, **kwargs):
        nonlocal step_counter
        original_step(*args, **kwargs)
        step_counter += 1
        if step_counter % every_n_steps != 0:
            return
        for _name, cam in camera_items:
            update_dynamic_camera(cam)
            cam.render(antialiasing=antialiasing)
            recorded = getattr(cam, "_recorded_imgs", None)
            if recorded:
                recorded[-1] = draw_hud_overlay(recorded[-1], hud_lines(hud))

    scene.step = wrapped_step
    try:
        yield
    finally:
        scene.step = original_step
        save_to = Path(save_to)
        save_to.parent.mkdir(parents=True, exist_ok=True)
        multi_camera = len(camera_items) > 1
        for name, cam in camera_items:
            output_path = recording_camera_output_path(save_to, name) if multi_camera else save_to
            cam.stop_recording(save_to_filename=str(output_path), fps=fps)


def _normalize_camera_entry(entry):
    if isinstance(entry, tuple) and len(entry) == 2:
        return str(entry[0]), entry[1]
    camera = entry
    name = getattr(camera, "name", None)
    if name is None:
        name = f"camera_{getattr(camera, 'idx', 'unknown')}"
    return str(name), camera


def recording_camera_output_path(base_path: Path, camera_name: str) -> Path:
    suffix = base_path.suffix or ".mp4"
    stem = base_path.stem
    safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(camera_name))
    return base_path.with_name(f"{stem}_{safe_name}{suffix}")


def update_dynamic_camera(camera) -> None:
    if getattr(camera, "_attached_link", None) is not None:
        camera.move_to_attach()
    elif getattr(camera, "_followed_entity", None) is not None:
        camera.update_following()
