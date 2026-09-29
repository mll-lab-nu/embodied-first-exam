"""lock_picking: standard_150mm. Difficulty is a design target, not a qualification."""

from .common import LockPickingTask
from topogym.tasks.base import merge_parameters


class LockPickingMediumTask(LockPickingTask):
    # Keep 45 mm of handle clearance beyond three pitches, as in the
    # 150 mm candidate checked with the current table and camera placement.
    # Restore the successful two-retreat mechanism, keeping the common lab placement.
    variant_parameters = {
        'geometry': {'pitch': .150, 'grip_offset': .495, 'bore_radius': .0075,
                     'slot_half_deg': 8., 'slots': [[-60., -30., 0.], [-60.], [0.]],
                     'initial_disc_deg': [0., 0., 0.], 'initial_key_deg': 0., 'endpoint_deg': 0.},
        'rotor_stops': [
            {'style': 'single_ring', 'bounds_deg': [-15., 15.], 'ear_phase_deg': -35.},
            {'style': 'single_ring', 'bounds_deg': [-10., 75.], 'ear_phase_deg': -35.},
            {'style': 'single_ring', 'bounds_deg': [-180., 180.], 'ear_phase_deg': -35.}],
    }
    defaults = merge_parameters(LockPickingTask.defaults, variant_parameters)
    variation_id = 'lock_picking_medium'
    family_id = 'standard_150mm'
    model_revision = 'historical_physics_v2'
    difficulty = 'medium'
