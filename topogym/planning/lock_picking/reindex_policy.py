"""Three current lock families, executed by a robot with measured-pose feedback."""
import numpy as np

from .lock_picking_medium_planning import LockPickingMediumPolicy


class LockPickingReindexPolicy(LockPickingMediumPolicy):
    """A passive action policy: no simulator, setters, or manual grasp binding."""
    def __init__(self, *, rotor_stops, endpoint_depth=4.08, **kwargs):
        super().__init__(**kwargs)
        self.rotor_stops = rotor_stops
        if not np.isfinite(endpoint_depth) or not 4.06 <= endpoint_depth <= 4.12:
            raise ValueError("Endpoint depth must stay inside the bounded local insertion range")
        self.endpoint_depth = float(endpoint_depth)
        slots = np.asarray(self.geometry["slots"][0], float)
        bound = rotor_stops[0]["bounds_deg"][1]
        if (len(slots) not in (2, 3, 4) or not np.allclose(np.diff(slots), 2*bound)
                or list(self.geometry["slots"][1]) != [slots[0]]
                or list(self.geometry["slots"][2]) != [0.] or slots[-1] != 0.):
            raise ValueError("Unsupported lock reindex family")

    def _actions(self):
        if self.part == "pickup":
            yield from super()._actions()
            return
        self.grip = .8
        slots = self.geometry["slots"][0]
        backlash = self.geometry["slot_half_deg"]-self.geometry["tab_half_deg"]
        swing = self.rotor_stops[0]["bounds_deg"][1]-1.5
        yield from self._move_key(angle=slots[0], seconds=2.75, phase="align_entry")
        yield from self._move_key(depth=1., angle=slots[0], seconds=6.5, phase="insert_D1")
        yield from self._move_key(depth=2., angle=slots[0], seconds=5.5, phase="insert_D2")
        for branch, slot in enumerate(slots):
            last = branch == len(slots)-1
            phase = "align_all_discs" if last else f"index_{branch+1}"
            # Half a degree of nominal overtravel at final alignment is inherited
            # from the measured medium route; rotor limits remain unchanged.
            target = backlash+.5 if last else slot+swing+backlash
            yield from self._move_key(angle=target, seconds=4.5, phase=phase)
            yield from self._hold(.75, require_grasp=True)
            if last:
                break
            prefix = f"retreat_{branch+1}"
            # Center in the measured common aperture before axial withdrawal.
            center = self._entry_angle(branch)
            yield from self._move_key(angle=center, seconds=1.2, phase=prefix+"_center")
            yield from self._move_key(depth=1.15, angle=center, seconds=6.5,
                                      phase=prefix+"_clear_D2")
            center = self._disc_angle(0)+slot
            yield from self._move_key(angle=center, seconds=1., phase=prefix+"_align_D1")
            yield from self._move_key(depth=1., angle=center, seconds=1., phase=prefix+"_enter_D1")
            yield from self._move_key(angle=slot-swing-backlash, seconds=4.5,
                                      phase=f"reset_{branch+1}_D1")
            yield from self._hold(.75, require_grasp=True)
            yield from self._move_key(depth=1.15, seconds=1.6, phase=f"gap_{branch+1}")
            selected = self._entry_angle(branch+1)
            yield from self._move_key(angle=selected, seconds=3.75, phase=f"select_slot_{branch+1}")
            yield from self._move_key(depth=2., angle=selected, seconds=5.5,
                                      phase=f"reinsert_{branch+1}_D2")
        yield from self._move_key(angle=0., seconds=1.3, phase="center_final_slots")
        yield from self._move_key(depth=3., angle=0., seconds=6.5, phase="insert_third_disc")
        yield from self._hold(1., require_grasp=True)
        yield from self._regrasp()
        yield from self._move_key(depth=3.8, angle=0., seconds=6.5, phase="approach_endpoint")
        yield from self._move_key(depth=self.endpoint_depth, angle=0., seconds=4.5, phase="insert_endpoint")
        self.phase = "hold_final_insertion"
        yield from self._hold(.6, require_grasp=True)
        self.phase, self.grip = "release_at_goal", 0.
        yield {"arm": {"gripper_position_rad": self.grip}}
        yield from self._hold(2.)
        if self._holding():
            raise RuntimeError("Automatic grasp failed to release")
        p, r = self._tcp()
        yield from self._move(p+[0, 0, .13], r, 1.5, "withdraw_gripper")
        self.phase = "verify_stable_insertion"
        start, stable_since = self._time(), None
        while self._time()-start < 15.:
            key = self.obs["privileged"]["world"]["bodies"]["lock_key"]
            quiet = (not self._holding() and np.linalg.norm(key["linear_velocity_m_s"]) < .01
                     and np.linalg.norm(key["angular_velocity_rad_s"]) < .1)
            stable_since = (self._time() if stable_since is None else stable_since) if quiet else None
            if stable_since is not None and self._time()-stable_since >= .5:
                return
            yield {}
        raise RuntimeError("Released key did not remain at rest for 0.5 s within 15 s")
