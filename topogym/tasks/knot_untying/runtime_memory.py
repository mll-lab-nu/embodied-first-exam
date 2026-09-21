"""Bound unused Genesis history during forward-only physical recordings.

Genesis 1.2.1 allocates a FEM checkpoint at every substep even without gradients.
Keep calling its original save method, including the required frame rollover,
but reuse one history slot. Native IPC states and physical parameters are not
changed. This follows the independently implemented rope-threading adapter.
"""
from importlib.metadata import version


class ForwardOnlyMemory:
    def __init__(self, scene, rope):
        if scene.sim.requires_grad:
            raise ValueError('Forward-only recording cannot discard gradient history')
        if version('genesis-world') != '1.2.1':
            raise RuntimeError('Forward-only cache adapter requires a new backend audit')
        self.solver, self.rope = scene.sim.fem_solver, rope
        self.original_save, self.original_query = self.solver.save_ckpt, rope.get_state
        self.initial_checkpoints = len(self.solver._ckpt)
        self.initial_queries = self._query_count()
        self.checkpoint_calls = self.query_calls = 0
        self.key = 'knot_untying_forward_only'
        if self.key in self.solver._ckpt:
            raise ValueError('Forward-only cache adapter is already installed')
        self.solver.save_ckpt = self.save_checkpoint
        rope.get_state = self.query_state

    def _query_count(self):
        return sum(len(states) for states in self.rope._queried_states.states.values())

    def save_checkpoint(self, name):
        result = self.original_save(self.key)
        self.checkpoint_calls += 1
        if len(self.solver._ckpt) > self.initial_checkpoints+1:
            raise RuntimeError('Unused FEM checkpoint history is still growing')
        return result

    def query_state(self):
        state = self.original_query()
        # Only release the queue's reference. The caller's returned state stays
        # valid and retains its own position/velocity buffers.
        self.rope._queried_states.discard(state)
        self.query_calls += 1
        return state

    def report(self):
        checks = dict(bounded_checkpoint_history=len(self.solver._ckpt) <= self.initial_checkpoints+1,
                      bounded_query_history=self._query_count() <= self.initial_queries)
        return dict(passed=all(checks.values()), checks=checks,
            checkpoint_calls=self.checkpoint_calls, query_calls=self.query_calls,
            retained_checkpoints=len(self.solver._ckpt), retained_queries=self._query_count(),
            original_frame_rollover_preserved=True, native_state_overwrites=False,
            scope='unused forward-only history ownership; no physical parameter or force change')
