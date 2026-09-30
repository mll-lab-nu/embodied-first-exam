"""Real codec checks with synthetic frames; not a Genesis rendering claim."""
from dataclasses import replace
import json

import numpy as np
import pytest

from topogym.recording.segment import SegmentMedia
from topogym.sensors.observation import SensorFrame
from topogym.simulator import SegmentRunner


def frame(state=0, time=0.):
    return SensorFrame("episode", 0, state, state, time,
        {"a": np.full((16, 24, 3), state, dtype=np.uint8),
         "b": np.full((16, 24, 3), state+10, dtype=np.uint8)}, {})


@pytest.mark.parametrize("times", [[], [.01], [.025, .05]])
def test_final_state_and_all_views_are_encoded(tmp_path, times):
    media = SegmentMedia(tmp_path, 1, frame())
    for i, time in enumerate(times, 1):
        media.append(frame(i, time))
    result = media.finish()
    rows = [json.loads(s) for s in (media.session.output / "frame_map.jsonl").read_text().splitlines()]
    assert rows[-1]["source_state_id"] == len(times)
    assert result["final_frame_state_id"] == len(times)
    assert set(result["videos"]) == {"a", "b", "combined"}
    assert result["frame_count"] == len(rows)
    if times == [.01]:
        assert rows[-1]["presentation_padding"]
        assert result["presentation_padding_frames"] == 1
    assert all((tmp_path / path).is_file() for path in result["videos"].values())
    assert not list(tmp_path.rglob("*.png"))
    assert result["initial_frame_sha256"] == SegmentMedia.pixel_hashes(frame())


def test_encoder_failure_leaves_incomplete_recording(tmp_path, monkeypatch):
    media = SegmentMedia(tmp_path, 1, frame())
    def fail(image):
        raise OSError("encoder failed")
    monkeypatch.setattr(media.session.writers["b"], "append_data", fail)
    with pytest.raises(OSError):
        media.append(frame(1, .04))
    media.abort()
    manifest = json.loads((media.session.output / "recording_manifest.json").read_text())
    assert manifest["recording_status"] == "incomplete"
    assert not [p for p in tmp_path.rglob("videos/*.mp4") if not p.name.endswith(".part.mp4")]


def test_runner_rgb_finalization_and_public_artifacts(local_env, tmp_path, monkeypatch):
    env = local_env
    env._config = replace(env.config, enable_rgb=True)
    def sensor_frame():
        f = frame(env._state_id, env._world.sim_time_s)
        return replace(f, episode_id=env._episode_id, branch_id=env._branch_id,
                       physics_step=env._world.physics_step)
    monkeypatch.setattr(env, "sensor_frame", sensor_frame)
    with SegmentRunner(env, tmp_path / "trail") as runner:
        actor = runner.interaction()
        actor.begin_segment(request_id="rgb")
        actor.step({"target": 1.})
        result = actor.end_segment()
        assert result["evidence_complete"]
        assert result["media"]["final_frame_state_id"] == 3
        video = actor.read_artifact(result["media"]["videos"]["a"]["artifact_id"])
        assert video[4:8] == b"ftyp"
        assert result["media"]["final_frame_sha256"] == SegmentMedia.pixel_hashes(sensor_frame())
        assert not list(runner.root.rglob("*.png"))
        assert env._world.physics_step == 3
        assert actor.end_segment() == result


def test_media_finalize_failure_prevents_success_manifest(local_env, tmp_path, monkeypatch):
    env = local_env
    env._config = replace(env.config, enable_rgb=True)
    monkeypatch.setattr(env, "sensor_frame", lambda: replace(frame(env._state_id, env._world.sim_time_s),
        episode_id=env._episode_id, branch_id=env._branch_id, physics_step=env._world.physics_step))
    import topogym.recording.segment as module
    def fail(*args, **kwargs):
        raise RuntimeError("decode failed at private /path")
    with SegmentRunner(env, tmp_path / "bad_media") as runner:
        monkeypatch.setattr(module, "probe", fail)
        actor = runner.interaction()
        result = actor.run_segment(request_id="decode", actions=[])
        assert result["status"] == "incomplete"
        assert not result["evidence_complete"]
        assert result["reason"] == "evidence_error"
        assert "/path" not in str(result)
        assert env._world.physics_step == 0
        with pytest.raises(RuntimeError, match="faulted"):
            actor.begin_segment(request_id="later")
