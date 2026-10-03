"""Below-easy Hedgehog: the CLASSIC ball in a wider cage with three equal windows.

The ball is the easy tier's ball, resting in the same gravity-settled pose in both settings,
28 mm toward the robot from the cage axis: a 60 mm spike points at the robot and reaches about
29 mm outside the cage wall, so the gripper can hold it from outside. The common window width
sets the difficulty: at 118 mm (very_easy) the held ball leaves by translation alone; at 108 mm
(easier) it leaves only after one wrist roll about the held spike. Knobs: ``cage`` and
``ball_pose``. See topogym/planning/hedgehog_in_cage/below_easy_witness.py. These are design
targets, not robot qualifications.
"""
from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.hedgehog_in_cage import (
    HedgehogLayout, cage_meshes, hedgehog_meshes, load_template, write_body,
)
from topogym.solvers.collision.triangle_meshes import TriangleMeshPair
from topogym.tasks.base import merge_parameters
from .hedgehog_in_cage_easy import HedgehogInCageEasyTask


def cage(window_mm):
    """Three equal windows, one toward the robot (180 deg), so the bars stand evenly at 0/120/240 deg.

    Windows are [centre_deg, chord width at the inner wall in mm]. The cage is wider than CLASSIC
    (150 instead of 117 mm inside): a straight exit needs a window of about 102 mm or more, which
    three evenly spaced windows cannot give at 117 mm. Collars drop from 30 to 18 mm.
    """
    return {"inner_diameter_mm": 150., "windows": [[60., float(window_mm)], [180., float(window_mm)],
                                                   [300., float(window_mm)]], "collar_height_mm": 18.}


class HedgehogBelowEasyTask(HedgehogInCageEasyTask):
    """Shared construction; very_easy / easier set only the window width."""

    model_revision = "below_easy_v2"
    family_id = "below_easy_three_windows"
    # Gravity-settled on CPU (Genesis, 25 ms tick / 40 substeps, 5 s) in the 108 mm cage and
    # lifted 0.2 mm out of contact.
    defaults = merge_parameters(HedgehogInCageEasyTask.defaults, {
        "cage": cage(108.),
        "ball_pose": {"position_m": [-0.027999, 0., -0.049957],
                      "quaternion_wxyz": [0.422212, 0.423279, -0.060657, 0.799307]},
    })
    fixed_parameters = ("scale", "cage", "ball_pose")

    def template(self):
        """The CLASSIC template with this setting's cage size, windows and collar (template units = mm/scale)."""
        template = deepcopy(load_template())
        cage, scale = self.config["cage"], float(self.config["scale"])
        windows = np.asarray(cage["windows"], dtype=float)
        template["template_id"] += "+below_easy"
        template["cage"].update(outer_diameter=cage["inner_diameter_mm"] / scale + 2 * template["cage"]["wall_thickness"],
                                window_count=len(windows),
                                window_centers_deg=windows[:, 0].tolist(),
                                window_widths=(windows[:, 1] / scale).tolist(),
                                collar_height=cage["collar_height_mm"] / scale)
        return template

    def build_assets(self, folder):
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "template.json"
        path.write_text(json.dumps(self.template(), indent=2) + "\n")
        layout = HedgehogLayout(load_template(path), float(self.config["scale"]))  # reuse its validation
        cage, cage_parts = cage_meshes(layout)
        ball, ball_parts = hedgehog_meshes(layout)
        c, u = layout.template["cage"], layout.unit
        finish = self.config["finish"]
        report = dict(template_id=layout.template["template_id"], scale=layout.scale,
                      geometry_status="below_easy design from the CLASSIC reconstruction",
                      cage_geometry=dict(outer_radius_m=c["outer_diameter"] * u / 2,
                                         windows=self.config["cage"]["windows"],
                                         collar_height_m=c["collar_height"] * u),
                      cage=write_body(folder, "cage", cage, cage_parts, (.30, .36, .42, 1), 2700, finish),
                      hedgehog=write_body(folder, "hedgehog", ball, ball_parts, (.80, .83, .86, 1), 2700, finish),
                      initial_pose=self.checked_ball_pose(cage_parts, ball_parts),
                      reference_route_verified=False, physics_qualified=False)
        (folder / "asset_report.json").write_text(json.dumps(report, indent=2) + "\n")
        return cage, ball, -c["height"] * u / 2, report

    def checked_ball_pose(self, cage_parts, ball_parts):
        """The configured pose, rejected if the ball would start inside the cage walls."""
        pose = self.config["ball_pose"]
        q = np.asarray(pose["quaternion_wxyz"], dtype=float)
        transform = np.eye(4)
        transform[:3, :3] = Rotation.from_quat(q[[1, 2, 3, 0]]).as_matrix()
        transform[:3, 3] = pose["position_m"]
        pair = TriangleMeshPair((trimesh.util.concatenate(cage_parts), trimesh.util.concatenate(ball_parts)))
        clearance = pair.clearance((np.eye(4), transform))
        if clearance < 0:
            raise ValueError(f"{self.variation_id}: the ball pose intersects the cage")
        return dict(position_m=list(pose["position_m"]), quaternion_wxyz=q.tolist(),
                    clearance_to_cage_m=clearance, gravity_settled=True)
