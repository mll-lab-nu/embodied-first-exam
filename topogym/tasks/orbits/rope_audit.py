"""Audit measured rope-only states and test a conservative removal condition."""
import argparse
import hashlib
import json
from pathlib import Path

import mujoco
import numpy as np

from .geometry import OrbitsLayout
from .verification import threading_signature


def audit(folder):
    folder = Path(folder)
    path = folder / "probe_trajectory.npz"
    with np.load(path) as archive:
        saved = {key: archive[key] for key in archive.files}
    model = mujoco.MjModel.from_xml_path(str(folder / "model.xml"))
    data = mujoco.MjData(model)
    layout = OrbitsLayout().scaled(.75)
    nodes = [model.site(f"node_{i}").id for i in range(saved["points"].shape[1])]
    terminal_sites = [[model.site(f"eye_{i}").id, nodes[j]]
                      for i, j in enumerate([0, -1])]
    max_depth = max_terminal = max_parity = max_length_error = 0.
    finite = bool(np.isfinite(saved["qpos"]).all() and np.isfinite(saved["points"]).all())
    if not finite:
        raise ValueError("Non-finite measured trajectory")
    ring_link_violations = []
    rest_length = model.flexedge_length0.copy()
    for i, qpos in enumerate(saved["qpos"]):
        data.qpos[:] = qpos
        mujoco.mj_forward(model, data)
        points = data.site_xpos[nodes]
        max_parity = max(max_parity, float(np.abs(points - saved["points"][i]).max()))
        for eye, endpoint in terminal_sites:
            max_terminal = max(max_terminal, float(np.linalg.norm(
                data.site_xpos[eye] - data.site_xpos[endpoint])))
        if len(rest_length):
            max_length_error = max(max_length_error, float(np.max(np.abs(
                np.linalg.norm(np.diff(points, axis=0), axis=1) - rest_length))))
        if data.ncon:
            max_depth = max(max_depth, float(max(0., -np.min(data.contact.dist))))
        signature = threading_signature(points, layout)
        if any(signature["ring_linking_numbers"]):
            ring_link_violations.append(dict(frame=i, time_s=float(saved["time_s"][i]),
                                             linking=signature["ring_linking_numbers"]))
    # An entire closed cord and handle strictly beyond the base's right edge
    # are separated from every component of this fixed fixture. This is a
    # sufficient condition; winding numbers alone are not a removal test.
    boundary = layout.base_length_m / 2 + .01
    cord_left = float(saved["points"][-1, :, 0].min() - layout.cord_radius_m)
    handle_radius = np.linalg.norm([layout.handle_length_m, layout.handle_width_m,
                                    layout.handle_height_m]) / 2
    handle_left = float(data.xpos[model.body("handle").id, 0] - handle_radius)
    removed = bool(cord_left > boundary and handle_left > boundary)
    report = dict(
        scope="measured_rope_only_sample_audit_not_robot",
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        sample_count=len(saved["qpos"]), simulation_start_s=float(saved["time_s"][0]),
        simulation_end_s=float(saved["time_s"][-1]), finite=finite,
        max_sampled_contact_depth_m=max_depth, max_terminal_error_m=max_terminal,
        max_recorded_point_error_m=max_parity, max_edge_length_error_m=max_length_error,
        ring_link_violations=ring_link_violations, final_threading=signature,
        removal_certificate=dict(passed=removed, sufficient_test="all cord and handle right of fixture",
                                 boundary_x_m=boundary, cord_left_x_m=cord_left,
                                 handle_left_bound_x_m=handle_left),
        full_robot_solution=False,
        note="Sampled audit supplements integration guards; reference action coverage must be reviewed separately.")
    (folder / "rope_audit.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    audit(parser.parse_args().folder)
