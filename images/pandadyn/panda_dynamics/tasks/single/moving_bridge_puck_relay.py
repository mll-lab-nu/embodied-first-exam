import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import box, set_initial, position, velocity
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.props.mechanisms import passive_gate, gravity_channel
from panda_dynamics.tasks.predicates import crossed


class MovingBridgePuckRelay(PandaDynamicEnv):
    TASK = "S12-MovingBridgePuckRelay"
    NAMESPACE = "PandaMultiStage"
    TOOL = "paddle"
    TOOL_START = (-0.08, -0.15, 0.075)
    PHASES = (
        "incoming_strike",
        "physical_bridge_transfer",
        "exit_interception",
        "second_strike",
        "closing_gate_goal",
    )
    INSTRUCTION = (
        "将运动冰球击上实际转动的桥面，在出口重新截获，再击穿正在关闭的实体门并射门。"
    )

    def build_task(self):
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.07, -0.13, 0.0465],
            mass=self.params["object_mass"],
            mu=0.15,
            restitution=0.5,
        )
        # v5: (a) the lane's bridge-side edge is moved 25 mm toward the bridge
        # (y edge -0.070 -> -0.045): the bridge end only passes the old edge over
        # y in [-0.10, -0.07] (30 mm), narrower than the 44 mm puck. (b) The
        # three sliding surfaces now step down 2 mm at each hand-off (source
        # 0.034 -> bridge 0.032 -> exit 0.030 instead of all at 0.030): with
        # coplanar sharp edges the sliding puck's front face hit the bridge's
        # top edge with a horizontal contact normal and stopped (measured
        # 0.0047 N s at x=0.080, z=0.030). Length, far edge, friction unchanged.
        box(
            self.scene,
            "source_lane",
            [0.14, 0.0725, 0.012],
            [-0.08, -0.1175, 0.022],
            static=True,
            mu=0.025,
        )
        self.fixtures["bridge"] = single_axis(
            self.scene,
            "bridge",
            [0.18, -0.05, 0.032],
            kind="rotary",
            shape="platform",
            speed=0.35,
            force=0.5,
            mass=0.20,
            platform_half=(0.10, 0.05),
        )
        box(
            self.scene,
            "exit_lane",
            [0.16, 0.055, 0.014],
            [0.25, 0.12, 0.016],
            static=True,
            mu=0.04,
        )
        self.fixtures["gate"] = passive_gate(
            self.scene,
            "gate",
            [0.37, 0.18, 0.03],
            length=0.12,
            spring=0.00012,
            friction=0.00008,
            initial=1.1,
        )
        self.fixtures["gate"].joint.set_limits([[0.0, 1.3]])
        box(
            self.scene,
            "goal_backstop",
            [0.01, 0.07, 0.04],
            [0.54, 0.12, 0.04],
            static=True,
        )

    def reset_task(self):
        set_initial(
            self.objects["puck"],
            [0.06, -0.13 + self.rng.uniform(-0.012, 0.012), 0.0465],
            [-self.params["incoming_speed"], 0, 0],
        )
        self.fixtures["bridge"].reset(self.rng.uniform(-0.15, 0.15), 0.35)
        self.fixtures["gate"].reset(1.1, 0)
        self.events.flags.update(goal=[0.48, 0.12, 0.043])

    def update_task(self):
        contact = self.contact("puck", "tool")
        p = position(self.objects["puck"])
        if self.phase == 0 and contact:
            self.advance()
        elif self.phase == 1:
            if self.contact("puck", "bridge"):
                self.events.once("bridge_support", self.time)
            if (
                self.events.has("bridge_support")
                and self.contact("puck", "exit_lane")
                and not self.contact("puck", "bridge")
            ):
                self.advance(exit_velocity=velocity(self.objects["puck"]).tolist())
        elif self.phase == 2 and contact:
            self.advance()
        elif self.phase == 3:
            if not contact:
                self.events.flags.setdefault("separated", self.time)
            if (
                contact
                and self.time - self.events.flags.get("separated", self.time) > 0.035
            ):
                self.advance()
        elif self.phase == 4 and crossed(
            self, "puck", self.events.flags["goal"], half=0.045
        ):
            if not contact and self.fixtures["gate"].q > 0.20:
                self.advance()
                self.events.physical_success = True
            else:
                self.events.fail("closed_gate_or_carried_puck", self.time)
