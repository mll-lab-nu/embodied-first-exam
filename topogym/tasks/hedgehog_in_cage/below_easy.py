"""Below-easy Hedgehog: the CLASSIC ball in a cage whose window toward the robot is widened.

Two knobs set the difficulty: ``cage`` (window layout and collar height) and ``ball_pose``,
the ball's gravity-settled pose in the cage frame. The ball is the easy tier's ball,
unchanged. In both settings a long spike points at the robot and reaches outside the cage,
so the gripper can hold it from outside. very_easy rests where a translation-only exit
exists; easier rests where one wrist roll about that spike is needed first. See
topogym/planning/hedgehog_in_cage/below_easy_witness.py. These are design targets, not
robot qualifications.
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
from .common import HedgehogInCageTask


class HedgehogBelowEasyTask(HedgehogInCageTask):
    """Shared construction; very_easy / easier fix ``cage`` and ``ball_pose``."""

    model_revision = "below_easy_v1"
    family_id = "below_easy_wide_window"
    # Windows are [centre_deg, chord width at the inner wall in mm]. The 144/216 deg pair of the
    # CLASSIC cage becomes one 106 mm window facing the robot (180 deg); collars 30 -> 18 mm.
    # Both settings share this cage, so the resting pose alone sets the difficulty.
    defaults = merge_parameters(HedgehogInCageTask.defaults, {
        "cage": {"windows": [[0., 60.], [72., 55.5], [180., 106.], [288., 55.5]],
                 "collar_height_mm": 18.},
        "ball_pose": {"position_m": [0., 0., 0.], "quaternion_wxyz": [1., 0., 0., 0.]},
    })
    fixed_parameters = ("scale", "cage", "ball_pose")

    def template(self):
        """The CLASSIC template with this setting's windows and collar (template units = mm/scale)."""
        template = deepcopy(load_template())
        cage, scale = self.config["cage"], float(self.config["scale"])
        windows = np.asarray(cage["windows"], dtype=float)
        template["template_id"] += "+below_easy"
        template["cage"].update(window_count=len(windows),
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
