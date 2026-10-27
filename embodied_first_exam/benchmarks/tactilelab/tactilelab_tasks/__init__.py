"""tactilelab_tasks: X-Trainer + GelSight-Mini contact-rich tasks on Isaac Lab.

The package is organised as follows:

* :mod:`tactilelab_tasks.core` - simulator-independent types, math, the ``Task`` and
  ``DemoPolicy`` base classes, the ``Planner`` protocol and the dataset recorder.
* :mod:`tactilelab_tasks.backends` - the Isaac Lab scene, the robot wrapper, Pink IK
  and the optional cuRobo plugin.  These import Isaac Lab lazily so that the core
  package stays importable without a GPU.
* :mod:`tactilelab_tasks.tasks` - one sub-package per task (scene build, success
  predicate, scripted policy).

``TASKS`` maps a task name to a :class:`TaskSpec`. Entries are lazy: importing this
module never imports a simulator; ``TaskSpec.build()`` does (inside a running Isaac
Sim app).
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

__version__ = "0.1.0"

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


@dataclass
class TaskSpec:
    """Registry entry: configuration file plus dotted ``module:Class`` paths.

    ``task`` classes take ``(cfg, obs_mode=...)`` and expose ``build()`` (scene
    construction); ``policy`` classes take ``(cfg, task)``.
    """

    name: str
    cfg_path: str
    task: str
    policy: str
    description: str = ""

    def load_cfg(self) -> Dict[str, Any]:
        import yaml

        with open(self.cfg_path, "r", encoding="utf-8") as fh:
            cfg = yaml.safe_load(fh) or {}
        cfg.setdefault("name", self.name)
        return cfg

    @staticmethod
    def _import(path: str):
        mod, _, cls = path.partition(":")
        return getattr(importlib.import_module(mod), cls)

    @property
    def task_cls(self):
        return self._import(self.task)

    @property
    def policy_cls(self):
        return self._import(self.policy) if self.policy else None

    def task_class(self):
        """Method form of :attr:`task_cls`."""
        return self.task_cls

    def policy_class(self):
        """Method form of :attr:`policy_cls` (None when the task has no scripted policy)."""
        return self.policy_cls

    def build(self, obs_mode: str = "full", **task_kwargs) -> Tuple[Any, Any]:
        """Instantiate ``(task, policy)``; builds the scene (Isaac Sim app must be running)."""
        cfg = self.load_cfg()
        task = self.task_cls(cfg, obs_mode=obs_mode, **task_kwargs)
        if hasattr(task, "build"):
            task.build()
        policy = self.policy_cls(cfg, task)
        return task, policy


#: name -> TaskSpec
TASKS: Dict[str, TaskSpec] = {}


def register(spec: TaskSpec) -> TaskSpec:
    TASKS[spec.name] = spec
    return spec


def _rigid(name: str, description: str) -> TaskSpec:
    return register(
        TaskSpec(
            name=name,
            cfg_path=os.path.join(_PKG_DIR, "tasks", name, "cfg.yaml"),
            task=f"tactilelab_tasks.tasks.{name}.task:Task",
            policy=f"tactilelab_tasks.tasks.{name}.policy:Policy",
            description=description,
        )
    )


# rigid assembly tasks (tactilelab_tasks.rigid)
_rigid("one_leg", "insert and screw one square-table leg into the table top")
_rigid("square_table", "assemble all four legs of the square table")
_rigid("lamp_bulb", "screw the bulb into the lamp base, then seat the hood")
_rigid("gear_mesh", "insert the medium gear onto its post through the meshing neighbours")
_rigid("nut_thread", "thread the M16 nut one full turn down the bolt")


def _cable(name: str, description: str) -> TaskSpec:
    return register(
        TaskSpec(
            name=name,
            cfg_path=os.path.join(_PKG_DIR, "tasks", name, "cfg.yaml"),
            task=f"tactilelab_tasks.tasks.{name}.task:Task",
            policy=f"tactilelab_tasks.tasks.{name}.policy:Policy",
            description=description,
        )
    )


# cable tasks (tactilelab_tasks.soft.cables; Newton sidecar)
_cable("cable_needle_thread", "lift a cable out of its clips and thread its tip through the hole of a wall")
_cable("cable_slack_reduce", "pinch the free end of a slack cable and pull it taut against the clamp")
_cable("cable_route_channel", "press a cable into a shallow slot between two rails, segment by segment")


def _dough(name: str, task_cls: str, policy_cls: str, description: str) -> TaskSpec:
    return register(
        TaskSpec(
            name=name,
            cfg_path=os.path.join(_PKG_DIR, "tasks", name, "cfg.yaml"),
            task=f"tactilelab_tasks.tasks.{name}.task:{task_cls}",
            policy=f"tactilelab_tasks.tasks.{name}.policy:{policy_cls}",
            description=description,
        )
    )


# dough / FEM tasks (tactilelab_tasks.dough; Newton sidecar worlds mpm.dough and fem.plugpad)
_dough(
    "dough_target_shape",
    "DoughTargetShapeTask",
    "DoughTargetShapePolicy",
    "pinch a dough bar at the two target slots with the gel pads; the third slot stays thick",
)
_dough(
    "dough_press_thickness",
    "DoughPressThicknessTask",
    "DoughPressThicknessPolicy",
    "pinch a dough ridge to the target thickness with the gel pads (pinch-walk)",
)
_dough(
    "dough_fill_tray",
    "DoughFillTrayTask",
    "DoughFillTrayPolicy",
    "pick the scraper from its rack and spread the dough heap evenly over the tray",
)
_dough(
    "fem_plug_insert",
    "FemPlugInsertTask",
    "FemPlugInsertPolicy",
    "pinch a compliant plug with the gel pads, carry it and seat it in the press-fit hole",
)


# Bimanual rigid tasks (tactilelab_tasks.tasks.<name>; task.py exposes ``Task``, policy.py ``Policy``)
def _task(name: str, description: str, policy: bool = True) -> TaskSpec:
    return register(
        TaskSpec(
            name=name,
            cfg_path=os.path.join(_PKG_DIR, "tasks", name, "cfg.yaml"),
            task=f"tactilelab_tasks.tasks.{name}.task:Task",
            policy=f"tactilelab_tasks.tasks.{name}.policy:Policy" if policy else "",
            description=description,
        )
    )


_task("drawer_container", "slide two containers into the drawer box and push them home")
_task("insert_tube", "pull the test tube out of its rack and insert it into the inclined slot")
_task("insert_hdmi", "plug the HDMI connector into the vertical port")
_task("lift", "grasp the lying bottle, reorient it upright in the air and place it on the pad")
_task("handover", "bimanual: pass the rod from the right gripper into the left gripper")


def _soft(name: str, task_cls: str, policy_cls: str, description: str) -> TaskSpec:
    return register(
        TaskSpec(
            name=name,
            cfg_path=os.path.join(_PKG_DIR, "tasks", name, "cfg.yaml"),
            task=f"tactilelab_tasks.tasks.{name}.task:{task_cls}",
            policy=f"tactilelab_tasks.tasks.{name}.policy:{policy_cls}",
            description=description,
        )
    )


# cloth / sleeve tasks (tactilelab_tasks.soft; Newton sidecar world softbody.world)
_soft(
    "cloth_edge_feed",
    "ClothEdgeFeedTask",
    "ClothEdgeFeedPolicy",
    "pinch the overhanging cloth edge and feed the gripper along it to the corner",
)
_soft(
    "cloth_fold_half",
    "ClothFoldHalfTask",
    "ClothFoldHalfPolicy",
    "pinch the flap of a cloth on a pedestal and roll it over the fold line onto the pinned half",
)
_soft(
    "sleeve_pull_on_forearm",
    "SleevePullOnForearmTask",
    "SleevePullOnForearmPolicy",
    "pinch the pull tab of a pre-donned sleeve and pull it along the posed left forearm",
)
