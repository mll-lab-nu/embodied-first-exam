"""Real friction-pregrasp evidence tests, not successful-solution assertions.

Run explicitly with -m genesis. The recorded qualification can legitimately
fail; the test requires the policy to detect it and preserve actual evidence.
Full solution/three-reset qualification awaits a verified grasp/robot route.
"""
from dataclasses import asdict
import json
import os

import numpy as np
import pytest

from topogym.planning.rigid_reference.feedback import FrictionReferencePolicy, Limits

pytestmark = [pytest.mark.genesis, pytest.mark.rigid]


@pytest.mark.parametrize("variant", ["easy", "medium", "hard"])
def test_claws_hold_feedback_evidence_and_segment0_restore(tmp_path, variant):
    from scripts.run_rigid_reference_policy import oracle_for
    from topogym.simulator import Env, SimulatorConfig, SegmentRunner
    from topogym.simulator.rollout_simulation.segment_contract import fingerprint
    from topogym.utils.io import write_json_atomic
    import torch
    torch.set_num_threads(1)
    config = SimulatorConfig(task_id="interlocked_claws", variation_id=variant,
        compute_backend=os.environ.get("TOPOGYM_RIGID_POLICY_BACKEND", "cpu"), enable_rgb=False,
        enable_privileged=True, control_mode="EE_ABS", max_physics_steps=2000, work_dir=tmp_path/"scene")
    with Env(config) as env:
        env.reset(seed=0)
        oracle = oracle_for(env)
        initial_task = fingerprint(env._task.get_state())
        class Hold(FrictionReferencePolicy):
            task_id, robot_id, model_revision = "interlocked_claws", "aloha", env._task.model_revision
        policy = Hold(oracle=oracle, part="hold")
        with SegmentRunner(env, tmp_path/"rollout") as runner:
            result = runner.run_policy(request_id="hold", policy=policy,
                submission_hash=fingerprint(dict(oracle=oracle, limits=asdict(Limits()))),
                mode="unlimited", state_fields=("world",))
            initial = runner.initial["state_ref"]
        violated = any(p > policy.limits.grasp_translation_m or a > policy.limits.grasp_rotation_rad
                       for p, a in policy.max_drift.values())
        assert not env._task.result.task_success
        if violated:
            assert not policy.completed and result["reason"] == "policy_error"
            assert "grasp_slip" in policy.failure
        else:
            assert policy.completed or policy.failure  # No silent policy_done on missing contact.
        write_json_atomic(tmp_path/"hold_qualification.json", dict(variant=variant, result=result,
            observed_duration_s=env._world.sim_time_s, grasp_passed=policy.completed,
            maximum_grasp_drift=policy.max_drift, failure=policy.failure, task_success=False))
        assert (tmp_path/"rollout/private/physics_states.jsonl").stat().st_size > 0
        env.interaction(privileged=True).rewind_to(initial)
        assert fingerprint(oracle_for(env)["initial"]) == fingerprint(oracle["initial"])
        assert fingerprint(env._task.get_state()) == initial_task
        assert env._world.sim_time_s == 0.
