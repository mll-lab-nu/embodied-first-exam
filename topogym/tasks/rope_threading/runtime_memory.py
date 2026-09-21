"""Bound forward-only Genesis caches without changing native dynamics."""
from importlib.metadata import version


class ForwardOnlyMemory:
    """Reuse checkpoint storage while preserving the original frame rollover.

Genesis 1.2.1 FEMSolver.save_ckpt allocates a new checkpoint at every native
step even when gradients are disabled. Calling the original method with one
stable key preserves both its state copy and copy_frame operations. Only the
unused backward-history storage changes. Returned query states remain valid
for their callers, but are not retained by the unused gradient queue.
"""
    def __init__(self, scene, rope):
        if scene.sim.requires_grad:
            raise ValueError("Forward-only cache policy cannot discard gradient history")
        if version("genesis-world") != "1.2.1":
            raise RuntimeError("Forward-only cache adapter requires a new backend audit")
        self.scene, self.rope = scene, rope
        self.solver = scene.sim.fem_solver
        self.original_save = self.solver.save_ckpt
        self.original_query = rope.get_state
        self.initial_checkpoints = len(self.solver._ckpt)
        self.initial_queries = self._retained_queries()
        self.checkpoint_calls = self.query_calls = 0
        self.key = "rope_threading_forward_only"
        if self.key in self.solver._ckpt:
            raise ValueError("Forward-only cache policy was already installed")
        self.solver.save_ckpt = self.save_checkpoint
        rope.get_state = self.query_state

    def _retained_queries(self):
        return sum(len(states) for states in self.rope._queried_states.states.values())

    def save_checkpoint(self, name):
        result = self.original_save(self.key)
        self.checkpoint_calls += 1
        if len(self.solver._ckpt) > self.initial_checkpoints+1:
            raise RuntimeError("Forward-only FEM checkpoint history is growing")
        return result

    def query_state(self):
        state = self.original_query()
        self.rope._queried_states.discard(state)
        self.query_calls += 1
        return state

    def report(self):
        checks = dict(bounded_checkpoint_history=len(self.solver._ckpt) <= self.initial_checkpoints+1,
            bounded_query_history=self._retained_queries() <= self.initial_queries)
        return dict(passed=all(checks.values()), checks=checks,
            checkpoint_calls=self.checkpoint_calls, query_calls=self.query_calls,
            initial_checkpoints=self.initial_checkpoints, initial_queries=self.initial_queries,
            retained_checkpoints=len(self.solver._ckpt), retained_queries=self._retained_queries(),
            original_frame_rollover_preserved=True, native_state_overwrites=False,
            scope="forward-only cache ownership; no force, state, timestep, or material change")
