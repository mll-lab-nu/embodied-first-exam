"""Solver backends for the rope tasks: one protocol, PBD and FEM+IPC behind it.

Why this exists: the rope tasks' only genuinely solver-coupled operations are a
short list -- scene options, the rope material, end constraints, node access,
and the tabletop friction shim. Everything else (braid generation, tube
meshing, planners, verifiers) reads centerlines and world coordinates and does
not care which solver moves the vertices. This package holds that short list
behind one object so call sites never branch on the solver, and switching is
one config value: ``rope.model`` = ``pbd_elastic_tube`` | ``fem_ipc_tube``.

The protocol splits end constraints by *when* each backend needs them:

- **declare_* (pre-build)**: FEM constraint capacity must exist before
  ``scene.build()`` (the IPC coupler reads it during build); PBD just buffers
  the selectors.
- **anchor / follow_link (post-build)**: PBD resolves particle indices (needs
  particle positions, which exist only after build) and calls
  ``fix_particles(_to_link)``; FEM verifies its pins resolved and engages the
  follow band, syncing its targets from the link's pose every step.

Selectors are (center, radius) pairs -- the same within-radius-else-nearest
rule as ``rope.endpoint_particle_indices`` -- because FEM vertex indices are
not knowable pre-build (tetgen inserts Steiner points).

Timing contract, in call order:

    backend = rope_backend(task_cfg.rope)
    backend.pre_scene()                       # before gs.Scene(...)
    scene = gs.Scene(..., **backend.scene_options())
    entity = scene.add_entity(morph, material=backend.material(), ...)
    backend.declare_anchor(entity, centers, radius)      # pre-build
    backend.declare_follow(entity, center, radius)       # pre-build, optional
    scene.build()
    backend.anchor(entity)                               # post-build
    backend.follow_link(entity, link)                    # post-build, optional
    indices = backend.resolve_indices(entity, centers, radius)   # bookkeeping
    positions = backend.nodes(entity)                    # any time after build
"""

from __future__ import annotations


def rope_backend(rope_cfg):
    """Instantiate the backend named by ``rope_cfg.model``.

    One instance per scene: backends carry per-scene state (buffered selectors,
    follow-band registrations).
    """

    model = str(rope_cfg.model)
    if model == "pbd_elastic_tube":
        from .pbd import PBDRopeBackend

        return PBDRopeBackend(rope_cfg)
    if model == "fem_ipc_tube":
        from .fem_ipc import FemIpcRopeBackend

        return FemIpcRopeBackend(rope_cfg)
    raise ValueError(
        f"Unsupported rope.model {model!r}; expected 'pbd_elastic_tube' or 'fem_ipc_tube'."
    )
