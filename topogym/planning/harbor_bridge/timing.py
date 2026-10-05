"""Explicit manager-side conversion to the bound standard joint-step limit.

This creates a new, unqualified reference. It does not alter a task, a grader,
the source trajectory, or the strict one-row/one-control-step HTTP transport.
"""
import ast
import json
import math
from pathlib import Path

import numpy as np

from .contracts import BridgeError, MAX_ROWS, digest, load_trajectory


def joint_step_limit(tooling):
    """Read a literal from the bound tooling without importing simulator code."""
    values = []
    for node in ast.parse(Path(tooling).read_text()).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "JOINT_STEP_LIMIT_RAD" for target in node.targets):
            try:
                values.append(ast.literal_eval(node.value))
            except (ValueError, TypeError):
                raise BridgeError("Bound tooling has no literal joint-step limit") from None
    if (len(values) != 1 or type(values[0]) not in (int, float)
            or not math.isfinite(values[0]) or values[0] <= 0):
        raise BridgeError("Bound tooling must declare one positive joint-step limit")
    return float(values[0])


def rate_limit_rows(rows, layout, limit):
    """Keep each endpoint and switch grippers at the source row's first step.

    The first row is unchanged: the standard service still checks its reach
    from the actual initial command. No initial pose is invented from a trace.
    """
    rows = np.asarray(rows)
    if (rows.dtype != np.float32 or rows.ndim != 2 or rows.shape[1] != len(layout)
            or not 1 <= len(rows) <= MAX_ROWS or not np.isfinite(rows).all()
            or not math.isfinite(limit) or limit <= 0):
        raise BridgeError("Invalid rate-conversion inputs")
    grips = [i for i, name in enumerate(layout) if name.endswith("_gripper")]
    joints = [i for i in range(len(layout)) if i not in grips]
    if not grips or not joints:
        raise BridgeError("Rate conversion requires explicit joint and gripper columns")
    output, source_rows, changed = [rows[0].copy()], [0], []
    previous = rows[0].copy()
    for index, target in enumerate(rows[1:], 1):
        begin = len(output)
        while True:
            if len(output) >= MAX_ROWS:
                raise BridgeError("Rate-converted trajectory exceeds the row budget")
            delta = target[joints].astype(np.float64) - previous[joints]
            command = target.copy()
            if np.any(np.abs(delta) > limit):
                command[joints] = previous[joints].astype(np.float64) + np.clip(delta, -limit, limit)
                # Outward float32 rounding can cause the server's ceil() to
                # insert another step even when the mathematical delta fits.
                over = np.abs(command[joints].astype(np.float64) - previous[joints]) > limit
                columns = np.asarray(joints)[over]
                command[columns] = np.nextafter(command[columns], previous[columns])
                if np.array_equal(command[joints], previous[joints]):
                    raise BridgeError("Joint-step limit is below float32 resolution")
            output.append(command)
            source_rows.append(index)
            previous = command
            if np.array_equal(command, target):
                break
        if len(output) - begin > 1:
            changed.append(dict(source_row=index, first_output_row=begin, output_rows=len(output) - begin))
    return np.asarray(output, dtype=np.float32), np.asarray(source_rows, dtype=np.int64), changed


def convert_trajectory(source, destination, binding, tooling):
    rows, _ = load_trajectory(source, binding)
    instance = binding["instance"]
    limit = joint_step_limit(tooling)
    converted, source_rows, changed = rate_limit_rows(rows, instance["action_layout"], limit)
    report = dict(kind="standard_joint_rate_limit_v1", harbor_qualified=False,
                  source_sha256=digest(source), tooling_sha256=digest(tooling), joint_step_limit_rad=limit,
                  source_rows=len(rows), output_rows=len(converted), inserted_rows=len(converted) - len(rows),
                  changed_rows=changed, first_row="unchanged; checked by standard service against initial command",
                  grippers="source target applied at first substep; no width conversion",
                  scope="new nominal action timing; independent live execution and replay required")
    # Preserve identity, not success/recording metadata from the old execution.
    np.savez(destination, actions=converted, action_layout=np.asarray(instance["action_layout"]),
             task=instance["task"], instance_sha=instance["state_sha"], scene_seed=instance["simulator"]["seed"],
             physics_steps_per_action=np.full(len(converted), instance["simulator"]["control_decimation"], dtype=np.int64),
             trajectory_version=2, source_row_indices=source_rows, meta=json.dumps(report))
    load_trajectory(destination, binding)
    report["output_sha256"] = digest(destination)
    return report
