"""Two prealigned rotors: pick up the two-tab key and insert it straight."""
from .simplified import SimplifiedLockPickingTask


class LockPickingVeryEasyTask(SimplifiedLockPickingTask):
    variation_id = "lock_picking_very_easy"
    family_id = "two_rotor_aligned"
    difficulty = "very_easy"
    instruction = (
        "Pick up the two-tab key from its rest and insert it through the two "
        "prealigned rotor slots and the final fixed plate."
    )
