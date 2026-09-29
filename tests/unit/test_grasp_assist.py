"""Negative acquisition cases, ownership and rewind; not physical qualification."""
from copy import deepcopy
from dataclasses import asdict
import numpy as np
import pytest
from topogym.utils.grasp import (GraspAssistConfig, GraspTarget, bilateral_contact_rows,
                                material_patch, closed_fraction)
from topogym.world.physics.grasp_manager import GraspManager


def test_bilateral_evidence_cannot_mix_links_times_or_speculative_contacts():
    c = dict(link_a=np.array([1, 2]), link_b=np.array([3, 4]),
             penetration=np.array([0., 0.]), position=np.zeros((2, 3)))
    def match(data):
        return bilateral_contact_rows(data, (1, 2), 3, center_m=[0, 0, 0], radius_m=.01, max_penetration_m=.001)
    assert match(c) == ()  # Different object for the second finger.
    c["link_b"][1] = 3
    assert match(c) == (0, 1)
    c["penetration"][1] = -.0001
    assert match(c) == ()
    c["penetration"][1] = .002
    assert match(c) == ()
    c["penetration"][1] = 0.
    c["position"][1, 0] = .02
    assert match(c) == ()
    # Each snapshot contains only one finger; prior calls cannot authorize.
    for row in (0, 1):
        assert match({k: v[row:row+1] for k, v in c.items()}) == ()


def test_patch_does_not_capture_nearby_other_material_layer():
    x = np.array([[0, 0, 0], [.001, 0, 0], [0, 0, .001]])
    uv = np.array([[0, 0], [.001, 0], [1, 1]])
    np.testing.assert_array_equal(material_patch(x, uv, 0, spatial_radius_m=.01, material_radius_m=.01), [0, 1])
    assert closed_fraction(.8, 0., .8) == 1.
    assert closed_fraction(.002, .037, .002) == 1.


class Backend:
    hands = ("left", "right")
    def __init__(self):
        self.fractions = {n: 0. for n in self.hands}
        self.choices = {n: [] for n in self.hands}
        self.constraints = {}
        self.reference = dict(position_m=[0., 0., 0.], quaternion_wxyz=[1., 0., 0., 0.])
    def fraction(self, name): return self.fractions[name]
    def candidates(self, name): return self.choices[name]
    def relative_pose(self, *args): return deepcopy(self.reference)
    def health_reason(self, binding): return None
    def acquire(self, name, key):
        binding = dict(hand=name, target=key, relative_pose=deepcopy(self.reference))
        self.constraints[name] = deepcopy(binding)
        return binding
    def exists(self, binding): return binding["hand"] in self.constraints
    def release(self, binding): del self.constraints[binding["hand"]]
    def verify_bindings(self, bindings):
        if {b["hand"]: b for b in bindings} != self.constraints:
            raise ValueError("Real binding mismatch")


def manager():
    b = Backend()
    return b, GraspManager(b, GraspAssistConfig("contact_weld_v1", (GraspTarget("cube", "body"),)))


def tick(m, dt=.01):
    m.before_tick(m.tick+1)
    m.after_tick(dt)


def test_continuous_admission_holding_independent_release_and_loss_latch():
    b, m = manager()
    b.fractions.update(left=.6, right=.5)
    b.choices.update(left=[("a", "body")], right=[("b", "body")])
    tick(m)
    assert not b.constraints
    b.choices["left"] = []
    tick(m)
    assert set(b.constraints) == {"right"}
    b.choices["left"] = [("a", "body")]
    tick(m); tick(m)
    assert set(b.constraints) == {"left", "right"}
    b.fractions["right"] = .3  # Partial opening releases; not only full-open.
    tick(m)
    assert set(b.constraints) == {"left"}
    assert m.hands["left"]["phase"] == "holding"
    del b.constraints["left"]
    tick(m); tick(m)
    assert m.hands["left"]["phase"] == "lost" and not b.constraints
    b.fractions["left"] = 0.
    tick(m)
    b.fractions["left"] = .6
    tick(m); tick(m)
    assert set(b.constraints) == {"left"}


def test_ambiguity_and_simultaneous_same_object_ownership_are_rejected():
    b, m = manager()
    b.fractions.update(left=.5, right=.5)
    b.choices.update(left=[("a", "body")], right=[("a", "body")])
    for _ in range(4): tick(m)
    assert not b.constraints
    assert all(s["rejection"] == "ownership_conflict" for s in m.hands.values())
    b.choices.update(left=[("a", "body"), ("b", "body")], right=[])
    tick(m)
    assert m.hands["left"]["rejection"] == "ambiguous_candidates"


def test_pregrasp_born_closed_acquires_only_with_initial_close_intent():
    def born_closed(**options):
        b = Backend()
        b.fractions.update(left=1., right=0.)   # left starts closed on its piece; right open
        b.choices.update(left=[("a", "body")], right=[("b", "body")])
        return b, GraspManager(b, GraspAssistConfig("contact_weld_v1", (GraspTarget("cube", "body"),), **options))
    b, m = born_closed()
    for _ in range(4): tick(m)
    assert not b.constraints  # Default: no closing command after birth, no weld.
    b, m = born_closed(initial_intent="close")
    for _ in range(4): tick(m)
    assert set(b.constraints) == {"left"}  # An open-born hand still needs a real close.
    with pytest.raises(ValueError): GraspAssistConfig("contact_weld_v1", (GraspTarget("a", "b"),), initial_intent="grip")


