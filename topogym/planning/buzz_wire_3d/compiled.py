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
        self.physics_steps_per_action = int(context["timing_spec"]["control_decimation"])
        # oraclefix 13: joint targets stay 1 urad inside the public limits (a target exactly at a limit rounds outward
        # in the adapter's float32 check and the bridge refuses the row as clipped)
        self.joint_limits = {name: [(float(lo)+1e-6, float(hi)-1e-6) for lo, hi in group["joint_limits_rad"]]
                             for name, group in context["action_spec"].get("groups", {}).items()}

    def act(self, observation):
        state = observation["state"]
        if self.index == 0:
            # oraclefix (lab, 2026-10-04): a Harbor Session restores its frozen birth on a new branch (branch_id 1,
            # state_id 0) before any action. The birth is state 0 at physics step 0 on the branch the owner restored
            # (the BUG 5 rule of solvability.py); every later tick must stay on that branch.
            if state["state_id"] != 0:
                raise ValueError("Compiled policy requires consecutive ticks from episode birth")
            self.birth_branch_id = state["branch_id"]
        if (state["physics_step"] != self.index * self.physics_steps_per_action
                or state["branch_id"] != self.birth_branch_id):
            raise ValueError("Compiled policy requires consecutive ticks from episode birth")
        events = observation["privileged"]["world"]["contact_events"]["events"]
        if any(e["touching"] and {e["role_a"], e["role_b"]} == {"robot", "wire_metal"} for e in events):
            raise RuntimeError("Robot touched the wire")
        if self.index == len(self.actions):
            return None
        self.tracking = {"action_index": self.index, "action_count": len(self.actions)}
        action = self.actions[self.index]
        self.index += 1
        limits = getattr(self, "joint_limits", {})
        if any(isinstance(command, dict) and "joint_position_rad" in command and name in limits
               for name, command in action.items()):
            action = {name: (dict(command, joint_position_rad=[min(max(float(v), lo), hi) for v, (lo, hi) in
                                                                zip(command["joint_position_rad"], limits[name])])
                             if isinstance(command, dict) and "joint_position_rad" in command and name in limits
                             else command)
                      for name, command in action.items()}
        return action
