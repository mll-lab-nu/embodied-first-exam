"""Execute the rope-only removal route, or its short development prefix.

The fixed fixture keeps the approved 75% scale. The 1.1 m working cord is an
explicit planning variant; this does not change the robot scene's default.
"""
import argparse
import json
from pathlib import Path

from .dynamics import Probe, natural_working_state
from .geometry import OrbitsLayout


def run_prefix(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=False)
    points, handle = natural_working_state(
        OrbitsLayout().scaled(.75), handle_x_m=.45, cord_length_m=1.1,
        spacing=.0075)
    probe = Probe(folder / "model.xml", spacing=.0075, initial_points=points,
                  handle_position=handle, checkpoint_each_phase=True,
                  max_penetration_m=.0015, max_grasp_error_m=.015)
    midpoint = len(points) // 2
    probe.data.eq_active[probe.model.equality("grasp_handle").id] = False
    scope = dict(
        scope="rope_only_reference_prefix", full_solution=False, robot_present=False,
        source="https://www.youtube.com/watch?v=B-EB9Q-JqXA",
        fixture_scale=.75, working_cord_length_m=1.1, spacing_m=.0075,
        initial_handle_x_m=.45, controller="prescribed material-point position constraints",
        gravity=True, fixture_collision=True, cord_self_collision=True,
        terminal_attachments="both original closed handle eyes remain connected",
        validation="first reference group only; final removal has not been achieved",
        completed=False)
    (folder / "scope.json").write_text(json.dumps(scope, indent=2) + "\n")
    try:
        for name, point in [
            ("settle", None), ("up_R4", [.1, 0., .15]),
            ("lift_bight_high", [.08, 0., .34]),
        ]:
            probe.move(name, bight=point, seconds=2.)
        probe.grasp_nodes([midpoint - 12, midpoint + 12])
        for name, point in [
            ("spread_initial", [.08, 0., .39]),
            ("over_ball", [-.18, 0., .39]),
            ("outside_R1", [-.19, 0., .27]),
        ]:
            probe.move(name, bight=point, span=.06, seconds=2.)
        probe.grasp_node(midpoint - 12)
        for name, point in [
            ("P_below1", [-.145, 0., .218]),
            ("P_up1", [-.145, 0., .335]),
            ("P_overball", [-.095, 0., .335]),
            ("P_down1", [-.095, 0., .218]),
        ]:
            probe.move(name, bight=point, seconds=2.)
        probe.grasp_node(midpoint)
        for name, point in [
            ("under_R2", [-.08, 0., .17]),
            ("Q_up_overlap", [-.08, 0., .335]),
            ("Q_overball_left", [-.15, 0., .335]),
            ("Q_down1_left", [-.145, 0., .218]),
            ("Q_outside1_left", [-.19, 0., .218]),
            ("Q_lift_outside", [-.19, 0., .42]),
            ("Q_cap_overright", [-.025, 0., .42]),
            ("Q_down_R2", [-.025, 0., .17]),
            ("tension_handle_free", None),
        ]:
            probe.move(name, bight=point, seconds=2.)
        scope["completed"] = True
    finally:
        probe.save(folder)
        scope["completed_simulation_time_s"] = float(probe.data.time)
        (folder / "scope.json").write_text(json.dumps(scope, indent=2) + "\n")
    return probe


def run(folder, *, prefix=False):
    if prefix:
        return run_prefix(folder)
    from .rope_audit import audit
    from .rope_route import execute

    route = Path(__file__).resolve().parents[3] / "configs/task_variants/orbits/rope_solution_v1.json"
    probe = execute(route, folder)
    report = audit(folder)
    scope_path = Path(folder) / "scope.json"
    scope = json.loads(scope_path.read_text())
    scope["full_solution"] = bool(report["removal_certificate"]["passed"])
    scope["full_solution_scope"] = "rope-only prescribed fixtures; no robot qualification"
    scope_path.write_text(json.dumps(scope, indent=2) + "\n")
    if not scope["full_solution"]:
        raise RuntimeError("Route ended without complete cord and handle separation")
    return probe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--prefix", action="store_true", help="Only the 38 s development prefix")
    args = parser.parse_args()
    run(args.folder, prefix=args.prefix)
