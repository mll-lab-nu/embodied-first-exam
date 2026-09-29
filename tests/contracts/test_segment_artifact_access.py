"""Artifact IDs and log access stay within the granted episode."""
import pytest
from topogym.simulator import SegmentRunner
from topogym.simulator.rollout_simulation.artifacts import ArtifactStore


def test_log_permissions_and_paths(local_env, tmp_path):
    with SegmentRunner(local_env, tmp_path / "trail") as runner:
        ordinary = runner.interaction()
        privileged = runner.interaction(privileged=True)
        ordinary.run_segment(request_id="a", actions=[{"target": 1.}])
        with pytest.raises(PermissionError):
            ordinary.get_log(1, "physics_states")
        assert len(privileged.get_log(1, "physics_states")) == 3
        for kind in ("../config", "/etc/passwd", "config"):
            with pytest.raises(ValueError):
                privileged.get_log(1, kind)
        with pytest.raises(ValueError):
            ordinary.read_artifact("../private/physics_states.jsonl")
        assert not any(hasattr(ordinary, n) for n in ("reset", "close", "make", "config"))


def test_artifact_symlink_and_mutation_rejected(tmp_path):
    folder = tmp_path / "artifacts"
    folder.mkdir()
    path = folder / "public.png"
    path.write_bytes(b"real")
    store = ArtifactStore(folder)
    descriptor = store.add("public.png")
    assert store.read(descriptor["artifact_id"]) == b"real"
    private = store.add("public.png", private=True)
    with pytest.raises(PermissionError):
        store.read(private["artifact_id"])
    outside = tmp_path / "private"
    outside.write_bytes(b"secret")
    path.unlink()
    path.symlink_to(outside)
    with pytest.raises(ValueError):
        store.read(descriptor["artifact_id"])


def test_numeric_chunks_are_detached_and_privileged(local_env, tmp_path, monkeypatch):
    import numpy as np
    original = local_env._world.read_state
    def measured():
        return dict(original(), samples=np.arange(1000, dtype=np.float64))
    monkeypatch.setattr(local_env._world, "read_state", measured)
    with SegmentRunner(local_env, tmp_path / "arrays") as runner:
        actor = runner.interaction(privileged=True)
        row = actor.get_log(0, "physics_states")[0]
        ref = row["world"]["samples"]
        value = actor.get_log_array(ref["chunk_id"], ref["key"])
        np.testing.assert_array_equal(value, np.arange(1000))
        with pytest.raises(ValueError):
            value.setflags(write=True)
        with pytest.raises(PermissionError):
            runner.interaction().get_log_array(ref["chunk_id"], ref["key"])
        with pytest.raises(ValueError):
            actor.get_log_array("../config.json", "samples")
