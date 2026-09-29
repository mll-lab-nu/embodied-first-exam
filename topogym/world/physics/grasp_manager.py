"""World-owned automatic grasp lifecycle; no clock or policy execution loop."""
from copy import deepcopy
from dataclasses import asdict
from topogym.utils.grasp import relative_error


class GraspManager:
    def __init__(self, backend, config):
        self.backend, self.config = backend, config
        self.hands = {name: dict(intent=config.initial_intent, last_fraction=backend.fraction(name),
            phase="idle", candidate=None, stable_time_s=0., binding=None,
            rejection=None, solved_ticks=0) for name in backend.hands}
        self.events, self.event_sequence, self.tick = [], 0, 0

    def _event(self, hand, event, **details):
        self.event_sequence += 1
        self.events.append(dict(sequence=self.event_sequence, physics_step=self.tick,
                                hand=hand, event=event, **deepcopy(details)))

    def before_tick(self, tick):
        if tick != self.tick+1:
            raise RuntimeError("Grasp manager must advance with the World clock")
        self.tick, self.events = tick, []
        for name, state in self.hands.items():
            fraction = self.backend.fraction(name)
            delta = fraction-state["last_fraction"]
            if fraction <= self.config.intent_deadband or delta < -self.config.intent_deadband:
                state["intent"] = "open"
            elif delta > self.config.intent_deadband:
                state["intent"] = "close"
            if abs(delta) > self.config.intent_deadband or fraction <= self.config.intent_deadband:
                state["last_fraction"] = fraction
            if state["intent"] == "open":
                if state["binding"] is not None:
                    self.backend.release(state["binding"])
                    self._event(name, "released", reason="opening_intent", binding=state["binding"])
                state.update(phase="idle", candidate=None, stable_time_s=0., binding=None,
                             rejection=None, solved_ticks=0)

    def after_tick(self, dt):
        # Collect every hand's candidates first: simultaneous contested ownership
        # is rejected for both hands, independent of dictionary/arm iteration order.
        candidates = {}
        for name, state in self.hands.items():
            if state["intent"] == "close" and state["binding"] is None and state["phase"] != "lost":
                candidates[name] = self.backend.candidates(name)
        claimed = {tuple(s["binding"]["target"]): n for n, s in self.hands.items() if s["binding"]}
        for name, state in self.hands.items():
            binding = state["binding"]
            if binding is not None:
                reason = None
                if not self.backend.exists(binding):
                    reason = "constraint_missing"
                else:
                    if hasattr(self.backend, "check_health"):
                        reason = self.backend.check_health(binding)
                    else:  # Existing small test backends use the rigid protocol.
                        reason = self.backend.health_reason(binding)
                        translation, angle = relative_error(binding["relative_pose"], self.backend.relative_pose(name, binding["target"]))
                        if translation > self.config.max_translation_error_m or angle > self.config.max_rotation_error_rad:
                            reason = "relative_pose_error"
                if reason:
                    if self.backend.exists(binding):
                        self.backend.release(binding)
                    self._event(name, "lost", reason=reason, binding=binding)
                    state.update(phase="lost", binding=None, candidate=None, stable_time_s=0., rejection=reason)
                else:
                    state["solved_ticks"] += 1
                    state["phase"] = "holding"
                continue
            if name not in candidates:
                continue
            available = candidates[name]
            reason = "no_bilateral_candidate" if not available else None
            if len(available) > 1:
                reason = "ambiguous_candidates"
            key = tuple(available[0]) if len(available) == 1 else None
            conflicts = getattr(self.backend, "conflicts", lambda a, b: a == b)
            if key is not None and (any(conflicts(key, k) for k in claimed) or
                    any(conflicts(key, k) for other, choices in candidates.items() if other != name for k in choices)):
                reason = "ownership_conflict"
            if reason:
                state.update(candidate=None, stable_time_s=0., phase="idle", rejection=reason)
                continue
            state["stable_time_s"] = state["stable_time_s"]+dt if state["candidate"] == key else dt
            state.update(candidate=key, phase="qualifying", rejection=None)
            if state["stable_time_s"]+1.e-12 >= self.config.stable_time_s:
                binding = self.backend.acquire(name, key)
                state.update(binding=binding, phase="registered", solved_ticks=0)
                claimed[key] = name
                self._event(name, "acquired", binding=binding, effective_from_physics_step=self.tick+1,
                            stable_time_s=state["stable_time_s"])

    def capture(self):
        state = dict(schema_version=1, config=asdict(self.config), hands=self.hands,
                     events=self.events, event_sequence=self.event_sequence, physics_step=self.tick)
        if hasattr(self.backend, "capture"):
            state["backend"] = self.backend.capture()
        return deepcopy(state)

    def restore(self, state):
        if state["schema_version"] != 1 or state["config"] != asdict(self.config) or set(state["hands"]) != set(self.hands):
            raise ValueError("Grasp checkpoint does not match this manager")
        if hasattr(self.backend, "restore"):
            self.backend.restore(state["backend"])
        self.backend.verify_bindings([s["binding"] for s in state["hands"].values() if s["binding"]])
        saved = deepcopy(state)
        self.hands, self.events = saved["hands"], saved["events"]
        self.event_sequence, self.tick = saved["event_sequence"], saved["physics_step"]

    def read(self):
        model = dict(
            acquisition_evidence="same_final_rigid_substep_bilateral_contact",
            sampling_scope="one sample per World tick; no continuous contact claim",
            constraint_model="ideal_six_dof_weld", reaction_force=None)
        if hasattr(self.backend, "read_model"):
            model = self.backend.read_model()
        return self.capture() | dict(active=any(s["binding"] for s in self.hands.values())) | model
