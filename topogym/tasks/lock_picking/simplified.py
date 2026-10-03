"""Approved two-rotor locks; complete robot solving is separately qualified."""
from topogym.assets.geometry.lock_picking_simplified import TwoDiscLockGeometry
from topogym.tasks.base import merge_parameters

from .common import LockPickingTask
from .lock_picking_easy import LockPickingEasyTask


class SimplifiedLockPickingTask(LockPickingTask):
    geometry_type = TwoDiscLockGeometry
    model_revision = "two_rotor_v1"
    terminal_revision = "terminal_v5_two_rotor_bore_contact"
    # Preserve easy's radii, thicknesses, spacing, finishes, physics and rest.
    # Only the stack/shaft length, apertures and passive stop travel change.
    variant_parameters = merge_parameters(LockPickingEasyTask.variant_parameters, {
        "geometry": {
            "grip_offset": .345,  # 2 * 150 mm + the existing 45 mm margin.
            "slots": [[0.], [0.]],
            "initial_disc_deg": [0., 0.],
        },
        "rotor_stops": [
            {"style": "single_ring", "bounds_deg": [-3., 3.], "ear_phase_deg": -35.},
            {"style": "single_ring", "bounds_deg": [-3., 3.], "ear_phase_deg": -35.},
        ],
    })
    defaults = merge_parameters(LockPickingTask.defaults, variant_parameters)
    fixed_parameters = ("geometry", "rotor_stops")
