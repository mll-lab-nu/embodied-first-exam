"""Forward-only cache reuse must preserve rollover and returned snapshots."""
from types import SimpleNamespace
import unittest

from topogym.tasks.rope_threading.runtime_memory import ForwardOnlyMemory


class Queue:
    def __init__(self):
        self.states = {}

    def append(self, state):
        self.states.setdefault(0, []).append(state)

    def discard(self, state):
        self.states[0].remove(state)
        if not self.states[0]:
            del self.states[0]


class Solver:
    def __init__(self):
        self._ckpt = {}
        self.rollovers = []

    def save_ckpt(self, name):
        storage = self._ckpt.setdefault(name, [None])
        storage[0] = len(self.rollovers)
        self.rollovers.append(storage[0])
        return storage[0]


class Rope:
    def __init__(self):
        self._queried_states = Queue()
        self.value = 0

    def get_state(self):
        state = SimpleNamespace(position=self.value, velocity=-self.value)
        self._queried_states.append(state)
        return state


class MemoryTests(unittest.TestCase):
    def fixture(self, gradient=False):
        solver, rope = Solver(), Rope()
        scene = SimpleNamespace(sim=SimpleNamespace(requires_grad=gradient, fem_solver=solver))
        return scene, solver, rope

    def test_original_rollover_occurs_every_time_with_bounded_storage(self):
        scene, solver, rope = self.fixture()
        policy = ForwardOnlyMemory(scene, rope)
        for frame in range(1000):
            self.assertEqual(solver.save_ckpt(str(frame)), frame)
        self.assertEqual(solver.rollovers, list(range(1000)))
        self.assertEqual(len(solver._ckpt), 1)
        self.assertTrue(policy.report()["passed"])

    def test_returned_snapshots_stay_valid_without_queue_ownership(self):
        scene, solver, rope = self.fixture()
        policy = ForwardOnlyMemory(scene, rope)
        snapshots = []
        for value in range(30):
            rope.value = value
            snapshots.append(rope.get_state())
        self.assertEqual([s.position for s in snapshots], list(range(30)))
        self.assertEqual([s.velocity for s in snapshots], [-i for i in range(30)])
        self.assertEqual(policy.report()["retained_queries"], 0)

    def test_gradient_history_is_never_discarded(self):
        scene, solver, rope = self.fixture(gradient=True)
        with self.assertRaisesRegex(ValueError, "gradient history"):
            ForwardOnlyMemory(scene, rope)
        for frame in range(3):
            solver.save_ckpt(str(frame))
        self.assertEqual(len(solver._ckpt), 3)


if __name__ == "__main__":
    unittest.main()
