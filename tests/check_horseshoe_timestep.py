"""Reject misleading timestep comparisons despite individually valid runs."""
from pathlib import Path

from omegaconf import OmegaConf
import pytest

from topogym.tasks.horseshoe_ring import verify_physical


@pytest.fixture
def paired_runs(tmp_path, monkeypatch):
    first, second = tmp_path/"baseline", tmp_path/"half"
    sources = ("execution_source.py", "physical_demo.py", "physical_plan.py",
               "physical_extraction.py", "physical_place.py", "scene.py",
               "robot_motion.py", "robot_clearance.py", "source_motion.json", "input_template.json")
    for folder, dt in ((first, .002), (second, .001)):
        folder.mkdir()
        for name in sources:
            (folder/name).write_text("same preserved source")
        (folder/"assets").mkdir()
        (folder/"assets/robot.urdf").write_text("same built model")
        OmegaConf.save(OmegaConf.create(dict(env=dict(sim=dict(dt=dt, substeps=4, gravity=[0, 0, -9.81])),
            task=dict(template_path=str(folder/"input_template.json")), run=dict(output=str(folder)),
            controller=dict(kp=[10000, 18000]))), folder/"config.yaml")
    # Individual execution validation has its own real-run checks. These tests
    # exercise the additional cross-run gates using already-qualified inputs.
    monkeypatch.setattr(verify_physical, "verify_run", lambda p: dict(passed=True,
        dt=float(OmegaConf.load(Path(p)/"config.yaml").env.sim.dt), final_ring_height_m=.922443))
    return first, second


def test_matching_conditions_allow_different_planned_trajectories(paired_runs):
    first, second = paired_runs
    (first/"planned_extraction.json").write_text('{"path":"one"}')
    (second/"planned_extraction.json").write_text('{"path":"another"}')
    result = verify_physical.compare_runs(first, second)
    assert result["passed"]
    assert result["fixed_trajectory_convergence_verified"] is False


@pytest.mark.parametrize("change,failed_check", [
    ("gain", "same_configuration_except_dt_and_paths"),
    ("template", "same_template"),
    ("policy", "same_execution_sources"),
    ("mesh", "same_built_geometry"),
    ("dt", "timestep_halved"),
])
def test_rejects_changed_comparison_conditions(paired_runs, change, failed_check):
    first, second = paired_runs
    if change in ("gain", "dt"):
        cfg = OmegaConf.load(second/"config.yaml")
        if change == "gain":
            cfg.controller.kp[0] *= 2
        else:
            cfg.env.sim.dt = .0015
        OmegaConf.save(cfg, second/"config.yaml")
    else:
        name = {"template": "input_template.json", "policy": "physical_plan.py", "mesh": "assets/robot.urdf"}[change]
        (second/name).write_text("changed")
    result = verify_physical.compare_runs(first, second)
    assert result["passed"] is False
    assert result["checks"][failed_check] is False
