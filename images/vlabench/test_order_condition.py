#!/usr/bin/env python3
"""Offline regression test of the image's OrderCondition fix (images/vlabench/Dockerfile, the `RUN f=.../condition.py`
step): VLABench @ cf588fe bounds the offset of neighbouring entities in the axes it does not sort on one side only
(`(a - b) < offset`), so the next entity may be any distance further or higher; the image's sed makes it `abs(a - b)`.

The test runs that RUN step, as the Dockerfile has it, on a copy of upstream's condition.py (the OrderCondition source of
cf588fe below, or the file given with --upstream), then runs the patched OrderCondition.is_met on synthetic entity
points (stub physics, no MuJoCo, no VLABench). Standard library only.

    python3 images/vlabench/test_order_condition.py [--dockerfile F] [--upstream VLABench/VLABench/tasks/condition.py]
    python3 images/vlabench/test_order_condition.py --no-patch      # upstream as it is: fails (the bug)
"""
from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = "/opt/VLABench/VLABench/tasks/condition.py"

# OpenMOSS/VLABench @ cf588fe60c0c7282174fe979f5913170cfe69017, VLABench/tasks/condition.py lines 1-42 (MIT)
UPSTREAM = '''import numpy as np
from VLABench.utils.register import register
from VLABench.utils.utils import distance
from VLABench.tasks.components.entity import Entity

class Condition:
    def __init__(self):
        pass

    def is_met(self, physics=None):
        raise NotImplementedError()

    def met_progress(self, physics=None):
        return self.is_met(physics)

@register.add_condition("order")
class OrderCondition(Condition):
    """
    check the position order of the given entities.
    params:
        entities: the given entities should in the expected order.
        axis: the  axis to check the order.
        offset: the acceptable offset between the entities in other axis.
    """
    def __init__(self, entities, axis=[0], offset=0.1):
        self.entities = entities
        self.axis = axis
        self.offset = offset

    def is_met(self, physics):
        if isinstance(self.entities[-1], Entity):
            self.entities_mjcf = [entity.mjcf_model.worldbody for entity in self.entities]
        entity_points = [physics.bind(entity_mjcf).xpos for entity_mjcf in self.entities_mjcf]
        for axis in [0, 1, 2]: # x y z
            if axis in self.axis:
                if not all([entity_points[i][axis] < entity_points[i+1][axis] for i in range(len(entity_points)-1)]):
                    return False
            else:
                if not all([(entity_points[i][axis] - entity_points[i+1][axis]) < self.offset for i in range(len(entity_points)-1)]):
                    return False
        return True
'''


def run_step(dockerfile: Path, path: Path) -> None:
    """Run the Dockerfile's RUN step that patches condition.py on `path` (fails if there is no such step)."""
    text = dockerfile.read_text(encoding="utf-8").replace("\\\n", " ")
    steps = [ln[4:] for ln in text.splitlines() if ln.startswith("RUN ") and TARGET in ln]
    assert len(steps) == 1, f"{dockerfile}: {len(steps)} RUN steps patch {TARGET}, not one"
    subprocess.run(["bash", "-ec", steps[0].replace(TARGET, str(path))], check=True)


def order_condition(path: Path):
    """The OrderCondition class of the (patched) file, with the module's imports stubbed."""
    src = path.read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OrderCondition")
    cls.decorator_list = []

    class Entity:
        def __init__(self, name):
            self.mjcf_model = type("M", (), {"worldbody": name})()

    ns = {"Condition": object, "Entity": Entity}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(path), "exec"), ns)
    return ns["OrderCondition"], Entity


class Physics:
    def __init__(self, points):
        self.points = points

    def bind(self, name):
        return type("B", (), {"xpos": self.points[name]})()


def is_met(cond_cls, entity_cls, points, **kw) -> bool:
    names = list(points)
    return cond_cls([entity_cls(n) for n in names], **kw).is_met(Physics(points))


# (case, entity points left to right, expected verdict of the fixed, two-sided check)
CASES = [
    ("in a row", {"a": (-0.15, 0.30, 1.25), "b": (0.0, 0.30, 1.25), "c": (0.15, 0.30, 1.25)}, True),
    ("small offsets either way", {"a": (-0.15, 0.30, 1.25), "b": (0.0, 0.36, 1.21), "c": (0.15, 0.27, 1.28)}, True),
    ("out of order along x", {"a": (0.0, 0.30, 1.25), "b": (-0.15, 0.30, 1.25), "c": (0.15, 0.30, 1.25)}, False),
    ("next one much nearer (y)", {"a": (-0.15, 0.30, 1.25), "b": (0.0, 0.10, 1.25), "c": (0.15, 0.10, 1.25)}, False),
    ("next one much further (y)", {"a": (-0.15, 0.30, 1.25), "b": (0.0, 0.60, 1.25), "c": (0.15, 0.60, 1.25)}, False),
    ("next one much higher (z)", {"a": (-0.15, 0.30, 1.05), "b": (0.0, 0.30, 1.05), "c": (0.15, 0.30, 1.40)}, False),
    ("next one much lower (z)", {"a": (-0.15, 0.30, 1.40), "b": (0.0, 0.30, 1.40), "c": (0.15, 0.30, 1.05)}, False),
]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dockerfile", type=Path, default=HERE / "Dockerfile")
    ap.add_argument("--upstream", type=Path, help="upstream VLABench/tasks/condition.py (default: the copy above)")
    ap.add_argument("--no-patch", action="store_true", help="test upstream's code as it is (the test then fails)")
    a = ap.parse_args(argv)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "condition.py"
        path.write_text(a.upstream.read_text(encoding="utf-8") if a.upstream else UPSTREAM, encoding="utf-8")
        if not a.no_patch:
            run_step(a.dockerfile, path)
        cond, ent = order_condition(path)
    bad = []
    for name, pts, want in CASES:
        got = is_met(cond, ent, pts)
        if got != want:
            bad.append(f"{name}: is_met {got}, want {want}")
    for b in bad:
        print("FAIL", b)
    if bad:
        return 1
    print(f"ok test_order_condition: {len(CASES)} cases")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
