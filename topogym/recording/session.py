"""Consume sensor frames without owning a scene, a camera, or a physics clock."""
from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import TYPE_CHECKING

from topogym.utils.io import sha256_file, to_jsonable, write_json_atomic

from topogym.recording.encoding import VideoWriter
from topogym.recording.timeline import SimulationTimeline, positive

if TYPE_CHECKING:
    from topogym.sensors.observation import SensorFrame


class RecordingSession:
    """Write synchronized views of one episode branch.

    Call ``append(frame)`` with frames supplied by the simulator. No callback is
    installed on the engine. Restoring history starts a new branch, which must
    use a new session/output directory; video never splices the two timelines.
    ``finish`` declares output completion, independently of task success.
    """

    def __init__(self, output, *, fps=30, metadata=None, writer_factory=VideoWriter):
        self.output = Path(output)
        self.fps = positive(fps, "fps")
        self.metadata = to_jsonable(metadata or {})
        self.writer_factory = writer_factory
        self.writers = {}
        self.frame_count = 0
        self.source_count = 0
        self.identity = None
        self.previous_state_id = None
        self.result = None
        self.opened = self.closed = self.failed = False
        self.map = None
        self.invalidated_state_ids = set()
        self.source_state_ids = set()
        self.last_video_state_id = None
        self.presentation_padding_frames = 0

    def __enter__(self):
        if self.opened or self.closed:
            raise RuntimeError("A recording session cannot be reused")
        self.output.mkdir(parents=True, exist_ok=False)
        self.opened = True
        try:
            self.map = (self.output / "frame_map.jsonl").open("x", encoding="utf-8")
            self._status("recording")
        except BaseException:
            if self.map is not None:
                self.map.close()
            self.closed = True
            raise
        return self

    def _status(self, status, **extra):
        write_json_atomic(self.output / "recording_manifest.json", dict(
            schema_version=2, recording_status=status, fps=self.fps,
            episode_id=None if self.identity is None else self.identity[0],
            branch_id=None if self.identity is None else self.identity[1],
            frame_count=self.frame_count, source_frame_count=self.source_count,
            presentation_padding_frames=self.presentation_padding_frames,
            invalidated_state_ids=sorted(self.invalidated_state_ids),
            history_semantics="audit video; invalidated frames are not a live episode trajectory",
            metadata=self.metadata, **extra))

    def on_lifecycle(self, event):
        """Annotate abandoned frames without erasing the audit recording."""
        if self.identity is None or event["episode_id"] != self.identity[0]:
            return
        if event["kind"] == "rewind":
            self.invalidated_state_ids.update(set(event["invalidated_state_ids"]) & self.source_state_ids)
            if self.closed:
                path = self.output / "recording_manifest.json"
                manifest = json.loads(path.read_text())
                manifest["invalidated_state_ids"] = sorted(self.invalidated_state_ids)
                write_json_atomic(path, manifest)
            else:
                self._status("recording")

    def append(self, frame: SensorFrame):
        if not self.opened or self.closed or self.failed or self.result is not None:
            raise RuntimeError("Recording is not accepting frames")
        try:
            self._append(frame)
        except BaseException:
            self.failed = True
            raise

    def _append(self, frame):
        import numpy as np
        identity = (frame.episode_id, frame.branch_id)
        if (not isinstance(frame.episode_id, str) or not frame.episode_id or
            any(type(value) is not int or value < 0 for value in (frame.branch_id, frame.state_id, frame.physics_step)) or
            not math.isfinite(frame.sim_time_s) or frame.sim_time_s < 0):
            raise ValueError("SensorFrame requires valid episode, state and physical time metadata")
        if not frame.rgb:
            raise ValueError("Recording requires RGB in the supplied SensorFrame")
        # Validate all views before writing any of them; a malformed late view
        # must not leave the other cameras one frame ahead.
        for camera_id, value in frame.rgb.items():
            image = np.asarray(value)
            if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] != 3:
                raise ValueError(f"Camera {camera_id} must provide H x W x 3 uint8 RGB")
        if self.identity is None:
            self.identity = identity
            self.timeline = SimulationTimeline(self.fps, frame.sim_time_s)
            for camera_id in frame.rgb:
                if not isinstance(camera_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", camera_id):
                    raise ValueError("Camera identifiers must be safe filename components")
                self.writers[camera_id] = self.writer_factory(
                    self.output / "videos" / f"{camera_id}.mp4", self.fps)
        elif identity != self.identity:
            raise ValueError("Episode or branch changed; finish this recording and start a new session")
        if set(frame.rgb) != set(self.writers):
            raise ValueError("All views must be present in every source frame")
        if self.previous_state_id is not None and frame.state_id <= self.previous_state_id:
            raise ValueError("Source state identifiers must increase within a recording")
        poses = to_jsonable(frame.camera_metadata)
        # The target media time and measured source time are both kept. Repeated
        # frames are identified by the same state_id; no states are interpolated.
        for index, target_time in self.timeline.advance(frame.sim_time_s):
            for name, writer in self.writers.items():
                writer.append_data(frame.rgb[name])
            row = dict(video_frame_index=index, target_video_time_s=target_time,
                       source_sim_time_s=frame.sim_time_s, physics_step=frame.physics_step,
                       source_state_id=frame.state_id, episode_id=frame.episode_id,
                       branch_id=frame.branch_id, camera_metadata=poses)
            self.map.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
            self.map.flush()
            self.frame_count += 1
            self.last_video_state_id = frame.state_id
        self.source_count += 1
        self.source_state_ids.add(frame.state_id)
        self.previous_state_id = frame.state_id

    def append_final(self, frame):
        """Show the final measured state even between FPS grid points; no physics."""
        if not self.opened or self.closed or self.failed or self.result is not None:
            raise RuntimeError("Recording is not accepting frames")
        if frame.state_id != self.previous_state_id:
            self.append(frame)
        if (frame.episode_id, frame.branch_id) != self.identity:
            raise ValueError("Final frame belongs to a different branch")
        if self.last_video_state_id == frame.state_id:
            return
        try:
            for name, writer in self.writers.items():
                writer.append_data(frame.rgb[name])
            self.map.write(json.dumps(dict(video_frame_index=self.frame_count,
                target_video_time_s=self.frame_count / self.fps, source_sim_time_s=frame.sim_time_s,
                physics_step=frame.physics_step, source_state_id=frame.state_id,
                episode_id=frame.episode_id, branch_id=frame.branch_id,
                presentation_padding=True, camera_metadata=to_jsonable(frame.camera_metadata))) + "\n")
            self.map.flush()
            self.frame_count += 1
            self.presentation_padding_frames += 1
            self.last_video_state_id = frame.state_id
        except BaseException:
            self.failed = True
            raise

    def finish(self, result):
        """Attach the caller's result without inferring success from the video."""
        if not self.opened or self.closed or self.failed or self.result is not None:
            raise RuntimeError("Cannot finish this recording")
        if not self.frame_count:
            raise ValueError("Cannot finish an empty recording")
        if result is None:
            raise ValueError("A recording result must be explicit; use an empty mapping if no task result exists")
        self.result = to_jsonable(result)

    def close(self, *, commit=False):
        if self.closed:
            return
        if not self.opened:
            self.closed = True
            return
        complete = bool(commit and not self.failed and self.result is not None and self.frame_count)
        errors = []
        for writer in self.writers.values():
            try:
                writer.close(commit=complete)
            except Exception as error:
                errors.append(error)
        if self.map is not None:
            self.map.close()
        self.closed = True
        if errors:
            self.failed = True
            complete = False
        if complete:
            self._status("complete", result=self.result,
                         videos={name: dict(path=f"videos/{name}.mp4", sha256=sha256_file(
                             self.output / "videos" / f"{name}.mp4")) for name in self.writers},
                         frame_map=dict(path="frame_map.jsonl", sha256=sha256_file(self.output / "frame_map.jsonl")))
        else:
            self._status("incomplete", result=self.result,
                         errors=[f"{type(error).__name__}: {error}" for error in errors])
        if errors:
            raise errors[0]

    def __exit__(self, kind, value, traceback):
        try:
            self.close(commit=kind is None)
        except Exception:
            if kind is None:
                raise
        return False
