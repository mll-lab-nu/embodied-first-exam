"""Complete seed-0 Buzz references through the manager-owned Harbor Session.

Historical qualification supplies a strategy, never a score or simulator state.
The current frozen physics and grader remain authoritative.
"""
from dataclasses import asdict
import json

import numpy as np

from topogym.planning.harbor_bridge.actions import SessionPolicyRunner
from topogym.planning.harbor_bridge.callbacks import data_path, prepare_output, run_stages
from topogym.planning.harbor_bridge.contracts import digest, json_digest
from topogym.utils.io import to_jsonable, write_json_atomic
from .compiled import CompiledJointPolicy
from .stages import stages


def load_reference(variation):
    if variation not in {"easy", "medium", "hard"}:
        raise ValueError(f"No complete Harbor Buzz reference for {variation}")
    prefix = f"buzz_wire_3d/{variation}/"
    recipe = json.loads(data_path(prefix + "recipe.json").read_text())
    expected_kind = "staged_feedback" if variation == "easy" else "compiled_joint_actions"
    if (recipe.get("schema_version") != 1 or recipe.get("variation") != variation
            or recipe.get("seed") != 0 or recipe.get("kind") != expected_kind):
        raise ValueError("Buzz reference recipe identity differs")
    item = recipe["input"]
    expected_name = "selection.json" if variation == "easy" else "policy_actions.json"
    if item["file"] != expected_name:
        raise ValueError("Unexpected Buzz reference input")
    path = data_path(prefix + item["file"])
    if digest(path) != item["sha256"]:
        raise ValueError(f"Buzz reference input changed: {path.name}")
    document = json.loads(path.read_text())
    if variation == "easy":
        if [row["step"] for row in document] != recipe["steps"]:
            raise ValueError("Buzz easy reference must contain the complete stage sequence")
    elif (document.get("schema") != "buzz_compiled_joint_policy_v1"
            or document.get("seed") != recipe["seed"]
            or document.get("config", {}).get("variation_id") != variation
            or document.get("control_dt_s") != recipe["control_dt_s"]
            or len(document.get("actions", [])) != recipe["action_count"]):
        raise ValueError("Buzz compiled reference identity or action count differs")
    return recipe, document


def validate_session(session, variation, recipe):
    env, cfg = session.env, session.env.config
    state = env.tick_record()["state"]
    # oraclefix (lab, 2026-10-04): a Harbor Session restores its frozen birth on a new branch (branch_id 1, state_id 0)
    # before any action, so its first tick is on branch 1, not 0. The birth is state 0 at physics step 0 on the branch
    # the owner restored (the BUG 5 rule of solvability.py, also used by compiled.py); a fresh Session has no steps or resets.
    if (session.task != "buzz_wire_3d" or session.n_steps or session._resets
            or state["physics_step"] != 0 or state["state_id"] != 0):
        raise ValueError("Buzz reference requires a fresh, unrewound Buzz Session")
    if (cfg.seed != recipe["seed"] or cfg.robot_id != "panda_robotiq"
            or cfg.control_mode != "JOINT_ABS"
            or env._task.variation_id != "buzz_wire_3d_" + variation):
        raise ValueError("Buzz reference differs from frozen seed, robot, control mode or variation")
    if cfg.grasp_assist.model != "contact_weld_v1":
        raise ValueError("Buzz reference requires the declared contact_weld_v1 assistance")
    task = env._task
    geometry = dict(model_revision=task.model_revision, terminal_revision=task.terminal_revision,
                    layout=asdict(task.build_layout()), center_xy_m=to_jsonable(task.config["center_xy_m"]))
    if json_digest(geometry) != recipe["geometry_sha256"]:
        raise ValueError("Buzz reference differs from frozen layout, placement or revision")
    # Control cadence must match even when Harbor has a different integration
    # step/decimation. Do not replace the caller's physics with historical CPU settings.
    if abs(env.timing_spec["control_dt_s"] - recipe["control_dt_s"]) > 1e-12:
        raise ValueError("Buzz reference control timing differs from frozen Session")
    initial = env._robot.observe()["arm"]
    for key, expected in recipe["initial_robot"].items():
        actual = np.asarray(initial[key], dtype=float)
        if actual.shape != np.shape(expected) or not np.allclose(actual, expected, rtol=0., atol=1e-5):
            raise ValueError(f"Buzz reference requires the recorded default home: {key}")


def run_reference_policy(session, output, *, variation):
    output = prepare_output(session, output, __file__)
    recipe, document = load_reference(variation)
    report = dict(status="validating", variation=variation, policy_kind=recipe["kind"],
                  reference_sha256=recipe["input"]["sha256"],
                  source_evidence=recipe["provenance"],
                  frozen_config=to_jsonable(session.env.config), task_success=False,
                  harbor_qualified=False, scope="Current Session execution; independent Harbor grading required")
    try:
        validate_session(session, variation, recipe)
        report["status"] = "running"
        write_json_atomic(output / "reference_report.json", report)
        if recipe["kind"] == "staged_feedback":
            result = run_stages(session, output, stages, selection=document)
        else:
            policy = CompiledJointPolicy(document)
            result = SessionPolicyRunner(session).run_policy(
                request_id="buzz-reference-" + variation, policy=policy,
                submission_hash=recipe["input"]["sha256"], state_fields=("world",))
        report.update(result=to_jsonable(result), task_success=bool(session.success()))
        if not report["task_success"]:
            raise RuntimeError("Complete Buzz reference ended without current Task success")
        report["status"] = "native_success_verifier_pending"
        return report
    except Exception as error:
        report.update(status="failed", error=str(error))
        raise
    finally:
        report.update(control_steps=session.n_steps, physics_steps=session.env._world.physics_step)
        write_json_atomic(output / "reference_report.json", report)
