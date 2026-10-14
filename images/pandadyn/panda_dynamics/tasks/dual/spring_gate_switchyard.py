import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.robots.arm import ArmSetup
from panda_dynamics.props.primitives import box, set_initial, position
from panda_dynamics.props.mechanisms import passive_gate
from panda_dynamics.tasks.predicates import bilateral_grip, crossed


class SpringGateSwitchyard(PandaDynamicEnv):
    TASK = "D07-SpringGateSwitchyard"
    NAMESPACE = "PandaMultiStage"
    LAYOUT = "facing_offset"
    ROLE_LABELS = (
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
        ("gate_operator", "preparing_striker"),
    )
    ARM_SETUPS = (
        ArmSetup(None, (0.04, -0.10, 0.16), base=(-0.55, -0.22, 0)),
        ArmSetup(
            "paddle",
            (0.30, -0.08, 0.045),
            base=(0.74, 0.22, 0),
            yaw=np.pi,
            quaternion=(0, 0, 0, 1),
        ),
    )
    ALLOW_FINGER_CONTACTS = True
    ALLOWED_FINGER_FIXTURES = ("gate",)
    PHASES = (
        "left_gate_open",
        "right_loop_shot",
        "gate_reconfiguration",
        "return_interception",
        "final_gate_shot",
    )
    INSTRUCTION = "左手实际握住弹簧门柄为右侧击球开路，在球绕行时改换门位，随后协同完成回球和最终射门。"

    def build_task(self):
        self.fixtures["gate"] = passive_gate(
            self.scene,
            "gate",
            [0.10, 0.05, 0.015],
            length=0.13,
            spring=0.015,
            friction=0.0002,
        )
        self.objects["puck"] = box(
            self.scene,
            "puck",
            [0.022, 0.022, 0.012],
            [0.20, -0.06, 0.013],
            mass=self.params["object_mass"],
            mu=0.01,
            restitution=0.65,
        )
        for name, half, p in (
            ("far_rail", [0.008, 0.18, 0.03], [-0.12, 0.05, 0.03]),
            ("upper_rail", [0.20, 0.008, 0.03], [0.08, 0.23, 0.03]),
            ("lower_rail", [0.20, 0.008, 0.03], [0.08, -0.15, 0.03]),
        ):
            box(self.scene, name, half, p, static=True, restitution=0.75)
        box(self.scene, "backstop", [0.01, 0.07, 0.03], [0.48, 0.15, 0.03], static=True)

    def reset_task(self):
        self.fixtures["gate"].reset(0, 0)
        set_initial(
            self.objects["puck"],
            [0.20, -0.06 + self.rng.uniform(-0.008, 0.008), 0.0125],
            [self.params["incoming_speed"], 0, 0],
        )
        self.events.flags.update(goal=[0.43, 0.15, 0.012])

    def update_task(self):
        gate = self.fixtures["gate"]
        if self.phase == 0 and bilateral_grip(self, "gate", "panda-0") and gate.q > 0.5:
            self.advance()
        elif self.phase == 1:
            if self.contact("puck", "right_tool"):
                self.events.once("first_shot", self.time)
            if (
                self.events.has("first_shot")
                and position(self.objects["puck"])[0] < -0.05
                and not self.contact("puck", "right_tool")
            ):
                self.advance()
        elif (
            self.phase == 2
            and bilateral_grip(self, "gate", "panda-0")
            and gate.q < -0.35
            and self.contact("puck", "upper_rail")
        ):
            self.advance()
        elif self.phase == 3 and self.contact("puck", "right_tool"):
            self.events.flags["return_strike"] = self.time
            self.advance()
        elif self.phase == 4:
            if (
                crossed(self, "puck", self.events.flags["goal"], half=0.055)
                and not self.contact("puck", "right_tool")
                and abs(gate.q) > 0.3
            ):
                self.advance()
                self.events.physical_success = True
