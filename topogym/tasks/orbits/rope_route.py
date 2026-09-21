"""Execute a recorded material-point route in a fresh rope-only simulation.

Route completion is separate from puzzle removal. Guards remain active during
the fresh execution, and newly acquired material points use measured positions.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import mujoco
import numpy as np
from scipy.spatial.transform import Rotation

from .dynamics import Probe, natural_working_state
from .geometry import OrbitsLayout


def execute(route_path, folder):
    route_path, folder = Path(route_path), Path(folder)
    route = json.loads(route_path.read_text())
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copy2(route_path, folder / "route.json")
    cfg = route["model"]
    points, handle = natural_working_state(
        OrbitsLayout().scaled(.75), handle_x_m=cfg["initial_handle_x_m"],
        cord_length_m=cfg["cord_length_m"], spacing=cfg["spacing_m"])
    probe = Probe(folder / "model.xml", initial_points=points, handle_position=handle,
                  spacing=cfg["spacing_m"], checkpoint_each_phase=True,
                  max_penetration_m=.0015, max_grasp_error_m=.015)
    digest = hashlib.sha256((folder / "model.xml").read_bytes()).hexdigest()
    if digest != route["model_sha256"]:
        raise ValueError("Route model hash does not match the generated model")
    keys = ("bight", "handle", "fold_0", "fold_1")
    ids = [probe.model.equality("grasp_" + key).id for key in keys]
    mocaps = [probe.bight_id, probe.handle_id, *probe.fold_ids]
    handle_body = probe.model.body("handle").id
    status = dict(scope="fresh_rope_only_route_execution", robot_present=False,
                  requested_route_scope=route["scope"], route_completed=False,
                  full_solution=False, physical_state_restores=0,
                  control_mode=route.get("control_mode", "measured_point_reacquisition"),
                  cold_solver_starts=sum(bool(a.get("cold_start_solver")) for a in route["actions"]),
                  source_route_sha256=hashlib.sha256(route_path.read_bytes()).hexdigest())
    (folder / "scope.json").write_text(json.dumps(status, indent=2) + "\n")
    try:
        for index, action in enumerate(route["actions"]):
            # Contact warm-starts affect a flexible cord's later drape. A route
            # may explicitly request a cold solver start at a phase boundary;
            # positions, velocities and simulation time are never restored.
            if action.get("cold_start_solver", False):
                probe.data.qacc_warmstart[:] = 0.
                probe.data.xfrc_applied[:] = 0.
                probe.data.qfrc_applied[:] = 0.
                mujoco.mj_forward(probe.model, probe.data)
                probe.events.append(dict(event="cold_start_contact_solver",
                                         time_s=float(probe.data.time),
                                         physical_state_restored=False))
            active = np.asarray(action["active_equalities"], dtype=bool)
            sites = np.asarray(action["target_site_ids"], dtype=int)
            if active.shape != probe.data.eq_active.shape or sites.shape != probe.model.eq_obj2id.shape:
                raise ValueError("Route equality bindings do not match model")
            for equality, mocap in zip(ids, mocaps):
                newly_acquired = active[equality] and (
                    not probe.data.eq_active[equality] or sites[equality] != probe.model.eq_obj2id[equality])
                if newly_acquired:
                    probe.data.mocap_pos[mocap] = probe.data.site_xpos[sites[equality]]
            if route.get("control_mode") == "recorded_fixture_commands":
                # These are actuator commands, never measured qpos/qvel.
                # Reacquisition error remains subject to the integration guard.
                start = np.asarray(action["start_mocap_positions_m"], dtype=float)
                if start.shape != probe.data.mocap_pos.shape or not np.isfinite(start).all():
                    raise ValueError("Invalid recorded fixture positions")
                probe.data.mocap_pos[:] = start
            probe.data.eq_active[:] = active
            probe.model.eq_obj2id[:] = sites
            target = np.asarray(action["target_mocap_positions_m"])
            orientation = action.get("handle_orientation_matrix")
            callback = None
            probe.data.xfrc_applied[handle_body] = 0.
            if orientation is not None:
                desired = np.asarray(orientation)
                if desired.shape != (3, 3) or not np.allclose(desired.T @ desired, np.eye(3), atol=1e-8):
                    raise ValueError("Invalid handle orientation target")

                def callback(model, data):
                    error = Rotation.from_matrix(desired @ data.xmat[handle_body].reshape(3, 3).T).as_rotvec()
                    data.xfrc_applied[handle_body, 3:] = .01 * error - .00015 * data.cvel[handle_body, :3]

            probe.events.append(dict(event="route_action", index=index,
                                     source_phase=action["phase"], time_s=float(probe.data.time),
                                     handle_orientation_matrix=orientation))
            probe.move(f"{index:03d}_{action['phase']}", seconds=action["duration_s"],
                       anchors={"bight": target[probe.bight_id], "handle": target[probe.handle_id],
                                0: target[probe.fold_ids[0]], 1: target[probe.fold_ids[1]]},
                       step_callback=callback)
        status["route_completed"] = True
    finally:
        probe.save(folder)
        status["simulation_time_s"] = float(probe.data.time)
        status["mujoco_warning_counts"] = probe.data.warning.number.tolist()
        (folder / "scope.json").write_text(json.dumps(status, indent=2) + "\n")
    return probe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("route", type=Path)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    execute(args.route, args.folder)
