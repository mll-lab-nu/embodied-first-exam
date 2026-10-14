import numpy as np
from panda_dynamics.base_env import PandaDynamicEnv
from panda_dynamics.props.primitives import ball, box, set_initial, position, velocity
from panda_dynamics.props.fixtures import single_axis
from panda_dynamics.props.mechanisms import gravity_channel, quat_xyz
from panda_dynamics.tasks.predicates import cup_catch, containment


class CupRouteDelivery(PandaDynamicEnv):
    TASK = "S01-CupRouteDelivery"
    NAMESPACE = "PandaMultiStage"
    INSTRUCTION = (
        "接住橙球，倒入指定 A/B 重力轨道，在出口反弹后再接住同一球，最后交给移动小车。"
    )
    PHASES = (
        "incoming_catch",
        "selected_route_entry",
        "track_and_rebound",
        "downstream_catch",
        "moving_cart_delivery",
    )
    REFERENCE_ACCELERATION = 0.3
    REFERENCE_JERK = 0.025
    TOOL_START = (-.16, -.32, .23)

    def build_task(self):
        self.objects["ball"] = ball(
            self.scene,
            "ball",
            self.params["radius"],
            self.params["object_mass"],
            self.params["restitution"],
        )
        self.routes = []
        for i, x in enumerate((-.12, .08)):
            self.routes.append(
                gravity_channel(
                    self.scene,
                    f"route_{i}",
                    [x, .23, self.params["track_height"]],
                    [x, -.12, self.params["track_height"]-self.params["track_drop"]],
                    wall=0.055, width=.06,
                )
            )
            box(self.scene,f"route_entry_stop_{i}",[.064,.006,.035],
                [x,.244,self.params["track_height"]+.035],static=True,restitution=.05)
            box(
                self.scene,
                f"rebound_{i}",
                [0.055, 0.065, 0.008],
                [x, -.165, self.params["rebound_height"]],
                q=quat_xyz([.35, 0, 0]),  # v5: tilt about x; rebound heads -y into open space
                static=True,
                restitution=0.90,
            )
        self.fixtures["cart"] = single_axis(
            self.scene,
            "cart",
            [-.25, -.33, .08],
            speed=self.params["fixture_speed"],
            force=8.0,
            slider_axis="x",
        )
        self.fixtures["cart"].motion="oscillate"

    def reset_task(self):
        route = int(self.rng.integers(2))
        y = float(self.rng.uniform(-.34, -.30))
        self.events.flags.update(
            route_index=route,
            goal=[(-.12,.08)[route],.23,self.params["track_height"]],
            target=[-.10, y, .23],
        )
        t = self.params["preview"]
        v = self.params["incoming_speed"]
        set_initial(
            self.objects["ball"],
            [-.10 + v * t, y, .38],
            [-v, 0, (0.23 + self.params["tool_height"] + self.params["radius"] - 0.38 + 4.905 * t * t) / t],
        )
        self.fixtures["cart"].reset(
            self.rng.uniform(-0.05, 0), self.params["fixture_speed"]
        )
        self.events.emit("release", 0.0, object="ball")

    def update_task(self):
        f = self.events.flags
        route = f["route_index"]
        p = position(self.objects["ball"])
        if self.phase == 0 and cup_catch(self, "ball", "panda-0", "first"):
            self.advance(object="ball")
        elif self.phase == 1:
            if self.contact("ball", f"route_{1 - route}"):
                self.events.fail("wrong_route", self.time)
            if (
                self.contact("ball", f"route_{route}")
                and p[1] > .10
                and not self.contact("ball", "tool")
            ):
                self.advance(
                    entry_speed=float(np.linalg.norm(velocity(self.objects["ball"])))
                )
        elif self.phase == 2:
            if self.contact("ball", "table"):
                self.events.fail("missed_gravity_route", self.time)
            if self.contact("ball", "tool"):
                self.events.fail("caught_before_required_rebound", self.time)
            if self.contact("ball", f"rebound_{route}") and p[1] < -.12 and p[2] > self.params["rebound_height"]-.005:
                self.advance(impulse=self.contact("ball", f"rebound_{route}"))
        elif self.phase == 3 and cup_catch(self, "ball", "panda-0", "second"):
            self.advance(object="ball")
        elif self.phase == 4:
            cart = self.fixtures["cart"]
            retained = containment(
                self, "ball", cart.link, 0.075, 0.06, self.params["radius"]
            )
            if self.phase_hold(
                retained
                and not self.contact("ball", "tool")
                and abs(cart.v) > 0.5 * self.params["fixture_speed"],
                0.7,
            ):
                self.events.physical_success = True
