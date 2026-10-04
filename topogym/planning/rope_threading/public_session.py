"""Reuse the contact_relaxed_v16 relay in one Harbor-owned frozen Session."""
from pathlib import Path

from topogym.config.scene import load_scene_config
from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.simulator.config import SimulatorConfig
from topogym.utils.arrays import to_numpy
from topogym.utils.io import to_jsonable, write_json_atomic
from .profiles import contact_relaxed_profile, reference_samples
from .relay_artifact import load_plan, validate_scene
from .relay_feedback import MeasuredKeeperPlanner
from .relay_policy import RopeRelayPolicy, LiveArmIK


def run_feedback_policy(session, output, *, variation="easy"):
    if session.task != "rope_threading" or session.n_steps or session._resets:
        raise ValueError("Rope reference requires a fresh frozen Rope Session")
    env, output = session.env, Path(output)
    profile = contact_relaxed_profile(variation)
    expected = to_jsonable(SimulatorConfig(**profile["simulator_overrides"]))
    actual = to_jsonable(env.config)
    for name in profile["simulator_overrides"]:
        # Stored IPC state replaces settling, preserving the same episode birth.
        if actual[name] != expected[name]:
            raise ValueError(f"Rope reference differs from frozen simulator option: {name}")
    samples, metadata = load_plan(reference_samples(variation), variant=variation, seed=env.config.seed)
    if metadata["identity"].get("task_parameters") != profile["task_parameters"]:
        raise ValueError("Rope samples do not belong to the selected development profile")
    assets = Path(next(e.asset_path for e in env._scene_spec.entities if e.name == "rope")).parent
    validate_scene(metadata, task=env._task, scene=load_scene_config(env.config),
                   home_qpos=to_numpy(env._robot.entity.get_qpos()).reshape(-1), asset_dir=assets)
    policy = RopeRelayPolicy(samples,
        kinematics=LiveArmIK(env._robot, max_branch_step_rad=1.2, position_tolerance_m=1e-4,
                             orientation_tolerance_rad=1e-3),
        speed_m_s=.12, free_speed_m_s=.25, control_dt_s=1. / session.control_hz,
        material_feedback=True, settle_s=30., max_feedback_m=.08,
        keeper_planner=MeasuredKeeperPlanner(output / "keeper", metadata, normalize=True), measured_regrasps=True)
    report = dict(status="running", profile=profile["name"], harbor_qualified=False)
    try:
        result = SessionPolicyRunner(session).run_policy(request_id="rope-relay-" + variation, policy=policy,
            submission_hash=session.instance_sha, state_fields=("world",))
        report.update(result=result, task_success=bool(session.success()), status="finished")
    finally:
        report.update(last_phase=policy.phase, tracking=to_jsonable(policy.tracking))
        write_json_atomic(output / "relay_report.json", report)
    return report
