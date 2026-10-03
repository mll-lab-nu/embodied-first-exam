"""Read-only inventory. Runner presence never implies a solved/qualified oracle."""
from pathlib import Path
import re
import tomllib

from .contracts import BridgeError, instance_binding, read_json

# Task-specific data only. Execution and packaging contain no family dispatch.
RUNNERS = {
    "cube_pick_place": (),
    "cast_keyhole": ("run_cast_keyhole_policy.py",),
    "cast_coil": ("run_cast_coil_policy.py",),
    "lock_picking": ("run_lock_picking_policy.py",),
    "fiber_bundling": ("run_fiber_bundling_policy.py", "run_solvability_workflow.py"),
    "buzz_wire_3d": ("run_buzz_wire_policy.py", "run_buzz_wire_simplified_policy.py"),
    "hedgehog_in_cage": ("run_hedgehog_oracle.py",),
    "interlocked_claws": ("run_claws_oracle.py", "run_interlocked_claws_simplified_policy.py"),
    "horseshoe_ring": ("run_horseshoe_oracle.py",),
    "knot_untying": ("run_knot_oracle.py", "run_knot_branching.py"),
    "blanket_flatten": ("run_blanket_oracle.py",),
    "rope_threading": ("run_rope_threading_relay.py", "run_rope_threading_policy.py"),
    "slotted_post_ring": (),
    "orbits": (),
}

TIERS = ("very_easy", "easier", "easy", "medium", "hard")


def task_difficulty(task, metadata):
    """Read the exact frozen task slug; 'very-easy' must never match 'easy'."""
    family = metadata.get("family", "").replace("_", "-")
    match = re.fullmatch(r"topogym-" + re.escape(family)
        + r"-(very-easy|easier|easy|medium|hard)-i[0-9]+-(privileged|standard)", Path(task).name)
    return match.group(1).replace("-", "_") if match else None


def inventory(root, tasks_root=None, *, tiers=None):
    root = Path(root)
    tasks_root = Path(tasks_root or root / "tasks")
    if tiers is not None and (not tiers or set(tiers) - set(TIERS)):
        raise BridgeError("Select known difficulty tiers")
    rows = []
    for path in sorted(tasks_root.glob("*/task.toml")):
        task = path.parent
        meta = tomllib.loads(path.read_text()).get("metadata", {})
        family = meta.get("family")
        if family not in RUNNERS:
            continue
        difficulty = task_difficulty(task, meta)
        if tiers is not None and difficulty not in tiers:
            continue
        mode = "standard" if (task / "environment/sim/instance.json").is_file() else "privileged"
        instance_path = task / ("environment/sim/instance.json" if mode == "standard" else "environment/instance.json")
        instance = read_json(instance_path)
        config = instance["simulator"]
        solve = task / "solution/solve.sh"
        script = solve.read_text() if solve.is_file() else ""
        existing = mode == "privileged" and "run-oracle" in script and "--code" in script
        bridge = task / "solution/bridge_manifest.json"
        blockers = []
        try:
            instance_binding(instance_path)
        except (BridgeError, OSError, ValueError, KeyError) as error:
            blockers.append(str(error))
        rows.append(dict(task=str(task), family=family, mode=mode, difficulty=difficulty,
            variation=instance.get("resolved_variation_id", instance.get("variation_id")),
            seed=config.get("seed"), declared_oracle=meta.get("oracle", "legacy_unspecified"),
            bridge="blocked_identity" if blockers else "candidate" if bridge.is_file() else "existing_script_packable" if existing else "requires_bound_reference",
            blockers=blockers,
            has_solution=solve.is_file(), runners=[str(Path("scripts/oracle_runners") / name) for name in RUNNERS[family]],
            profile={k: config.get(k) for k in ("compute_backend", "precision", "physics_dt_s", "control_decimation",
                                                "solver_substeps", "grasp_assist")},
            success_rule=instance.get("success_rule")))
    return dict(schema_version=1, scope="source inventory only; no physical qualification inferred", tasks=rows,
                selected_tiers=list(tiers) if tiers is not None else None,
                task_count=len(rows), families_without_robot_runner=[k for k, v in RUNNERS.items() if not v and k != "cube_pick_place"])
