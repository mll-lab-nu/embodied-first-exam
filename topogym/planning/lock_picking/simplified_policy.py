"""Measured-pose robot oracles for the approved two-rotor lock scenes.

Only ordinary EE_ABS actions are emitted. The key acquires its grasp through
bilateral contact; the first passive rotor is turned by a key tab, never set.
"""
from .lock_picking_medium_planning import LockPickingMediumPolicy


class SimplifiedLockPickingPolicy(LockPickingMediumPolicy):
    def __init__(self, *, rotor_stops, endpoint_depth=3.08, **kwargs):
        super().__init__(**kwargs)
        if [list(row) for row in self.geometry["slots"]] != [[0.], [0.]]:
            raise ValueError("The simplified oracle requires two single-slot rotors")
        if len(rotor_stops) != 2 or not 3.07 <= endpoint_depth <= 3.10:
            raise ValueError("Expected two rotor stops and a bounded END insertion depth")
        initial = self.geometry["initial_disc_deg"]
        if list(initial) not in ([0., 0.], [20., 0.]):
            raise ValueError("Unsupported simplified lock initial angles")
        self.rotor_stops = rotor_stops
        self.endpoint_depth = float(endpoint_depth)

    def _actions(self):
        if self.part == "pickup":
            yield from super()._actions()
            return
        self.grip = .8
        self.precise_insertion = True
        first = self._disc_angle(0)
        if abs(first) > 1.:
            yield from self._move_key(angle=first, seconds=2., phase="align_first_slot")
            yield from self._move_key(depth=1., angle=first, seconds=5., phase="engage_first_rotor")
            backlash = self.geometry["slot_half_deg"]-self.geometry["tab_half_deg"]
            # With the leading tab inside D1, the negative slot edge transmits
            # torque after the angular backlash is taken up. D2 is not engaged.
            yield from self._move_key(angle=-backlash, seconds=4., phase="turn_first_rotor")
            yield from self._move_key(angle=0., seconds=1.5, phase="center_first_slot")
            angles = [self._disc_angle(i) for i in range(2)]
            if max(abs(a) for a in angles) > 2.:
                raise RuntimeError(f"Rotor alignment did not converge: {angles}")
        else:
            yield from self._move_key(angle=0., seconds=1., phase="align_straight_entry")
        yield from self._move_key(depth=1.15, angle=0., seconds=4., phase="pass_first_rotor")
        yield from self._move_key(depth=2.15, angle=0., seconds=6., phase="pass_second_rotor")
        yield from self._move_key(depth=self.endpoint_depth, angle=0., seconds=6., phase="insert_END")
        self.phase = "confirm_insertion"
        yield from self._hold(1., require_grasp=True)
        # SegmentRunner stops on native Task success, including its 0.5 s
        # confirmation window. Reaching the end of this program is not success.
