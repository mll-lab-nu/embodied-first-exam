"""Reset to an explicitly selected recorded shape before any execution steps.

This starts a fresh experiment with zero cloth velocity; it is not a claimed
continuation of the old dynamics. Flat material rest lengths and visual support
indices are preserved, and all later cloth motion comes from the solver.
"""
import hashlib
from pathlib import Path
import numpy as np


def restore_selected_shape(task, cfg, output):
    source = Path(cfg.path).resolve()
    trace = np.load(source)
    for name, actual in [('faces', task.faces), ('supports', task.supports)]:
        if not np.array_equal(trace[name], actual):
            raise ValueError(f'Selected initial shape has different {name}')
    for name, actual in [('material_uv', task.material_uv), ('weights', task.weights)]:
        if trace[name].shape != actual.shape or not np.allclose(trace[name], actual, atol=1e-7, rtol=0):
            raise ValueError(f'Selected initial shape has different {name}')
    states = trace['positions']
    frame = int(cfg.get('frame', -1))
    if states.ndim == 3:
        if not -len(states) <= frame < len(states):
            raise ValueError('Selected frame is outside the source recording')
        frame %= len(states)
        positions = states[frame].astype(float)
    else:
        positions = states.astype(float)
        frame = 0
    if positions.shape != (task.cloth.n_particles, 3) or not np.isfinite(positions).all():
        raise ValueError('Invalid selected particle coordinates')
    rest = task.cloth._edges_len_rest.copy()
    task.cloth.set_particles_pos(positions)
    task.cloth.set_particles_vel(0.)
    if not np.array_equal(rest, task.cloth._edges_len_rest):
        raise RuntimeError('Initial reset changed material rest lengths')
    np.savez_compressed(Path(output)/'selected_initial_state.npz', positions=positions,
        velocities=np.zeros_like(positions), faces=task.faces, material_uv=task.material_uv,
        supports=task.supports, weights=task.weights)
    return dict(source=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        source_frame=frame, classification='fresh_physics_from_recorded_shape_with_zero_velocity',
        initialization_position_writes=1, live_position_writes=0, rest_lengths_unchanged=True,
        material_mapping_and_binding_verified=True, initial_velocity='zero',
        dynamics_continuation_of_source=False)
