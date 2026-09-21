"""Seed contract, linked dimensions, snapshot integrity and fail-closed retries."""
from copy import deepcopy
import json

import numpy as np
from omegaconf import OmegaConf
import pytest

from topogym.tasks.horseshoe_ring.variant_generator import (
    create_instance, validate_instance, retarget_seed, digest)
from topogym.tasks.horseshoe_ring import variant_pipeline
from topogym.tasks.horseshoe_ring.robot_motion import Kinematics


def test_seed_order_roundtrip_and_common_spec():
    first = {s: create_instance(s) for s in (0, 7, 42, 123)}
    reverse = {s: create_instance(s) for s in (123, 42, 7, 0)}
    assert first == reverse
    assert len({v["instance_id"] for v in first.values()}) == 4
    assert len({digest(v["parameters"]) for v in first.values()}) == 4
    for value in first.values():
        restored = json.loads(json.dumps(value))
        assert validate_instance(restored) == value
        assert value["episode_spec"]["variant"]["instruction"]
        assert value["resolved_config"]["run"]["output"] is None
        assert value["resolved_config"]["run"]["record_video"] is False
        assert value["episode_spec"]["resolved_config"]["task"]["scale"] == 2*value["parameters"]["scale_ratio"]
        assert value["evidence"] == dict(status="proposed", physics="not_run", accepted=False)


@pytest.mark.parametrize("family", ["F1", "F2", "F3"])
def test_anchor_freezes_micro_axes_and_retry_preserves_family(family):
    anchor = create_instance(11, family=family, jitter=False)
    assert anchor["parameters"] == anchor["resolved_config"]["task"]["generation"]["anchor_parameters"]
    first, retry = (create_instance(11, family=family, attempt=k) for k in (0, 1))
    assert first["parameters"]["family_id"] == retry["parameters"]["family_id"] == family
    assert first["parameters"] != retry["parameters"]


@pytest.mark.parametrize("seed", [-1, True, 1.5, 2**63])
def test_invalid_seed_rejected(seed):
    with pytest.raises(ValueError):
        create_instance(seed)


def test_snapshot_and_execution_profile_tampering_rejected():
    value = create_instance(7)
    for field in ("parameters", "episode_spec"):
        changed = deepcopy(value)
        if field == "parameters":
            changed[field]["scale_ratio"] = 3
        else:
            changed[field]["execution_profile"]["parameters"]["planning_seed"] += 1
        with pytest.raises(ValueError):
            validate_instance(changed)


def test_small_geometry_change_recomputes_initial_ik():
    value = create_instance(7, family="F2")
    cfg = OmegaConf.create(value["resolved_config"])
    result = retarget_seed(value, cfg)
    assert result["variant_retargeting"]["instance_id"] == value["instance_id"]
    assert max(result["variant_retargeting"]["maximum_ik_error"]) < .0005
    assert result["report"]["scene_scale"] == cfg.task.scale
    assert np.isfinite(np.array([f["qpos"] for f in result["frames"]])).all()
    assert result["variant_retargeting"]["qualification"] == "IK only; physics not implied"


def test_failed_physics_never_returns_accepted_candidate(tmp_path, monkeypatch):
    release = tmp_path/"release.json"
    release.write_text('{"visual_review_passed": true}')
    monkeypatch.setattr(variant_pipeline, "FAMILY_RELEASE", release)
    calls = []
    def reject(path, output, dt):
        calls.append(json.loads(path.read_text()))
        raise RuntimeError("injected physical collision")
    monkeypatch.setattr(variant_pipeline, "execute_instance", reject)
    with pytest.raises(RuntimeError, match="No qualified"):
        variant_pipeline.generate_validated(tmp_path/"failed", 42, max_attempts=2)
    assert len(calls) == 2
    assert len({v["parameters"]["family_id"] for v in calls}) == 1
    ledger = json.loads((tmp_path/"failed/attempts.json").read_text())
    assert ledger["accepted"] is False
    assert all("injected physical collision" in r["rejection"] for r in ledger["attempts"])
    assert not (tmp_path/"failed/accepted_instance.json").exists()


def test_success_only_returns_verified_attempt(tmp_path, monkeypatch):
    release = tmp_path/"release.json"
    release.write_text('{"visual_review_passed": true}')
    monkeypatch.setattr(variant_pipeline, "FAMILY_RELEASE", release)
    calls = []
    def execute(path, output, dt):
        calls.append(dt)
        output.mkdir()
    monkeypatch.setattr(variant_pipeline, "execute_instance", execute)
    monkeypatch.setattr(variant_pipeline, "qualify", lambda *a, **k: dict(accepted=True, checks={"fixture": True}))
    value = variant_pipeline.generate_validated(tmp_path/"ok", 42, family="F3", max_attempts=1)
    assert calls == [.002, .001]
    assert value["qualification"]["accepted"]
    assert (tmp_path/"ok/accepted_instance.json").is_file()
    assert not list((tmp_path/"ok").rglob("*.h5"))


def test_unreleased_families_cannot_generate_accepted_instances(tmp_path, monkeypatch):
    monkeypatch.setattr(variant_pipeline, "FAMILY_RELEASE", tmp_path/"missing.json")
    with pytest.raises(ValueError, match="Release all three"):
        variant_pipeline.generate_validated(tmp_path/"blocked", 1)
    assert not (tmp_path/"blocked").exists()


def test_family_gate_rejects_a_solved_route_from_the_wrong_family(tmp_path, monkeypatch):
    from topogym.tasks.horseshoe_ring.variant_generator import VERSION
    base = np.column_stack([np.linspace(0, .2, 30), np.zeros(30), np.zeros(30)])
    refs = {"F1": base, "F2": base+[0, .15, 0], "F3": base+[0, 0, .15]}
    release = tmp_path/"release.json"
    release.write_text(json.dumps(dict(generator_version=VERSION, passed=True, visual_review_passed=True,
        routes_m={k: v.tolist() for k, v in refs.items()})))
    monkeypatch.setattr(variant_pipeline, "FAMILY_RELEASE", release)
    p = dict(family_id="F1", yaw_deg=0., scale_ratio=1., translation_m=[0., 0., 0.])
    assert variant_pipeline.family_gate(base+[0, .05, .2], p)["passed"]
    assert not variant_pipeline.family_gate(refs["F2"]+[0, .05, .2], p)["passed"]


def test_unpaired_prototype_not_exposed_as_sampleable():
    from topogym.tasks.horseshoe_ring.variant_generator import validate_parameters
    value = create_instance(1)
    cfg = deepcopy(value["resolved_config"])
    cfg["task"]["generation"]["prototype_id"] = "ellipse"
    with pytest.raises(ValueError, match="not physically paired"):
        validate_parameters(cfg["task"])
