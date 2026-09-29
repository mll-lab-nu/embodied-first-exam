"""Future real-physics checks; authored during a no-test-execution refactor.

Requires the audited Genesis 1.2.1 runtime. CPU is the default; CUDA must be
selected explicitly using TOPOGYM_TEST_DEVICE=cuda and is a separate result.
The tolerances below are same-device continuation tolerances, not a promise of
bit-identical CPU/GPU trajectories. No rendering or robot assets are needed.
"""
import os
import random

import numpy as np
import pytest


pytestmark = [pytest.mark.genesis, pytest.mark.rigid]


@pytest.fixture
def falling_box_world():
    import genesis as gs
    import torch
    from topogym.world import GenesisWorld

    device = os.environ.get("TOPOGYM_TEST_DEVICE", "cpu")
    if device not in {"cpu", "cuda"}:
        raise ValueError("TOPOGYM_TEST_DEVICE must be cpu or cuda")
    if device == "cuda" and not torch.cuda.is_available():
        pytest.fail("Requested CUDA validation was not performed: CUDA is unavailable")
    if not getattr(gs, "_initialized", False):
        gs.init(backend=getattr(gs, device), precision="64", seed=17, logging_level="warning")
    assert gs.backend == getattr(gs, device), "Run each device in a separate process"
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=.005, substeps=4, gravity=(0, 0, -9.81)),
                     show_viewer=False)
    plane = scene.add_entity(gs.morphs.Plane(), material=gs.materials.Rigid(friction=.5))
    box = scene.add_entity(gs.morphs.Box(size=(.1, .1, .1), pos=(0, 0, 1.)),
                           material=gs.materials.Rigid(rho=1000., friction=.5))
    world = GenesisWorld(scene, entities={"plane": plane, "box": box}, seed=17)
    try:
        world.build()
        yield world
    finally:
        world.close()


def _box_state(world):
    body = world.read_state()["bodies"]["box"]
    return np.r_[body["position_m"], body["quaternion_wxyz"],
                 body["linear_velocity_m_s"], body["angular_velocity_rad_s"]]


def test_gravity_contact_and_arbitrary_saved_state_continuation(falling_box_world):
    world = falling_box_world
    states, trajectory = {}, {0: _box_state(world)}
    for tick in range(1, 151):
        world.advance()
        trajectory[tick] = _box_state(world)
        if tick in {27, 110, 132}:
            states[tick] = world.capture_state()
    assert trajectory[27][2] < trajectory[0][2] - .05
    assert trajectory[27][9] < -.5  # z linear velocity: gravity is actually active.
    assert .04 <= trajectory[150][2] <= .065, "Box must rest on the physical plane"
    contacts = world.read_state()["contacts"]
    assert len(contacts["link_a"]) > 0, "Resting support requires actual contacts"
    assert np.linalg.norm(contacts["force"], axis=-1).max(initial=0.) > 0.
    tolerance = 2e-8 if os.environ.get("TOPOGYM_TEST_DEVICE", "cpu") == "cpu" else 2e-5
    # Restore out of order, including a contact state and a free-flight state.
    # Old states must survive a rewind and subsequent branch execution.
    for tick in (132, 27, 110, 27):
        world.restore_state(states[tick])
        assert world.physics_step == tick
        assert world.sim_time_s == pytest.approx(tick * world.physics_dt_s)
        np.testing.assert_allclose(_box_state(world), trajectory[tick], rtol=0., atol=tolerance)
        for next_tick in range(tick + 1, tick + 9):
            world.advance()
            np.testing.assert_allclose(_box_state(world), trajectory[next_tick], rtol=0., atol=tolerance)


def test_read_capture_and_reset_clock_do_not_integrate(falling_box_world):
    world = falling_box_world
    for _ in range(7):
        world.advance()
    before, native_tick = _box_state(world), world.scene.t
    checkpoint = world.capture_state()
    first = world.read_state()
    first["bodies"]["box"]["position_m"][:] = 999.
    world.read_state()
    np.testing.assert_array_equal(_box_state(world), before)
    assert world.physics_step == 7 and world.scene.t == native_tick
    world.reset_clock()
    assert world.physics_step == 0 and world.scene.t == native_tick
    np.testing.assert_array_equal(_box_state(world), before)
    world.restore_state(checkpoint)
    assert world.physics_step == 7 and world.scene.t == native_tick


def test_checkpoint_restores_all_supported_random_streams(falling_box_world):
    import torch

    world = falling_box_world
    checkpoint = world.capture_state()

    def samples():
        values = [random.random(), float(np.random.random()), float(torch.rand(())),
                  float(world.rng.random())]
        if torch.cuda.is_initialized():
            values.append(float(torch.rand((), device="cuda")))
        return values

    expected = samples()
    samples()
    world.restore_state(checkpoint)
    assert samples() == expected


def test_spatial_hasher_buffers_are_captured_and_restored(falling_box_world, monkeypatch):
    from genesis.utils.geom import SpatialHasher

    world = falling_box_world
    # Exercise the real Genesis helper without needing external cloth assets.
    # In a PBD scene the solver exposes this exact class at its `sh` attribute.
    hasher = SpatialHasher(cell_size=.1, grid_res=(2, 2, 2))
    hasher.build(n_batch=1)
    monkeypatch.setattr(world.scene.sim.rigid_solver, "_checkpoint_spatial_hasher", hasher, raising=False)
    fields = (hasher.slot_size, hasher.slot_start, hasher.cur_cnt)
    for index, field in enumerate(fields):
        field.fill(index + 1)
    checkpoint = world.capture_state()
    captured = {id(item.target) for item in checkpoint.buffers}
    assert all(id(field) in captured for field in fields)
    for field in fields:
        field.fill(99)
    world.restore_state(checkpoint)
    for index, field in enumerate(fields):
        np.testing.assert_array_equal(field.to_numpy(), index + 1)


def test_foreign_world_state_rejected_and_close_idempotent(falling_box_world):
    from dataclasses import replace

    world = falling_box_world
    state = world.capture_state()
    with pytest.raises(ValueError, match="another built world"):
        world.restore_state(replace(state, world_id="another-world"))
    world.close()
    world.close()
    with pytest.raises(RuntimeError, match="closed"):
        world.advance()


def test_incomplete_checkpoint_capability_is_rejected(monkeypatch):
    from types import SimpleNamespace
    from topogym.world import GenesisWorld
    import topogym.world.genesis_world as implementation

    monkeypatch.setattr(implementation, "version", lambda _: "1.2.1")
    rigid = type("RigidSolver", (), {})()
    ipc = type("IPCCoupler", (), {})()
    scene = SimpleNamespace(dt=.005, requires_grad=False, n_envs=0, _emitters=[],
                            sim=SimpleNamespace(_active_solvers=[rigid], coupler=ipc))
    world = GenesisWorld(scene)
    with pytest.raises(NotImplementedError, match="coupler"):
        world._check_checkpoint_support()