def test_restore_copies_timers_ownership_and_events_without_reacquisition():
    b, m = manager()
    b.fractions["left"] = .5
    b.choices["left"] = [("a", "body")]
    tick(m)
    early = m.capture()
    tick(m)
    held, native = m.capture(), deepcopy(b.constraints)
    b.fractions["left"] = 0.
    tick(m)
    b.constraints = native
    m.restore(held)
    assert m.capture() == held
    m.hands["left"]["binding"]["relative_pose"]["position_m"][0] = 9.
    assert held["hands"]["left"]["binding"]["relative_pose"]["position_m"][0] == 0.
    b.constraints = {}
    m.restore(early)
    b.fractions["left"] = .5
    tick(m)
    assert m.capture() == held
    with pytest.raises(ValueError, match="mismatch"):
        b.constraints = {}; m.restore(held)


def test_configs_own_immutable_targets_and_reject_incomplete_modes():
    with pytest.raises(ValueError): GraspAssistConfig("contact_weld_v1")
    with pytest.raises(ValueError): GraspAssistConfig(targets=(GraspTarget("a", "b"),))
    values = [0., 0., 0.]
    target = GraspTarget("a", "b", values)
    values[0] = 9.
    assert asdict(target)["center_m"] == (0., 0., 0.)
    from topogym.simulator.config import SimulatorConfig
    from topogym.utils.io import to_jsonable
    config = SimulatorConfig(grasp_assist=GraspAssistConfig('contact_weld_v1', (target,)))
    serialized = to_jsonable(config)
    restored = SimulatorConfig(**serialized)
    serialized['grasp_assist']['targets'][0]['center_m'][0] = 99.
    assert restored.grasp_assist == config.grasp_assist
    with pytest.raises(ValueError, match='Invalid grasp_assist'):
        SimulatorConfig(grasp_assist={'model': 'contact_weld_v1', 'unknown': True})


def test_actual_finger_opening_invalidates_hold_until_explicit_reopen():
    b, m = manager()
    b.fractions['left'] = .5
    b.choices['left'] = [('a', 'body')]
    tick(m); tick(m)
    b.health_reason = lambda binding: 'physical_fingers_opened'
    tick(m)
    assert not b.constraints and m.hands['left']['phase'] == 'lost'
    b.health_reason = lambda binding: None
    tick(m)
    assert not b.constraints


def test_initial_closed_target_does_not_create_hidden_pregrasp_and_small_opening_accumulates():
    b = Backend()
    b.fractions['left'] = .8
    b.choices['left'] = [('a', 'body')]
    m = GraspManager(b, GraspAssistConfig('contact_weld_v1', (GraspTarget('a', 'body'),)))
    for _ in range(3): tick(m)
    assert not b.constraints
    b.fractions['left'] = .9
    tick(m); tick(m)
    assert b.constraints
    for fraction in (.899, .898, .897):
        b.fractions['left'] = fraction
        tick(m)
    assert not b.constraints and m.hands['left']['intent'] == 'open'


def test_non_tail_deletion_preserves_every_surviving_row_and_static_constraint(monkeypatch):
    from dataclasses import make_dataclass
    from types import SimpleNamespace as NS
    import genesis as gs
    import topogym.world.physics.grasp_rigid as module
    class Field:
        def __init__(self, data): self.data = np.array(data)
        def to_numpy(self): return self.data.copy()
        def from_numpy(self, data): self.data = data.copy()
    names = sorted(module.EQUALITY_FIELDS)
    values = dict(eq_obj1id=Field([[0], [1], [3], [5]]), eq_obj2id=Field([[9], [2], [4], [6]]),
        eq_type=Field(np.full((4, 1), int(gs.EQUALITY_TYPE.WELD))),
        eq_data=Field(np.arange(44).reshape(4, 1, 11)), sol_params=Field(np.arange(28).reshape(4, 1, 7)))
    info = make_dataclass('Info', names)(**values)
    old = {n: f.to_numpy() for n, f in values.items()}
    count = Field([4])
    solver = NS(equalities_info=info, constraint_solver=NS(
        constraint_state=NS(qd_n_equalities=count), _eq_const_info_cache={'stale': True}),
        _rigid_global_info=NS(n_equalities=Field(1)))
    monkeypatch.setattr(module, 'version', lambda _: '1.2.1')
    module.delete_weld_preserving_others(solver, 1, 2)
    assert count.to_numpy()[0] == 3
    for n, field in values.items():
        np.testing.assert_array_equal(field.to_numpy()[:3], old[n][[0, 3, 2]])
    assert not solver.constraint_solver._eq_const_info_cache
    with pytest.raises(RuntimeError, match='exactly one'):
        module.delete_weld_preserving_others(solver, 0, 9)  # Static row cannot be deleted.
