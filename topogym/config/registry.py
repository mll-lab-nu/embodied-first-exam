"""One task catalog: every task has a definition and explicit operation-level gaps."""

from __future__ import annotations
from dataclasses import dataclass, asdict
from importlib import import_module


@dataclass(frozen=True)
class SupportGap:
    module: str
    feature: str
    blocks: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class TaskRegistration:
    task_id: str
    implementation: str
    physics_model: str
    default_robot: str = "aloha"
    gaps: tuple[SupportGap, ...] = ()
    status: str = "integrated"
    validation: str = "see_runs_test_results"


class TaskSupportError(NotImplementedError):
    def __init__(self, task_id, operation, gaps):
        self.task_id, self.operation, self.gaps = task_id, operation, tuple(gaps)
        super().__init__(
            f"{task_id}: {operation} unavailable; "
            + "; ".join(f"{g.module}::{g.feature}: {g.reason}" for g in gaps)
        )


_ATTACH = SupportGap(
    "topogym/world/genesis_world.py",
    "soft_attachment",
    ("assist_grasp",),
    "PBD/FEM selectable grasp bands, moving targets and their reversible state are not integrated",
)


def _goal_gap(task, detail):
    return SupportGap(f"topogym/tasks/{task}/common.py", "evaluate_state", ("solve",), detail)


_RIGID_ATTACH = SupportGap(
    "topogym/world/genesis_world.py",
    "rigid_attachment_creation",
    ("assist_grasp",),
    "contact_weld_v1 is available through explicit owner grasp_assist configuration; this task/setting has no default qualified grasp regions or production grasp acceptance",
)


def _registration(name, cls, physics, robot="aloha", gaps=()):
    from .variation_records import RECORDS
    if physics in {"rigid", "rigid_articulated"}:
        gaps = (_RIGID_ATTACH,) + tuple(gaps)
    implementation = next(row["implementation"] for row in RECORDS
                          if row["task_id"] == name and "base" in row["aliases"])
    return TaskRegistration(name, implementation, physics, robot, gaps)


_TASKS = {
    item.task_id: item
    for item in (
        _registration("cast_coil", "CastCoilTask", "rigid"),
        _registration("cast_keyhole", "CastKeyholeTask", "rigid"),
        _registration(
            "blanket_flatten", "BlanketFlattenTask", "pbd_cloth", gaps=(_ATTACH,)
        ),
        _registration("horseshoe_ring", "HorseshoeRingTask", "rigid", gaps=(_goal_gap("horseshoe_ring", "Placement-region rules implemented; real placement and reachability qualification pending"),)),
        _registration(
            "hedgehog_in_cage", "HedgehogInCageTask", "rigid", "panda_robotiq",
            gaps=(_goal_gap("hedgehog_in_cage", "Placement-region rules implemented; real placement and reachability qualification pending"),)
        ),
        _registration("interlocked_claws", "InterlockedClawsTask", "rigid", gaps=(_goal_gap("interlocked_claws", "Placement-region rules implemented; real placement and reachability qualification pending"),)),
        _registration(
            "buzz_wire_3d",
            "BuzzWireTask",
            "rigid",
            "panda_robotiq",
        ),
        _registration(
            "lock_picking",
            "LockPickingTask",
            "rigid_articulated",
            "panda_robotiq",
            (
                _goal_gap(
                    "lock_picking",
                    "Insertion and rotor guards implemented; physical pin-slot torque qualification pending",
                ),
            ),
        ),
        _registration(
            "fiber_bundling",
            "FiberBundlingTask",
            "rigid_articulated",
            "panda_robotiq",
        ),
        _registration(
            "rope_threading",
            "RopeThreadingTask",
            "fem_ipc",
            gaps=(
                _ATTACH,
                _goal_gap(
                    "rope_threading",
                    "Material-ordered passage implemented; physical threading and settling qualification pending",
                ),
            ),
        ),
        _registration(
            "knot_untying",
            "KnotUntyingTask",
            "fem_ipc",
            gaps=(
                _ATTACH,
                _goal_gap(
                    "knot_untying",
                    "Table-supported planar crossing rule implemented; physical untying and threshold calibration pending",
                ),
            ),
        ),
        _registration(
            "orbits",
            "OrbitsTask",
            "fem_ipc",
            gaps=(
                _ATTACH,
                _goal_gap(
                    "orbits",
                    "Whole-target placement-region rule implemented; physical reachability and placement qualification pending",
                ),
            ),
        ),
        _registration(
            "slotted_post_ring",
            "SlottedPostRingTask",
            "fem_ipc",
            gaps=(
                _ATTACH,
                _goal_gap(
                    "slotted_post_ring",
                    "Whole-ring placement-region rule implemented; physical reachability and placement qualification pending",
                ),
            ),
        ),
    )
}


