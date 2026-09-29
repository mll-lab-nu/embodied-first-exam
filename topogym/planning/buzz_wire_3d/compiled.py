"""Ordinary joint actions compiled from one selected development lineage.

This policy restores no simulator state. Qualification requires a new physical
execution from home, followed by an independent audit of that new episode.
"""


class CompiledJointPolicy:
    def __init__(self, document, *, action_limit=None):
        if document["schema"] != "buzz_compiled_joint_policy_v1":
            raise ValueError("Unknown compiled policy format")
        self.document = document
        self.actions = document["actions"] if action_limit is None else document["actions"][:action_limit]
        self.phase, self.tracking, self.samples = "compiled_joint_actions", {}, []

    def initialize(self, context):
        if context["action_spec"]["mode"] != "JOINT_ABS":
            raise ValueError("Compiled policy requires JOINT_ABS")
        if abs(context["timing_spec"]["control_dt_s"]-self.document["control_dt_s"]) > 1e-12:
            raise ValueError("Compiled action timing differs")
        self.index = 0

    def act(self, observation):
        state = observation["state"]
        if state["physics_step"] != self.index or state["branch_id"] != 0:
            raise ValueError("Compiled policy requires consecutive ticks from episode birth")
        events = observation["privileged"]["world"]["contact_events"]["events"]
        if any(e["touching"] and {e["role_a"], e["role_b"]} == {"robot", "wire_metal"} for e in events):
            raise RuntimeError("Robot touched the wire")
        if self.index == len(self.actions):
            return None
        self.tracking = {"action_index": self.index, "action_count": len(self.actions)}
        action = self.actions[self.index]
        self.index += 1
        return action
