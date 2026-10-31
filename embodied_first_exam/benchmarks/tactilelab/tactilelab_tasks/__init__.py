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
_rigid("one_leg", "Pick up the table leg standing on the table, push its stud down into one corner bore of the table top (turning it is allowed, not required) and let go of it.")
_rigid("square_table", "Pick up the four table legs one after the other, push each stud down into its corner bore of the table top (turning a leg is allowed, not required) and let go.")
_rigid("lamp_bulb", "Pick up the light bulb, put it down into the socket of the lamp base (turning it is allowed, not required), then put the lampshade (hood) over it onto the base, and let go.")
_rigid("gear_mesh", "Pick up the medium gear lying flat on the table, slide it down onto the middle post of the gear base so that it meshes with the small and the large gear already on their posts, and let go.")
_rigid("nut_thread", "The M16 nut already sits engaged on the top of the fixed bolt: grasp it, turn it down the thread and let go of it.")


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
_cable("cable_needle_thread", "Take the cable out of its two open clips and push its tip through the square hole of the wall in front of it.")
_cable("cable_slack_reduce", "A cable's head is clamped under a bar; its free part bulges to the side and its tail rests on a notched ridge. Pinch the cable between the gel pads and pull it straight, without letting it slip.")
_cable("cable_route_channel", "Starting from its clamped end, press the cable segment by segment down into the shallow slot between two rails, then let go and leave it at rest.")


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
    "With the bare gel pads, squeeze the upright dough bar thin at its two outer slots while its middle stays thick, then lift the hand clear.",
)
_dough(
    "dough_press_thickness",
    "DoughPressThicknessTask",
    "DoughPressThicknessPolicy",
    "With the bare gel pads, squeeze the dough ridge to the target thickness at two places along it, then lift the hand clear.",
)
_dough(
    "dough_fill_tray",
    "DoughFillTrayTask",
    "DoughFillTrayPolicy",
    "Take the scraper out of its rack, spread the dough heap over the whole tray floor evenly, then lift the scraper clear.",
)
_dough(
    "fem_plug_insert",
    "FemPlugInsertTask",
    "FemPlugInsertPolicy",
    "Pinch the compliant rubber plug between the gel pads, lift it out of its loose pick socket, carry it to the press-fit hole, push it in until it is seated, release it and withdraw.",
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


_task("drawer_container", "Pick up the two storage containers and slide them horizontally into the drawer box, the first one onto the lower rail pair and the second onto the upper one, each pushed in to its back stop.")
_task("insert_tube", "Pull the test tube up out of its rack, insert it into the 30°-inclined bore of the tube slot, let go and move the hand away.")
_task("insert_hdmi", "Pick up the HDMI plug standing on the table, insert it into the port, let go and move the hand away.")
_task("lift", "Grasp the bottle lying in its cradle, set it down on the green pad at the height it has when standing there (turning it upright in the air is the way to get it there) and open the gripper.")
_task("handover", "The right gripper holds a rod; pass it into the open left gripper, close the left gripper on it, then open the right gripper and move it away, leaving the rod held in the air by the left hand.")


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
    "A cloth lies on a shelf with its edge overhanging. Pinch the edge between the gel pads and slide the pinch along the edge to its corner on the robot's left without dragging the cloth.",
)
_soft(
    "cloth_fold_half",
    "ClothFoldHalfTask",
    "ClothFoldHalfPolicy",
    "A cloth lies on a pedestal with its free half overhanging. Pinch the free edge, roll it over the fold line onto the pinned half, release it and let it rest.",
)
_soft(
    "sleeve_pull_on_forearm",
    "SleevePullOnForearmTask",
    "SleevePullOnForearmPolicy",
    "A sleeve is already on the left forearm. Pinch its pull tab with the right gripper, pull the sleeve along the forearm until its cuff reaches the target band, release it and let it rest.",
)
