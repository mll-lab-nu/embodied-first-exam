"""Audit recorded native execution, independently of the oracle's decisions."""
import gzip
import json
from pathlib import Path


def rows(path):
    path = Path(path)
    if not path.exists():
        path = path.with_suffix(path.suffix + ".gz")
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt") as stream:
        for line in stream:
            yield json.loads(line)


def audit_run(folder):
    """Require one birth-to-success lineage and complete ordinary action coverage.

    This checks reported rigid solver substeps. It does not establish continuous
    geometric clearance, friction-only grasping, or success on other instances.
    Both the default and explicit development control decimations are supported.
    """
    folder = Path(folder)
    report = json.loads((folder / "run_report.json").read_text())
    first = last = previous = None
    count = metal = robot = uncovered = 0
    lineage = True
    traversal = False
    for row in rows(folder / "private/physics_states.jsonl"):
        state, world = row["state"], row["world"]
        count += 1
        if first is None:
            first = row
            lineage &= state["physics_step"] == 0 and state["parent_state_id"] is None
        else:
            lineage &= (state["episode_id"] == first["state"]["episode_id"]
                        and state["physics_step"] == previous["physics_step"] + 1
                        and state["parent_state_id"] == previous["state_id"])
        lineage &= state["branch_id"] == 0
        previous, last = state, row
        contacts = world["contact_events"]
        if state["physics_step"] and not all(contacts.get(k, False) for k in (
                "substeps_complete", "geometry_roles_complete", "robot_geometry_complete")):
            uncovered += 1
        for event in contacts["events"]:
            if event["touching"]:
                roles = {event["role_a"], event["role_b"]}
                metal += roles == {"wand_metal", "wire_metal"}
                robot += roles == {"robot", "wire_metal"}
        traversal |= bool(row["task"]["result"]["metrics"].get("traversal_complete", False))
    controls = ticks = 0
    ordinary = True
    for row in rows(folder / "private/control_steps.jsonl"):
        if row["kind"] == "completed":
            controls += 1
            ticks += row["physics_steps"]
            ordinary &= row["info"]["control_mode"] == "JOINT_ABS"
    result = dict(scope="continuous native execution; reported rigid solver substeps",
        physics_ticks=max(0, count-1), control_actions=controls,
        lineage_from_birth=bool(first and lineage), ordinary_joint_actions=bool(ordinary),
        controls_cover_ticks=bool(last and ticks == count-1 == report["physics_steps"]),
        initial_robot_matches_report=bool(first and first["robot"] == report["initial_robot"]),
        metal_wire_contact_events=metal, robot_wire_contact_events=robot,
        uncovered_ticks=uncovered, traversal_complete_seen=bool(traversal),
        native_task_success=bool(last and last["task"]["result"]["task_success"]),
        final_task=last["task"]["result"] if last else None)
    result["passed"] = bool(report["status"] == "passed" and report["task_success"]
        and all(result[k] for k in ("lineage_from_birth", "ordinary_joint_actions",
            "controls_cover_ticks", "initial_robot_matches_report", "traversal_complete_seen",
            "native_task_success")) and not (metal or robot or uncovered))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    result = audit_run(args.run)
    (args.run / "independent_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "final_task"}))
    raise SystemExit(0 if result["passed"] else 1)