def task_catalog():
    return tuple(asdict(item) for item in _TASKS.values())


def task_registration(task_id):
    try:
        return _TASKS[task_id]
    except KeyError as exc:
        raise ValueError(f"Unknown task_id: {task_id!r}") from exc


def task_definition(task_id, variation_id="base", seed=None):
    record = variation_registration(task_id, variation_id, seed)
    if record["status"] != "integrated":
        raise TaskSupportError(task_id, "build", variation_gaps(task_id, variation_id, seed))
    module, name = record["implementation"].split(":")
    return getattr(import_module(module), name)


def require_task_support(task_id, operation, variation_id="base", seed=None):
    gaps = tuple(g for g in (*task_registration(task_id).gaps,
                            *variation_gaps(task_id, variation_id, seed)) if operation in g.blocks)
    if gaps:
        raise TaskSupportError(task_id, operation, gaps)


def variation_catalog(task_id):
    """All canonical settings, including explicit placeholders, without imports."""
    from copy import deepcopy
    from .variation_records import RECORDS
    task_registration(task_id)
    return tuple(deepcopy(row) for row in RECORDS if row["task_id"] == task_id)


def variation_registration(task_id, variation_id="base", seed=None):
    if variation_id == SEEDED_VARIATION:
        if seed is None:
            raise ValueError(f"{task_id}: variation 'seeded' needs a seed to choose its tier")
        return seeded_variation(task_id, seed)
    for row in variation_catalog(task_id):
        if variation_id == row["variation_id"] or variation_id in row["aliases"]:
            return row
    raise ValueError(f"{task_id}: variation {variation_id!r} has no migrated runtime parameter contract")


TIER_ORDER = ("easy", "medium", "hard")
SEEDED_VARIATION = "seeded"


def seeded_variation(task_id, seed):
    """The tier record chosen by ``seed % 3`` for ``variation_id="seeded"``."""
    from topogym.utils.variant_rng import VariantRng
    tiers = sorted((row for row in variation_catalog(task_id) if row["pool"] == "tier"),
                   key=lambda row: TIER_ORDER.index(row["difficulty"]))
    if [row["difficulty"] for row in tiers] != list(TIER_ORDER):
        raise ValueError(f"{task_id}: seeded variation needs exactly one easy, medium and hard tier")
    return tiers[VariantRng(seed).tier(len(tiers))]


def available_variations(task_id):
    """Selectable names only; unavailable slots appear in variation_catalog."""
    names = set()
    for row in variation_catalog(task_id):
        if row["status"] == "integrated":
            names.update((row["variation_id"], *row["aliases"]))
    return tuple(sorted(names, key=lambda name: (name != "base", name)))


def variation_gaps(task_id, variation_id="base", seed=None):
    row = variation_registration(task_id, variation_id, seed)
    if row["status"] == "integrated":
        return ()
    module = row["implementation"].split(":")[0].replace(".", "/") + ".py"
    return (SupportGap(module, "variation_initialization", ("build", "reset", "solve"), row["reason"]),)


def resolve_variation(task_id, variation_id, overrides, seed):
    """Compatibility parameter API; scene selection uses task_definition too."""
    from topogym.tasks.base import merge_parameters
    row = variation_registration(task_id, variation_id)
    if row["status"] != "integrated":
        raise TaskSupportError(task_id, "build", variation_gaps(task_id, variation_id))
    cls = task_definition(task_id, variation_id)
    return merge_parameters(getattr(cls, "variant_parameters", {}), overrides)
