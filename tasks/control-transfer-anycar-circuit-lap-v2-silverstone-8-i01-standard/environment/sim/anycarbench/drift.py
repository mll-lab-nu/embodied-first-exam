"""Public RC drift-parking scene and physical rear-wheel brake extension."""

from collections import deque
import math
import xml.etree.ElementTree as ET
import numpy as np
from .model import Vehicle, NOMINAL, xml_model, traffic_cone

DEFAULT_COURSE = dict(
    radius=1.5, park_x=-3.0, park_y=2.05, slot_length=1.2, slot_width=0.65
)


def route(course):
    r = course["radius"]
    first = np.column_stack([np.linspace(-3, 0, 40), np.full(40, -r)])
    theta = np.linspace(-math.pi / 2, math.pi / 2, 81)
    bend = np.column_stack([r * np.cos(theta), r * np.sin(theta)])
    last = np.column_stack([np.linspace(0, -1.3, 30), np.full(30, r)])
    return np.vstack([first, bend[1:], last[1:]])


def course_xml(course, friction=0.65):
    root = ET.fromstring(xml_model(NOMINAL, [(-12, 12, friction)], dict(a=4.5, b=3.5)))
    world = root.find("worldbody")
    for node in list(world):
        if node.tag == "geom":
            world.remove(node)
    ET.SubElement(
        world,
        "geom",
        name="surface0",
        type="plane",
        size="0 0 .1",
        friction=f"{friction} .005 .0001",
        priority="2",
        rgba=".17 .19 .22 1",
    )
    assets = root.find("asset")
    ET.SubElement(
        assets,
        "texture",
        type="skybox",
        builtin="gradient",
        rgb1=".45 .6 .75",
        rgb2=".9 .92 .94",
        width="512",
        height="512",
    )
    x, y = course["park_x"], course["park_y"]
    # Static full-size collision envelopes; shared RC bodywork above them.
    for i, dx in enumerate(
        (-course["slot_length"] / 2 - 0.25, course["slot_length"] / 2 + 0.25)
    ):
        body = ET.SubElement(
            world,
            "body",
            name=f"parked{i}",
            pos=f"{x + dx} {y} 0",
            euler="0 0 3.141592653589793",
        )
        ET.SubElement(
            body,
            "geom",
            name=f"barrier_parked{i}",
            type="box",
            size=".245 .135 .115",
            pos="0 0 .12",
            rgba="0 0 0 0",
        )
        for mesh, material in [
            ("gt_body", "race_paint"),
            ("gt_cabin", "race_glass"),
            ("gt_roof", "race_paint"),
        ]:
            ET.SubElement(
                body,
                "geom",
                type="mesh",
                mesh=mesh,
                material=material,
                contype="0",
                conaffinity="0",
            )
        for wx in [-0.158, 0.1385]:
            for wy in [-0.115, 0.115]:
                ET.SubElement(
                    body,
                    "geom",
                    type="cylinder",
                    size=".04 .02",
                    pos=f"{wx} {wy} .04",
                    euler="1.5707963267948966 0 0",
                    rgba=".025 .025 .025 1",
                    contype="0",
                    conaffinity="0",
                )
    curb_y = y + course["slot_width"] / 2 + 0.08
    ET.SubElement(
        world,
        "geom",
        name="barrier_curb",
        type="box",
        pos=f"{x} {curb_y} .07",
        size="2 .06 .07",
        rgba=".65 .65 .62 1",
    )
    for side in [-1, 1]:
        ET.SubElement(
            world,
            "geom",
            type="box",
            pos=f"{x + side * course['slot_length'] / 2} {y} .003",
            size=f".012 {course['slot_width'] / 2} .003",
            rgba=".9 .85 .3 1",
            contype="0",
            conaffinity="0",
        )
    points = route(course)
    # Cone-lined approach and U-bend; the parking entry stays open.
    for i in range(4, 115, 10):
        tangent = points[i + 1] - points[i - 1]
        tangent /= np.linalg.norm(tangent)
        normal = np.array([-tangent[1], tangent[0]])
        for side in (-1, 1):
            cx, cy = points[i] + side * 0.8 * normal
            ET.SubElement(
                world,
                "geom",
                name=f"barrier_cone_{i}_{side}",
                type="cylinder",
                size=".035 .13",
                pos=f"{cx} {cy} .13",
                rgba="0 0 0 0",
            )
            for geom in ET.fromstring("<group>" + traffic_cone(cx, cy) + "</group>"):
                world.append(geom)
    for i in range(0, len(points) - 1, 3):
        a, b = points[i], points[min(i + 1, len(points) - 1)]
        ET.SubElement(
            world,
            "geom",
            type="capsule",
            fromto=f"{a[0]} {a[1]} .006 {b[0]} {b[1]} .006",
            size=".012",
            rgba=".82 .86 .83 1",
            contype="0",
            conaffinity="0",
        )
    root.find("visual/global").set("offwidth", "960")
    root.find("visual/global").set("offheight", "540")
    return ET.tostring(root, encoding="unicode")


class DriftVehicle(Vehicle):
    def __init__(self, course=None, plant=None, friction=0.65, brake_torque=3.0):
        course = dict(DEFAULT_COURSE if course is None else course)
        super().__init__(
            plant or NOMINAL,
            [(0, 1, friction)],
            course,
            model_xml=course_xml(course, friction),
        )
        self.brake_torque = brake_torque
        self.rear_dofs = [self.model.joint(n + "_spin").dofadr[0] for n in ("bl", "br")]
        self.brake_queue = deque([0.0] * self.plant["delay_steps"])

    def reset(self, x, y, yaw):
        self.model.dof_frictionloss[self.rear_dofs] = 0.001
        super().reset(x, y, yaw)
        self.brake_queue = deque([0.0] * self.plant["delay_steps"])

    def advance(self, action, substep_callback=None):
        self.brake_queue.append(float(np.clip(action[2], 0, 1)))
        # MuJoCo dry joint friction supplies bounded torque opposing rear-wheel spin.
        self.model.dof_frictionloss[self.rear_dofs] = (
            0.001 + self.brake_torque * self.brake_queue.popleft()
        )
        super().advance(action[:2], substep_callback)
