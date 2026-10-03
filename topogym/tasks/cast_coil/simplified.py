"""Reviewed cube geometries with external grasps and the original Coil goal."""
import numpy as np
from scipy.spatial.transform import Rotation

from topogym.assets.geometry.cast_coil_simplified import (
    SimplifiedCoilAssembly, generate_assets, scaled_record)
from topogym.assets.variation_resources import read_json
from topogym.utils.grasp import GraspAssistConfig, GraspTarget
from .common import CastCoilTask


def grasp_points(record):
    """Pad centres near the two outside X faces; jaws close outside Y faces.

    Approach penetration is only 2 mm so fingers stay on each piece's outside
    spine, including during the easier lateral motion.
    """
    half = record["parameters"]["edge_mm"]*.0005
    return {"right": np.array([-half+.002, 0., 0.]),
            "left": np.array([half-.002, 0., 0.])}


class SimplifiedCoilTask(CastCoilTask):
    # The authored cube is 102 mm. At half scale it clears the ALOHA's
    # physical fingertip aperture (rail travel is not the usable opening).
    defaults = dict(CastCoilTask.defaults, scale=.5, center_xy_m=[-.07, .02],
                    yaw_deg=180., initial_xy_offset_m=[-.13, 0.],
                    initial_silver_yaw_deg=15.)
    fixed_parameters = ("scale", "objective")
    geometry_resource = None

    def geometry(self):
        return scaled_record(read_json(self.geometry_resource), self.config["scale"])

    def build_assets(self, folder):
        return generate_assets(folder, record=self.geometry(), allow_existing_empty=True)

    def initial_silver_rotation(self, rotation):
        angle = float(self.config["initial_silver_yaw_deg"])
        if not np.isfinite(angle):
            raise ValueError("Initial silver yaw must be finite")
        return rotation * Rotation.from_euler("z", angle, degrees=True)

    def grasp_assist(self):
        assembly = SimplifiedCoilAssembly(record=self.geometry())
        points = grasp_points(assembly.record)
        return GraspAssistConfig("contact_weld_v1", tuple(
            GraspTarget(body.name, body.name,
                        tuple(points[side]-body.visual.center_mass), .038)
            for side, body in zip(("right", "left"), assembly.bodies)))
