"""Process-local world/probe checkpoints with explicit policy-state support."""
from copy import deepcopy
from uuid import uuid4

from .contracts import UnsupportedCapability, identifier


class Checkpoints:
    def __init__(self, owner):
        self.owner = owner
        self.records = {}
        self.names = {}
        self.sequence = 0

    def save(self, name, *, world_only=False):
        identifier(name)
        owner = self.owner
        states = {}
        for key, loaded in owner.policies.items():
            policy = loaded["policy"]
            if not world_only:
                if not all(callable(getattr(policy, method, None)) for method in ("save_debug_state", "load_debug_state")):
                    raise UnsupportedCapability("Policy lacks save_debug_state/load_debug_state; world_only=True discards it on restore")
                states[key] = dict(state=deepcopy(policy.save_debug_state()), initialized=loaded["initialized"])
        if owner.env is not None:
            owner.env._checkpoint_current()
        token = uuid4().hex
        self.sequence += 1
        row = dict(checkpoint_id=token, name=name, session_id=owner.session_id,
                   sequence=self.sequence, state_ref=owner.state_ref(), action_count=owner.action_count,
                   probe=owner.probe.snapshot() if owner.probe else None, policy_states=states,
                   world_only=world_only)
        self.records[token] = row
        self.names[name] = token
        return {key: row[key] for key in ("checkpoint_id", "name", "session_id", "state_ref", "world_only")}

    def restore(self, checkpoint):
        owner = self.owner
        if isinstance(checkpoint, dict):
            if checkpoint.get("session_id") != owner.session_id:
                raise ValueError("Checkpoint belongs to another session")
            token = checkpoint["checkpoint_id"]
        else:
            token = self.names.get(checkpoint, checkpoint)
        if token not in self.records:
            raise ValueError("Unknown checkpoint or invalidated future")
        row = self.records[token]
        if owner.env is not None:
            valid = {info.state_id for info in owner.env.state_history}
            if row["state_ref"]["state_id"] not in valid:
                raise ValueError("Checkpoint is from an invalidated future")
        if not set(row["policy_states"]) <= set(owner.policies):
            raise ValueError("Checkpoint policy instance is no longer available")
        try:
            if owner.env is not None:
                owner.runner.interaction(privileged=True).rewind_to(row["state_ref"])
            if owner.probe is not None:
                if row["probe"] is None:
                    owner.probe = None
                else:
                    owner.probe.restore(row["probe"])
            owner.policies = {k: v for k, v in owner.policies.items() if k in row["policy_states"]}
            for key, state in row["policy_states"].items():
                loaded = owner.policies[key]
                loaded["policy"].load_debug_state(deepcopy(state["state"]))
                loaded["initialized"] = state["initialized"]
            owner.action_count = row["action_count"]
            if owner.env is not None:
                owner.tracking.rewind([s.state_id for s in owner.env.state_history], owner.env._info())
            owner.windows.reset("rewind")
            owner.evidence.event("restore_committed", checkpoint_id=token,
                                 action_count=owner.action_count, state_ref=owner.state_ref())
        except BaseException:
            owner.poisoned = True  # A half-restored policy/world is never reused.
            raise
        obsolete = [key for key, other in self.records.items() if other["sequence"] > row["sequence"]]
        for key in obsolete:
            self.records.pop(key)
        self.names = {name: key for name, key in self.names.items() if key in self.records}
        return dict(restored=token, invalidated_checkpoints=obsolete, policy_count=len(owner.policies),
                    state_ref=owner.state_ref(), exploration=owner.evidence.exploration)
