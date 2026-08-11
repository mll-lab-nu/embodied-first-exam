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
    """Resolve ``recording.camera`` to camera names.

    Accepts a list as well as the comma-separated string, because Hydra rejects
    a bare `recording.camera=oblique,topdown` as ambiguous and the first fix it
    suggests is the list form `[oblique,topdown]`. Taking only the string would
    send anyone who follows that advice into an "unknown camera ['oblique'"
    error instead.
    """

    available_names = sorted(str(name) for name in cameras.keys())
    if OmegaConf.is_config(camera_spec):
        camera_spec = OmegaConf.to_container(camera_spec, resolve=True)
    if isinstance(camera_spec, (list, tuple)):
        selected = [str(name).strip() for name in camera_spec if str(name).strip()]
    else:
        camera = str(camera_spec)
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
