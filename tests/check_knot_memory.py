"""Forward cache ownership must preserve rollover and caller snapshots."""
from types import SimpleNamespace
import unittest

from topogym.tasks.knot_untying.runtime_memory import ForwardOnlyMemory


class StateQueue:
    def __init__(self):
        self.states = {}

    def append(self, value):
        self.states.setdefault(0, []).append(value)

    def discard(self, value):
        self.states[0].remove(value)
        if not self.states[0]:
            del self.states[0]


class MemoryTests(unittest.TestCase):
    def fixture(self, *, gradients=False):
        solver = SimpleNamespace(_ckpt={}, rollovers=[])
        rope = SimpleNamespace(_queried_states=StateQueue(), current_position=0.)

        def save(name):
            solver._ckpt.setdefault(name, {})['position'] = rope.current_position
            solver.rollovers.append(rope.current_position)
            return rope.current_position

        def query():
            state = SimpleNamespace(position=rope.current_position)
            rope._queried_states.append(state)
            return state

        solver.save_ckpt, rope.get_state = save, query
        scene = SimpleNamespace(sim=SimpleNamespace(requires_grad=gradients, fem_solver=solver))
        return scene, solver, rope

    def test_bounded_history_preserves_every_rollover(self):
        scene, solver, rope = self.fixture()
        policy = ForwardOnlyMemory(scene, rope)
        for i in range(1000):
            rope.current_position = i
            self.assertEqual(solver.save_ckpt(str(i)), i)
        self.assertEqual(solver.rollovers, list(range(1000)))
        self.assertEqual(len(solver._ckpt), 1)
        self.assertTrue(policy.report()['passed'])

    def test_returned_snapshots_remain_independent(self):
        scene, _, rope = self.fixture()
        policy = ForwardOnlyMemory(scene, rope)
        snapshots = []
        for i in range(30):
            rope.current_position = i
            snapshots.append(rope.get_state())
        self.assertEqual([s.position for s in snapshots], list(range(30)))
        self.assertEqual(policy.report()['retained_queries'], 0)

    def test_gradient_execution_is_rejected_before_mutation(self):
        scene, solver, rope = self.fixture(gradients=True)
        original = solver.save_ckpt
        with self.assertRaisesRegex(ValueError, 'gradient history'):
            ForwardOnlyMemory(scene, rope)
        self.assertIs(solver.save_ckpt, original)


if __name__ == '__main__':
    unittest.main()
