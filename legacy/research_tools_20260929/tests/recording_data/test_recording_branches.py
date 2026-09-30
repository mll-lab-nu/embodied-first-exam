"""公共录制的同步、分支边界和不完整产物；只编写，未运行。

使用小型 fake writer，不调用 ffmpeg，也不据此证明 MP4 编解码正确。
"""
import json
from pathlib import Path

import numpy as np
import pytest

from topogym.recording import RecordingSession
from topogym.sensors.observation import SensorFrame
from topogym.utils.snapshots import freeze


class MemoryWriter:
    instances = []

    def __init__(self, path, fps):
        self.path, self.fps = Path(path), fps
        self.frames = []
        self.commit = None
        type(self).instances.append(self)

    def append_data(self, image):
        self.frames.append(np.array(image, copy=True))

    def close(self, *, commit=True):
        self.commit = commit
        if commit:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Only a hashing/publication fixture: these bytes are not a video.
            self.path.write_bytes(b"fake-writer-output")


@pytest.fixture(autouse=True)
def reset_memory_writers():
    MemoryWriter.instances = []


def frame(*, state_id=0, branch_id=0, time=0.0, value=7):
    images = {"front": np.full((2, 2, 3), value, dtype=np.uint8),
              "wrist": np.full((2, 2, 3), value + 1, dtype=np.uint8)}
    return SensorFrame("episode-A", branch_id, state_id, int(round(time / 0.01)),
                       time, freeze(images), freeze({"front": {"pose": [1, 0, 0]}}))


def test_views_share_source_state_and_repeated_frames_keep_identity(tmp_path):
    with RecordingSession(tmp_path / "recording", fps=20, writer_factory=MemoryWriter) as recording:
        recording.append(frame())
        recording.append(frame(state_id=10, time=0.1, value=12))
        recording.finish({"task_success": False})
    rows = [json.loads(line) for line in (recording.output / "frame_map.jsonl").read_text().splitlines()]
    assert [row["video_frame_index"] for row in rows] == [0, 1, 2]
    assert [row["source_state_id"] for row in rows] == [0, 10, 10]
    assert rows[1]["target_video_time_s"] == pytest.approx(0.05)
    assert rows[1]["source_sim_time_s"] == pytest.approx(0.1)
    assert len(MemoryWriter.instances) == 2
    assert all(len(writer.frames) == 3 for writer in MemoryWriter.instances)
    assert all(writer.commit is True for writer in MemoryWriter.instances)
    manifest = json.loads((recording.output / "recording_manifest.json").read_text())
    assert manifest["recording_status"] == "complete"
    assert manifest["result"]["task_success"] is False


def test_branch_change_is_rejected_instead_of_splicing_video(tmp_path):
    with pytest.raises(ValueError, match="branch changed"):
        with RecordingSession(tmp_path / "old", writer_factory=MemoryWriter) as recording:
            recording.append(frame(state_id=10, time=0.1))
            recording.append(frame(state_id=11, branch_id=1, time=0.0))
    manifest = json.loads((recording.output / "recording_manifest.json").read_text())
    assert manifest["recording_status"] == "incomplete"
    assert all(writer.commit is False for writer in MemoryWriter.instances)
    assert all(not writer.path.exists() for writer in MemoryWriter.instances)


def test_new_session_records_restored_branch_with_its_actual_time(tmp_path):
    with RecordingSession(tmp_path / "branch_0", writer_factory=MemoryWriter) as first:
        first.append(frame(state_id=10, time=0.1))
        first.finish({})
    with RecordingSession(tmp_path / "branch_1", writer_factory=MemoryWriter) as second:
        second.append(frame(state_id=11, branch_id=1, time=0.0))
        second.finish({})
    row = json.loads((second.output / "frame_map.jsonl").read_text())
    assert row["source_sim_time_s"] == 0.0
    assert row["source_state_id"] == 11
    assert row["branch_id"] == 1
    assert json.loads((first.output / "recording_manifest.json").read_text())["branch_id"] == 0


def test_missing_finish_leaves_output_incomplete(tmp_path):
    with RecordingSession(tmp_path / "unfinished", writer_factory=MemoryWriter) as recording:
        recording.append(frame())
    assert all(writer.commit is False for writer in MemoryWriter.instances)
    assert json.loads((recording.output / "recording_manifest.json").read_text())["recording_status"] == "incomplete"


def test_invalid_second_view_cannot_advance_first_writer(tmp_path):
    good = frame()
    bad = SensorFrame(good.episode_id, good.branch_id, good.state_id,
                      good.physics_step, good.sim_time_s,
                      freeze({"front": good.rgb["front"], "wrist": np.zeros((2, 2), dtype=np.uint8)}),
                      good.camera_metadata)
    with pytest.raises(ValueError, match="RGB"):
        with RecordingSession(tmp_path / "bad", writer_factory=MemoryWriter) as recording:
            recording.append(bad)
    assert all(not writer.frames for writer in MemoryWriter.instances)
