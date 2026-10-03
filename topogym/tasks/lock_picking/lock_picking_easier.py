"""Align only the first rotor, then insert the two-tab key."""
from topogym.tasks.base import merge_parameters

from .simplified import SimplifiedLockPickingTask


class LockPickingEasierTask(SimplifiedLockPickingTask):
    variation_id = "lock_picking_easier"
    family_id = "two_rotor_first_turn"
    difficulty = "easier"
    instruction = (
        "Align the first rotor with the already aligned second rotor, then "
        "insert the two-tab key through both slots and the final fixed plate."
    )
    variant_parameters = merge_parameters(SimplifiedLockPickingTask.variant_parameters, {
        "geometry": {"initial_disc_deg": [20., 0.]},
        "rotor_stops": [
            {"style": "single_ring", "bounds_deg": [-3., 23.], "ear_phase_deg": -35.},
            {"style": "single_ring", "bounds_deg": [-3., 3.], "ear_phase_deg": -35.},
        ],
    })
    defaults = merge_parameters(SimplifiedLockPickingTask.defaults, variant_parameters)
