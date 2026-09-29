"""Frozen rigid/PBD birth-state codec using destination-owned World handles.

Exact backend/schema/entity/buffer layouts only. IPC, external forces and
cross-device restores are rejected. The existing in-episode restore contract
is unchanged; no source pointers or source world_id enter a new World.
"""
from __future__ import annotations

from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

import numpy as np

from topogym.utils.io import canonical_hash, sha256_file
from topogym.world.initial_state import load_numeric_archive, save_numeric_archive, require_same_layout
from topogym.world.state import BufferState, copy_native_state
from topogym.world.physics.pbd_binding import read_birth_visual_binding


def backend_identity(world):
    import genesis as gs
    root = Path(gs.__file__).parent
    solvers = [type(s).__name__ for s in world.scene.sim._active_solvers]
    if "PBDSolver" not in solvers or set(solvers)-{"RigidSolver", "PBDSolver"}:
        raise ValueError("Frozen initial states support rigid + PBD only")
    if type(world.scene.sim.coupler).__name__ != "LegacyCoupler":
        raise ValueError("Unsupported frozen-state coupler")
    files = ("engine/entities/particle_entity.py", "engine/entities/pbd_entity.py",
             "engine/solvers/pbd_solver.py", "engine/solvers/rigid/rigid_solver.py")
    return dict(codec="rigid_pbd_numeric_v1", genesis=version("genesis-world"),
        precision=np.dtype(gs.np_float).str, backend=str(gs.backend),
        dt_s=world.physics_dt_s, solvers=solvers,
        backend_sources={n: sha256_file(root/n) for n in files},
        state_codec_sha256=sha256_file(Path(__file__).parents[1]/"state.py"),
        world_sha256=sha256_file(Path(__file__).parents[1]/"genesis_world.py"),
        table_friction_sha256=sha256_file(Path(__file__).with_name("pbd_table_friction.py")),
        bindings={name: read_birth_visual_binding(e).sha256 for name, e in world.entities.items()
                  if hasattr(e, "get_particles_pos")})


def native_values(state):
    return [None if s is None else {k: v for k, v in vars(s).items() if k not in ("_scene", "scene")}
            for s in state.native_state.solvers_state]


def export_initial_state(world, folder, *, identity, robot=None, qualification=None):
    state = world.capture_state()
    if state.grasp_state is not None:
        raise ValueError("Initial-state export must precede runtime grasp configuration")
    backend = backend_identity(world)
    if state.ipc_state is not None:
        raise ValueError("IPC is outside this codec")
    robot_state = None if robot is None else robot.capture_state()
    payload = dict(native=native_values(state),
        buffers={b.path: dict(kind=b.kind, value=b.value) for b in state.buffers},
        flags=[(type(owner).__name__, name, value) for owner, name, value in state.engine_flags],
        inputs=[(entity.name, value) for entity, value in state.entity_inputs],
        rng=(state.python_rng, state.numpy_rng, state.torch_rng, state.cuda_rng, state.world_rng),
        physics_step=state.physics_step, scene_tick=state.scene_tick, engine_substep=state.engine_substep,
        robot=None if robot_state is None else dict(robot_id=robot_state.robot_id, targets=robot_state.targets))
    if len(payload["buffers"]) != len(state.buffers):
        raise ValueError("Ambiguous buffer paths cannot be exported")
    return save_numeric_archive(folder, payload, dict(backend=backend, identity=identity,
        identity_sha256=canonical_hash(identity), qualification=qualification or {},
        scope="management_initial_state", includes_robot=robot is not None))


def restore_initial_state(world, manifest, *, identity, robot=None, expected_sha256=None):
    """Restore without a physics step. Caller must discard World on write failure."""
    payload, metadata = load_numeric_archive(manifest, expected_sha256=expected_sha256)
    if metadata["identity_sha256"] != canonical_hash(identity) or metadata["identity"] != identity:
        raise ValueError("Frozen initial-state scene/configuration identity differs")
    if metadata["backend"] != backend_identity(world):
        raise ValueError("Frozen initial-state backend or birth binding differs")
    if metadata["includes_robot"] != (robot is not None):
        raise ValueError("Frozen initial-state robot coverage differs")
    template = world.capture_state()
    if template.grasp_state is not None:
        raise ValueError("Initial-state import must precede runtime grasp configuration")
    target_native = native_values(template)
    require_same_layout(payload["native"], target_native, "native")
    by_path = {b.path: b for b in template.buffers}
    if payload["buffers"].keys() != by_path.keys():
        raise ValueError("Frozen initial-state buffer inventory differs")
    buffers = []
    for path, target in by_path.items():
        saved = payload["buffers"][path]
        if saved["kind"] != target.kind:
            raise ValueError(f"Buffer kind differs: {path}")
        require_same_layout(saved["value"], target.value, path)
        buffers.append(BufferState(target.target, saved["value"], target.kind, path))
    flags = [(type(owner).__name__, name, value) for owner, name, value in template.engine_flags]
    require_same_layout(payload["flags"], flags, "flags")
    if [(a, b) for a, b, _ in payload["flags"]] != [(a, b) for a, b, _ in flags]:
        raise ValueError("Frozen initial-state flag owners differ")
    inputs = [(entity.name, value) for entity, value in template.entity_inputs]
    require_same_layout(payload["inputs"], inputs, "inputs")
    if [n for n, _ in payload["inputs"]] != [n for n, _ in inputs]:
        raise ValueError("Frozen initial-state input owners differ")
    restored_robot = None
    if robot is not None:
        from topogym.robot.joint_position import RobotState
        restored_robot = RobotState(**payload["robot"])
        current = robot.capture_state()
        if restored_robot.robot_id != current.robot_id:
            raise ValueError("Frozen initial-state robot embodiment differs")
        require_same_layout(restored_robot.targets, current.targets, "robot")
        robot.validate_action(restored_robot.targets)
    native = copy_native_state(template.native_state, device="cpu")
    for target, saved in zip(native.solvers_state, payload["native"]):
        if saved is not None:
            for name, value in saved.items():
                setattr(target, name, value)
    rng = payload["rng"]
    require_same_layout(rng, (template.python_rng, template.numpy_rng, template.torch_rng,
                            template.cuda_rng, template.world_rng), "rng")
    for key in ("physics_step", "scene_tick", "engine_substep"):
        if type(payload[key]) is not int or payload[key] < 0:
            raise ValueError("Invalid frozen-state clock")
    restored = replace(template, native_state=native, buffers=tuple(buffers),
        engine_flags=tuple((owner, name, saved[2]) for (owner, name, _), saved in zip(template.engine_flags, payload["flags"])),
        entity_inputs=tuple((entity, saved[1]) for (entity, _), saved in zip(template.entity_inputs, payload["inputs"])),
        python_rng=rng[0], numpy_rng=rng[1], torch_rng=rng[2], cuda_rng=rng[3], world_rng=rng[4],
        physics_step=payload["physics_step"], scene_tick=payload["scene_tick"], engine_substep=payload["engine_substep"])
    # Targets are destination handles obtained above; world_id remains the new
    # world's identity. Normal in-episode restore still rejects foreign states.
    world.restore_state(restored)
    if robot is not None:
        robot.restore_state(restored_robot)
    return dict(manifest_sha256=sha256_file(manifest), identity_sha256=metadata["identity_sha256"],
                source_physics_step=payload["physics_step"], restored_buffers=len(buffers),
                initialization_advance_calls=0, qualification=metadata["qualification"])
