"""Separate current task progress, failure, evaluation switches and qualification."""
from .contracts import json_value


def summarize_task(info, task, *, exploration=False):
    info, task = json_value(info), json_value(task)
    result = task.get("result", {})
    support = info.get("support", {})
    success = info.get("task_success", result.get("task_success"))
    terminated = info.get("task_terminated", result.get("terminated"))
    reason = info.get("termination_reason") or result.get("reason")
    failed = bool(terminated and success is False)
    return dict(
        state=dict(episode_id=info.get("episode_id"), branch_id=info.get("branch_id"),
                   state_id=info.get("state_id"), control_step=info.get("control_step"),
                   physics_step=info.get("physics_step"), sim_time_s=info.get("sim_time_s")),
        progress=dict(goal_active=task.get("goal_active"), stable_time_s=task.get("stable_time_s"),
                      metrics=result.get("metrics", {}), task_success=success),
        outcome=dict(terminated=terminated, failed=failed, failure_code=info.get("failure_code"),
                     failure_reason=reason if failed else None, termination_reason=reason,
                     time_limit=reason == "time_limit"),
        evaluation=dict(goal_enabled=info.get("goal_evaluation_complete"),
                        measurement_status=info.get("evaluation_status", result.get("evaluation_status")),
                        terminal_revision=info.get("terminal_revision")),
        qualification=dict(registry_status=support.get("status"),
            validation_reference=support.get("validation"), declared_gaps=support.get("gaps", []),
            variation=support.get("variation"), grasp_assist=support.get("grasp_assist"),
            accepted_scope=None, evidence_status="historical_acceptance_not_resolved",
            note="registry support and the goal enable switch do not certify a task or this run"),
        exploration=bool(exploration), formal_qualification=False, physics_steps_advanced=0)
