"""Native human-camera capture on simulation timestamps; no pose interpolation."""

from dataclasses import dataclass
from pathlib import Path
import json
import time
import numpy as np
import imageio.v2 as imageio


@dataclass(frozen=True)
class QualityPreset:
    width: int
    height: int
    fps: int


PRESETS = {
    "preview": QualityPreset(1280, 720, 30),
    "presentation": QualityPreset(1920, 1080, 60),
    "4k": QualityPreset(3840, 2160, 60),
}


def quality_preset(name):
    if name not in PRESETS:
        raise ValueError(f"Unknown quality {name!r}; choose {list(PRESETS)}")
    return PRESETS[name]


def camera_frame(env, camera="overview"):
    image = env.unwrapped.render_rgb_array(camera)
    if hasattr(image, "cpu"):
        image = image.cpu().numpy()
    image = np.asarray(image)
    return (image[0] if image.ndim == 4 else image).astype(np.uint8)


def annotate(image, env):
    """A compact header; overview framing reserves the upper background."""
    import cv2

    image = image.copy()
    scale = image.shape[1] / 1280
    band = round(57 * scale)
    cv2.rectangle(image, (0, 0), (image.shape[1], band), (29, 33, 35), -1)
    lines = [
        f"{env.TASK} | {env.difficulty} seed={env.seed_value} | t={env.time:.3f}s | {env.phase_name}",
        f"{len(env.arms)} Panda | valid={env.events.valid} accepted={env.events.physical_success and env.events.valid and not env.events.failure_reason} | {env.physics_hz} Hz | 1x | roles: {', '.join(env.arm_role_labels.values())}",
    ]
    for i, line in enumerate(lines):
        cv2.putText(
            image,
            line,
            (round(12 * scale), round((22 + 23 * i) * scale)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46 * scale,
            (245, 245, 242),
            max(1, round(scale)),
            cv2.LINE_AA,
        )
    return image


class PhysicsVideoCapture:
    """Observe existing substeps at round(n * physics_hz / fps), never step them."""

    def __init__(
        self,
        env,
        directory,
        quality="presentation",
        camera="overview",
        prefix="replay",
        source_rollout=None,
    ):
        self.env = env.unwrapped
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.preset = quality_preset(quality)
        if self.env.quality != quality:
            raise ValueError(
                "Environment human camera must be created with the selected quality"
            )
        self.camera, self.quality, self.prefix = camera, quality, prefix
        self.started = time.perf_counter()
        self.timestamps = []
        self.source_rollout = str(source_rollout) if source_rollout else None
        options = dict(
            fps=self.preset.fps,
            codec="libx264",
            pixelformat="yuv420p",
            macro_block_size=1,
            ffmpeg_params=[
                "-crf",
                "18",
                "-preset",
                "medium",
                "-movflags",
                "+faststart",
            ],
        )
        self.clean = imageio.get_writer(self.directory / f"{prefix}.mp4", **options)
        self.annotated = imageio.get_writer(
            self.directory / f"{prefix}-annotated.mp4", **options
        )
        self.index = 0
        self.env.capture_hook = self.sample
        self.sample(self.env)

    def sample(self, env):
        required_step = round(self.index * env.physics_hz / self.preset.fps)
        actual_step = round(env.time * env.physics_hz)
        if actual_step < required_step:
            return
        if actual_step > required_step:
            raise RuntimeError(
                "Skipped physics-time video sample; do not claim the target capture fps"
            )
        frame = camera_frame(env, self.camera)
        if frame.shape != (self.preset.height, self.preset.width, 3):
            raise RuntimeError(f"Native camera size mismatch: {frame.shape}")
        target = self.index / self.preset.fps
        self.timestamps.append(
            dict(
                index=self.index,
                target_time=target,
                simulation_time=env.time,
                phase=env.phase_name,
                physical_success=env.events.physical_success,
                valid=env.events.valid,
            )
        )
        self.clean.append_data(frame)
        self.annotated.append_data(annotate(frame, env))
        self.index += 1

    def close(self, validity=None):
        self.env.capture_hook = None
        self.clean.close()
        self.annotated.close()
        errors = [abs(t["simulation_time"] - t["target_time"]) for t in self.timestamps]
        result = dict(
            resolution=[self.preset.width, self.preset.height],
            fps=self.preset.fps,
            frames=self.index,
            frame_timestamps=self.timestamps,
            camera=self.camera,
            preset=self.quality,
            shader=self.env.shader,
            codec="libx264",
            crf=18,
            pixel_format="yuv420p",
            playback_rate=1,
            physics_hz=self.env.physics_hz,
            action_hz=100,
            seed=self.env.seed_value,
            source_rollout=self.source_rollout,
            capture="continuous physics action replay; nearest physics substep, no duplicate/interpolated frames",
            max_sampling_error_s=max(errors, default=0),
            simulation_duration=self.env.time,
            encoded_duration=self.index / self.preset.fps,
            export_wall_seconds=time.perf_counter() - self.started,
            validity=validity,
            physical_success=self.env.events.physical_success,
            success=bool(
                self.env.events.physical_success
                and self.env.events.valid
                and not self.env.events.failure_reason
            ),
            failure_reason=self.env.events.failure_reason,
            clean=f"{self.prefix}.mp4",
            annotated=f"{self.prefix}-annotated.mp4",
        )
        (self.directory / f"{self.prefix}-video.json").write_text(
            json.dumps(result, indent=2)
        )
        return result
