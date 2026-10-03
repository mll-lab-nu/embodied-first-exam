"""Passive diagnostics and native command export for private reference runs.

Native finger coordinates are NOT Harbor opening widths. Conversion must use
the target instance's robot adapter and must be physically replayed there.
"""
from pathlib import Path
import json
import time

import numpy as np

from topogym.utils.io import to_jsonable, write_json_atomic, sha256_file


class PolicyTrace:
    """Observe an ordinary policy without owning its physics or success rule."""

    def __init__(self, policy, output, *, before_phase=None):
        self.policy = policy
        self.output = Path(output)
        self.started = time.monotonic()
        self.phase = None
        self.last_write = -float("inf")
        self.events = []
        self.before_phase = before_phase

    def initialize(self, context):
        self.policy.initialize(context)

    def act(self, observation):
        try:
            action = self.policy.act(observation)
            if self.before_phase is not None and self.policy.phase != self.phase:
                self.before_phase(self.policy)
            return action
        finally:
            now = time.monotonic()
            phase = self.policy.phase
            state = observation["state"]
            if phase != self.phase:
                self.events.append(dict(phase=phase, sim_time_s=state["sim_time_s"],
                                        wall_time_s=now-self.started))
                self.phase = phase
            if now-self.last_write >= 1.:
                write_json_atomic(self.output / "policy_progress.json", dict(
                    phase=phase, sim_time_s=state["sim_time_s"],
                    wall_time_s=now-self.started, phases=self.events,
                    diagnostics=to_jsonable(self.policy.diagnostics)))
                self.last_write = now


def read_native_commands(execution, action_spec):
    """Read only committed controls from a continuous, unre-wound episode.

    Export every action, including holds, from executed_joint_targets. Measured
    qpos and proposed EE targets cannot reproduce the accepted command stream.
    A final partial control interval is retained explicitly in physics_steps.
    """
    execution = Path(execution)
    config = json.loads((execution / "config.json").read_text())
    timing = config["physics_dt_s"], config["control_decimation"]
    layout = []
    for side in action_spec["arms"]:
        layout.extend(action_spec["groups"][side]["arm_joint_names"])
        layout.append(side + "_native_gripper")
    rows, ticks, states = [], [], []
    previous_tick, episode = 0, None
    ended = False
    for line in (execution / "private/control_steps.jsonl").read_text().splitlines():
        event = json.loads(line)
        if event["kind"] != "completed":
            continue
        info = event["info"]
        if ended or info["branch_id"] != 0 or info["control_step"] != len(rows)+1:
            raise ValueError("Reference must be one continuous episode from default home")
        episode = episode or info["episode_id"]
        n = event["physics_steps"]
        if (info["episode_id"] != episode or type(n) is not int or not 1 <= n <= timing[1]
                or info["physics_step"] != previous_tick+n
                or not np.isclose(event["action_duration_s"], n*timing[0], rtol=0, atol=1e-10)):
            raise ValueError("Reference control/tick history is inconsistent")
        targets = info["executed_joint_targets"]
        row = []
        for side in action_spec["arms"]:
            joints = targets[side]["joint_position_rad"]
            if len(joints) != len(action_spec["groups"][side]["arm_joint_names"]):
                raise ValueError("Joint target layout changed during execution")
            row.extend(joints)
            row.append(targets[side]["gripper_position_m"])
        if not np.isfinite(row).all():
            raise ValueError("Nonfinite executed joint target")
        ended = bool(event["terminated"] or event["truncated"])
        if n != timing[1] and not ended:
            raise ValueError("Nonterminal partial controls cannot be replayed as ordinary steps")
        rows.append(row)
        ticks.append(n)
        states.append(info["state_id"])
        previous_tick = info["physics_step"]
    if not rows:
        raise ValueError("No committed controls to export")
    return dict(targets=np.asarray(rows, dtype=np.float64), physics_steps=np.asarray(ticks, dtype=np.int64),
                state_ids=np.asarray(states, dtype=np.int64), layout=np.asarray(layout),
                physics_dt_s=np.asarray(timing[0]), control_decimation=np.asarray(timing[1]))


def export_native_reference(execution, action_spec, report):
    """Write private evidence; this alone never certifies a Harbor reference."""
    execution = Path(execution)
    data = read_native_commands(execution, action_spec)
    destination = execution / "native_joint_targets.npz"
    with destination.open("xb") as stream:
        np.savez_compressed(stream, **data)
    manifest = dict(schema_version=1, artifact=destination.name, sha256=sha256_file(destination),
                    semantics="executed native joint targets; finger entries are native coordinates, not widths",
                    rows=len(data["targets"]), physics_steps=int(data["physics_steps"].sum()),
                    local_task_success=bool(report.get("task_success")), harbor_replay_qualified=False,
                    instance_id=report["instance_id"], asset_sha256=report["asset_sha256"],
                    source_manifest_sha256=sha256_file(execution / "source_manifest.json"),
                    config_sha256=sha256_file(execution / "config.json"))
    write_json_atomic(execution / "native_reference.json", manifest)
    return manifest
