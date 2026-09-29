"""Segment media packaging using the shared recorder, frame clock and encoder."""
from dataclasses import replace
from pathlib import Path
import hashlib
import re

import numpy as np
from PIL import Image

from topogym.recording.session import RecordingSession
from topogym.recording.encoding import probe
from topogym.utils.io import write_json_atomic


def save_rgb(root, relative, frame):
    folder = Path(root) / relative
    folder.mkdir(parents=True, exist_ok=False)
    result = {}
    for name, pixels in frame.rgb.items():
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise ValueError("Invalid camera ID")
        path = folder / f"{name}.png"
        Image.fromarray(pixels).save(path)
        result[name] = str(path.relative_to(root))
    return result


class SegmentMedia:
    def __init__(self, root, segment_id, frame):
        self.root, self.segment_id = Path(root), segment_id
        self.order = tuple(frame.rgb)
        if "combined" in self.order:
            raise ValueError("Reserved composite camera identifier")
        self.last_frame = frame
        self.initial_state_id = frame.state_id
        self.initial_hashes = self.pixel_hashes(frame)
        self.session = RecordingSession(self.root / f"segments/segment_{segment_id}", fps=30,
            metadata=dict(camera_order=self.order, composition="horizontal, padded to common height"))
        self.session.__enter__()
        try:
            self.append(frame)
        except BaseException:
            self.session.close(commit=False)
            raise

    def composite(self, frame):
        if tuple(frame.rgb) != self.order:
            raise ValueError("Camera order changed")
        height = max(p.shape[0] for p in frame.rgb.values())
        images = [np.pad(frame.rgb[name], ((0, height-frame.rgb[name].shape[0]), (0, 0), (0, 0)))
                  for name in self.order]
        # The published frame map is a time/state index, not a camera-pose channel.
        # Authorized fixed calibration remains in the observation profile.
        return replace(frame, rgb=dict(frame.rgb, combined=np.concatenate(images, axis=1)),
                       camera_metadata={})

    @staticmethod
    def pixel_hashes(frame):
        return {name: hashlib.sha256(np.ascontiguousarray(pixels).tobytes()).hexdigest()
                for name, pixels in frame.rgb.items()}

    def append(self, frame):
        self.session.append(self.composite(frame))
        self.last_frame = frame

    def finish(self, *, complete=True):
        if complete:
            self.session.append_final(self.composite(self.last_frame))
            self.session.finish(dict(evidence_complete=True))
        self.session.close(commit=complete)
        videos, checks = {}, {}
        if complete:
            for name in (*self.order, "combined"):
                source = self.session.output / f"videos/{name}.mp4"
                check = probe(source, decode=True)
                if check["frames"] != self.session.frame_count:
                    raise ValueError("Video frame count differs from frame map")
                relative = str(source.relative_to(self.root))
                videos[name], checks[name] = relative, check
            write_json_atomic(self.session.output / "validation.json", checks)
        return dict(videos=videos,
                    frame_map=str((self.session.output / "frame_map.jsonl").relative_to(self.root)),
                    initial_frame_state_id=self.initial_state_id,
                    initial_frame_sha256=self.initial_hashes,
                    final_frame_sha256=self.pixel_hashes(self.last_frame), fps=self.session.fps,
                    camera_order=self.order, frame_count=self.session.frame_count,
                    presentation_padding_frames=self.session.presentation_padding_frames,
                    final_frame_state_id=self.last_frame.state_id)

    def abort(self):
        self.session.close(commit=False)
