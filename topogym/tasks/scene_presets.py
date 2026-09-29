"""Default task scenes, independent of the simulator API and recording settings.

Task classes consume these defaults directly, so ordinary make/reset and named
variations share the same baseline. No historical demo directory is consulted.
"""
from copy import deepcopy
import json
from pathlib import Path

SCENE_PRESET_ID = "lab_tasks_v1"

PRESETS = {
    "horseshoe_ring": {"target_ring_finish": "copper"},
    "hedgehog_in_cage": {"finish": "wood"},
    "buzz_wire_3d": {
        "linear_scale": 0.60, "center_xy_m": [-0.08, -0.27],
        "base_elevation_m": 0.04,
    },
    "lock_picking": {
        "geometry": {"first_x": 0.0, "center_y": -0.26},
        "aperture_outline": {
            "enabled": True, "width_m": 0.0008, "color_rgb": [1.0, 0.95, 0.0],
        },
        "rotor_stops": [
            {"style": "single_ring", "bounds_deg": [-15., 35.], "ear_phase_deg": -35.},
            {"style": "single_ring", "bounds_deg": [-10., 75.], "ear_phase_deg": -35.},
            {"style": "single_ring", "bounds_deg": [-180., 180.], "ear_phase_deg": -35.},
        ],
    },
    "fiber_bundling": {},
    "rope_threading": {"geometry": {"translation_m": [-0.1156786, 0.03, 0.0015], "yaw_deg": 75.}},
    "knot_untying": {},
    "orbits": {
        "linear_scale": 0.85, "yaw_deg": 90.0,
        "placement_anchor": "base_center", "base_center_xy_m": [-0.1356786, 0.0],
        # Retain the original assembly-AABB coordinate for explicit legacy layouts.
        "center_xy_m": [-0.1356786, -0.24],
    },
    "slotted_post_ring": {"center_xy_m": [-0.02, 0.04]},
}


def defaults(task_id, **parameters):
    """Return independent task defaults; the preset identity enters instance hash."""
    return {**deepcopy(parameters), **deepcopy(PRESETS[task_id]),
            "scene_preset_id": SCENE_PRESET_ID}


def record_preset(task, folder):
    if task.config["scene_preset_id"] != SCENE_PRESET_ID:
        raise ValueError(f"Unknown scene_preset_id: {task.config['scene_preset_id']!r}")
    from topogym.assets.scene_visuals import SURFACES
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    record = dict(scene_preset_id=SCENE_PRESET_ID, task_id=task.task_id,
                  parameters=task.identity_config(), visual_roles=SURFACES)
    (folder / "scene_preset.json").write_text(json.dumps(record, sort_keys=True, indent=2)+"\n")
    return {"scene_preset_id": SCENE_PRESET_ID}
