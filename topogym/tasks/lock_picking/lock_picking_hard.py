"""lock_picking: F3. Difficulty is a design target, not a qualification."""

from .common import LockPickingTask
from topogym.tasks.base import merge_parameters


class LockPickingHardTask(LockPickingTask):
    variant_parameters = {'geometry': {'pitch': 0.15, 'disc_radius': 0.08, 'disc_thickness': 0.01, 'bore_radius': 0.0075, 'slot_radius': 0.045, 'slot_half_deg': 8.0, 'tab_radius': 0.036, 'tab_half_deg': 4.0, 'tab_thickness': 0.005, 'shaft_radius': 0.0065, 'grip_offset': 0.495, 'handle_radius': 0.018, 'slots': [[-72.0, -48.0, -24.0, 0.0], [-72.0], [0.0]], 'initial_disc_deg': [0.0, 0.0, 0.0], 'initial_key_deg': 0.0, 'endpoint_deg': 0.0}, 'rotor_stops': [{'style': 'single_ring', 'bounds_deg': [-12.0, 12.0], 'ear_phase_deg': -35}, {'style': 'single_ring', 'bounds_deg': [-10.0, 87.0], 'ear_phase_deg': -35}, {'style': 'single_ring', 'bounds_deg': [-180, 180], 'ear_phase_deg': -35}]}
    defaults = merge_parameters(LockPickingTask.defaults, variant_parameters)
    variation_id = 'lock_picking_hard'
    family_id = 'F3'
    model_revision = 'seed_families_v1'
    difficulty = 'hard'
    fixed_parameters = ('geometry.slots', 'geometry.pitch', 'geometry.initial_disc_deg', 'rotor_stops')
