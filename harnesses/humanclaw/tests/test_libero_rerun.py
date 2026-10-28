"""Reruns must restore saved state and reject source drift before paid work."""
from contextlib import nullcontext
import json

import pytest


@pytest.fixture
def runner(monkeypatch):
    from humanclaw_bench.libero import adapters, backend, run, service
    from humanclaw_bench.libero.smoke import ScriptedModel
    from humanclaw_bench.harnesses import runtime

    created, models = [], []

    class SnapshotRobot(backend.MockBackend):
        reset_position = 0
        changed_catalog = False

        def __init__(self, task, seed, directory, **kwargs):
            super().__init__()
            if self.changed_catalog:
                self.catalog[0]["description"] = "Changed observation capability"
                self.catalog_hash = backend.digest(self.catalog)
            self.position = self.reset_position
            self.source = {"source_tree_sha256": "fixture-source"}
            self.initial_snapshot = self.snapshot()
            self.journal = backend.MotionJournal(directory)
            self.journal.metadata("initial", {"snapshot": self.initial_snapshot})
            created.append(self)

        def manifest(self):
            return {"catalog_hash": self.catalog_hash, "controller": "fixture"}

        def snapshot(self):
            return {"position": self.position}

        def restore(self, snapshot):
            self.position = snapshot["position"]

        def close(self):
            self.journal.close()

    original_meter = service.MeteredService
    def meter(*args, **kwargs):
        model = ScriptedModel()
        models.append(model)
        return original_meter(*args, **kwargs, responder=model)

    # Keep the real runner, HTTP gateway, agent loop, journal and report code.
    # Only the expensive simulator, RoboRSI hooks and remote model are fixtures.
    monkeypatch.setattr(backend, "RoboBackend", SnapshotRobot)
    monkeypatch.setattr(backend, "source_identity", lambda _: {"source_tree_sha256": "fixture-source"})
    monkeypatch.setattr(run, "configure_roborsi", lambda *_: {})
    monkeypatch.setattr(adapters, "robor_instrumentation", lambda *_: nullcontext())
    monkeypatch.setattr(runtime, "native_connection", lambda _: ("http://unused", "unused"))
    monkeypatch.setattr(service, "MeteredService", meter)
    for key in ("OPENAI_BASE_URL", "OPENAI_API_BASE", "OPENAI_API_KEY",
                "ROBORSI_OPENAI_BASE_URL", "ROBORSI_OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    return run, SnapshotRobot, created, models


def test_rerun_restores_snapshot_in_new_attempt(runner, tmp_path):
    run, robot, created, models = runner
    args = dict(harness="bare", task="fixture/0", seed=0, output=tmp_path,
                config={"model": "fixture", "timeout_seconds": 20}, roboroot=tmp_path)
    original, first = run.run_episode(**args)
    assert first["outcome"]["benchmark_success"]
    robot.reset_position = 73  # Seed/reset alone must not determine a rerun.
    repeated, second = run.run_episode(**args, initial_from=original)
    assert repeated != original
    assert first["run_id"] != second["run_id"]
    assert json.loads((repeated / "initial_state.json").read_text()) == {"position": 0}
    assert created[-1].position == 2
    assert second["outcome"]["benchmark_success"]
    assert second["usage_coverage"] == 1
    assert len(models) == 2 and all(len(model.requests) == 2 for model in models)


def test_rerun_refuses_changed_catalog_before_model_request(runner, tmp_path):
    run, robot, _, models = runner
    args = dict(harness="bare", task="fixture/0", seed=0, output=tmp_path,
                config={"model": "fixture", "timeout_seconds": 20}, roboroot=tmp_path)
    original, _ = run.run_episode(**args)
    robot.changed_catalog = True
    repeated, report = run.run_episode(**args, initial_from=original)
    assert repeated != original
    assert report["outcome"]["infrastructure_error"]
    assert "drift" in report["outcome"]["error"]
    assert report["model_requests"] == 0
    assert len(models) == 1
