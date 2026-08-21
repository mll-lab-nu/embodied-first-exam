"""Closed elastic band spike: can a figure-8 band hang on a peg, and be flipped flat?

DIAGNOSTIC TOOL, not a production demo. Phase 0 of docx 3.3 (`band_untwist`),
whose one blocker is the closed elastic ring -- see
`docs/develop/tasks/task_environment_buildout_zh.md` section 3. Nothing under
`topogym/tasks/`, `verification/` or `planning/` exists for this task yet, and
none of it gets written until the four readings below come back.

    U1  the periodic sweep is a valid closed tube      tests/check_closed_band_mesh.py
    U2  it loads as FEM+IPC and settles                run.test=settle
    U3  the figure-8 holds instead of springing open   run.test=hold   <- the deciding one
    U4  a flip takes the self-crossing 1 -> 0, and     run.test=flip
        the wrong way round takes it 1 -> 2

**The band spawns as a flat O and is wound into the figure-8 by driving its lower
lobe.** It is not spawned twisted, and that is forced rather than stylistic.
`rest_shape_straight` (`world/genesis_ipc_vertex_constraints.py:130`) builds the
rest rod out of `tube_material_coords`, which reads the spawn in an OPEN Bishop
frame -- so on a closed band it copies the seam closure's twist straight into the
rest. Spawn the 8 and the rest rod comes out pre-twisted by the same amount: the
8 becomes the twist-free state and the flat O the strained one, i.e. exactly
backwards, and the band would spring back to a figure-8 after a successful flip.
Spawning the O costs zero closure twist (its Bishop frame is planar and closes on
its own), so the rest stays untwisted whichever `rope.fem.rest_shape` is picked,
and winding it up in-solver holds the self-linking at 0 by construction -- no
motion can change it. Teaching the rest mapping to take material frames is a
Phase 1 item; it means editing existing files, which a spike does not do.

The wind-up is the inverse of the task's own action, so one driver serves both,
and `run.test=hold` measures what docx 3.3 depends on: whether a band released
after winding stays wound, or springs open with no robot involved.

Standalone scene -- ground plane, wall panel, peg, band. No table preset, no
robot. dt=0.01 / substeps=1, because the stock IPC coupler advances its world
once per substep while configuring it with the whole `sim.dt`
(`ipc_coupler/utils.py:93`). Same shape as `tests/fem_ipc_rope_spike.py`.

    python -m tests.closed_band_spike run.test=mesh
    python -m tests.closed_band_spike run.test=settle run.verbose=true
    python -m tests.closed_band_spike run.test=hold run.viewer=true run.keep_open=true
    python -m tests.closed_band_spike run.test=flip run.flip_side=wrong
    python -m tests.closed_band_spike -m run.test=hold task.rope.fem.E=5e4,1e5,2e5

Requires `pip install pyuipc` (CUDA 12.6+).
"""

from __future__ import annotations

import time

import hydra
import numpy as np
from omegaconf import DictConfig

TESTS = ("mesh", "settle", "hold", "flip")


def require_pyuipc() -> None:
    try:
        import uipc  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "closed_band_spike: python module 'uipc' is missing -- the IPC coupler "
            "cannot run. Install it in this venv with `pip install pyuipc` (needs "
            f"CUDA 12.6+). Original error: {error}"
        )


class LobeTwistDriver:
    """Turn a band of vertices about the vertical axis, and let them rise.

    Winding a hanging loop shortens it, so a pure rotation would stretch the band
    against its own length. The rise is taken from the centerline generator at the
    two ends of the motion and scaled linearly with the turn, which is an
    approximation -- the generator holds the lobe width fixed while a real band
    narrows as it winds. How good it is shows in the tracking error printed each
    sample: a large one means the band is fighting the path.

    Angles are RELATIVE to the shape captured at construction, so the same class
    drives the wind-up from the flat O and the flip from wherever the band ended
    up, without either needing to know the other's absolute angle.
    """

    def __init__(self, handle, axis_xy, positions, *, lift_per_half_turn: float) -> None:
        self.handle = handle
        self.axis = np.asarray(axis_xy, dtype=float)[:2]
        self.captured = np.asarray(positions, dtype=float)[handle.verts].copy()
        self.lift_per_half_turn = float(lift_per_half_turn)
        self.target = self.captured.mean(axis=0)

    def turn_by(self, half_turns: float) -> None:
        angle = float(half_turns) * np.pi
        cos, sin = np.cos(angle), np.sin(angle)
        local = self.captured[:, :2] - self.axis[None, :]
        targets = np.column_stack(
            [
                self.axis[0] + local[:, 0] * cos - local[:, 1] * sin,
                self.axis[1] + local[:, 0] * sin + local[:, 1] * cos,
                self.captured[:, 2] + self.lift_per_half_turn * float(half_turns),
            ]
        )
        self.handle.engage(targets)
        self.target = targets.mean(axis=0)

    def tracking_error(self, positions) -> float:
        current = np.asarray(positions, dtype=float)[self.handle.verts].mean(axis=0)
        return float(np.linalg.norm(current - self.target))


@hydra.main(version_base="1.3", config_path="../configs", config_name="closed_band_spike")
def main(cfg: DictConfig) -> None:
    if str(cfg.run.test) not in TESTS:
        raise SystemExit(f"closed_band_spike: run.test must be one of {TESTS}.")
    if str(cfg.run.test) != "mesh":
        require_pyuipc()  # run.test=mesh touches no solver, so it runs without CUDA

    import genesis as gs

    from topogym.core import save_resolved_config
    from topogym.supervision import stop_before_physics
    from topogym.world import materials
    from topogym.world.closed_band import (
        WALL_PROJECTION,
        band_self_crossings,
        closed_arc_length,
        closed_transport_frames,
        closed_tube_mesh,
        hanging_band_centerline,
    )
    from topogym.world.genesis_ipc_vertex_constraints import follow_near, resolved_pins
    from topogym.world.rope import (
        check_self_contact_clearance,
        resolve_mesh_dir,
        tensor_to_numpy,
        tube_material_coords,
        tube_morph,
        write_obj,
    )
    from topogym.world.rope_backends import rope_backend

    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"closed_band_spike_config -> {resolved}", flush=True)

    band, rope = cfg.run.band, cfg.task.rope
    fem = rope.fem
    radius = float(rope.radius)
    segment_length = float(rope.mesh.segment_length)
    radial = int(rope.mesh.radial_segments)
    merge_radius = float(band.crossing_merge_radius)
    peg_center = np.asarray([float(value) for value in band.peg_center], dtype=float)
    wound_turns = float(band.half_turns)
    if abs(wound_turns) < 0.1:
        raise SystemExit(
            f"closed_band_spike: run.band.half_turns={wound_turns} leaves nothing to wind. "
            "docx 3.3 is +1 or -1 half turn."
        )

    def centerline_at(half_turns: float) -> np.ndarray:
        return hanging_band_centerline(
            perimeter=float(band.perimeter),
            loop_radius=float(band.loop_radius),
            peg_center=peg_center,
            half_turns=half_turns,
            segment_length=segment_length,
        )

    def crossings_of(line: np.ndarray):
        return band_self_crossings(
            line, projection=WALL_PROJECTION, merge_radius=merge_radius
        )

    # --- geometry (no solver) -------------------------------------------------
    spawn_line = centerline_at(0.0)  # flat; the twist is applied by the solver
    frames = closed_transport_frames(spawn_line, tube_radius=radius, self_linking_target=0)
    vertices, faces = closed_tube_mesh(spawn_line, frames, radius=radius, radial_segments=radial)
    check_self_contact_clearance(
        radius=radius,
        radial_segments=radial,
        ring_spacing=segment_length,
        contact_d_hat=float(fem.contact_d_hat),
    )
    mesh_path = resolve_mesh_dir(rope.mesh.output_dir) / "closed_band.obj"
    write_obj(mesh_path, vertices, faces)

    wound_line = centerline_at(wound_turns)
    lift_per_half_turn = float(
        (wound_line[:, 2].min() - spawn_line[:, 2].min()) / wound_turns
    )
    print(
        f"closed_band_spike band: perimeter {frames.perimeter:.4f} m, "
        f"Lk {frames.self_linking} at Tw {frames.twist_turns:+.4f} turns, "
        f"{len(spawn_line)} rings x {radial}, skin {len(vertices)} verts -> {mesh_path}"
    )
    print(
        f"closed_band_spike flat O hangs to z {spawn_line[:, 2].min() * 1000:.1f} mm and reads "
        f"{len(crossings_of(spawn_line))} self-crossings; the generator puts "
        f"{wound_turns:+.1f} half turns at z {wound_line[:, 2].min() * 1000:.1f} mm "
        f"({len(crossings_of(wound_line))} crossings, lift "
        f"{lift_per_half_turn * wound_turns * 1000:+.1f} mm)"
    )
    if str(cfg.run.test) == "mesh":
        print("closed_band_spike mesh: tests/check_closed_band_mesh.py has the full skin gate.")
        return

    # --- scene ----------------------------------------------------------------
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[cfg.env.genesis.backend])

    backend = rope_backend(rope)
    backend.pre_scene()

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=float(cfg.run.dt), substeps=1, gravity=(0.0, 0.0, -9.81)
        ),
        viewer_options=gs.options.ViewerOptions(
            camera_pos=(-0.55, -0.30, 0.32),
            camera_lookat=(float(peg_center[0]), 0.0, float(peg_center[2]) - 0.05),
            camera_fov=45,
        ),
        show_viewer=cfg.run.viewer,
        **backend.scene_options(),
    )

    # `static_rigid_material` is 'ipc_only', which the plane also needs: a Plane
    # carries a base joint, so the coupler's auto-select picks
    # 'external_articulation' and its own plane handler then rejects it.
    static = backend.static_rigid_material()
    scene.add_entity(gs.morphs.Plane(), material=static, name="ground")
    scene.add_entity(
        gs.morphs.Box(
            pos=(float(band.panel_x), 0.0, 0.5 * float(band.panel_top_z)),
            size=(float(band.panel_thickness), float(band.panel_width), float(band.panel_top_z)),
            fixed=True,
        ),
        material=static,
        surface=materials.plastic("fixture", (0.62, 0.64, 0.67)),
        name="panel",
    )
    scene.add_entity(
        gs.morphs.Cylinder(
            pos=(float(band.panel_x) - 0.5 * float(band.peg_length), 0.0, float(peg_center[2])),
            radius=float(band.peg_radius),
            height=float(band.peg_length),
            euler=(0.0, 90.0, 0.0),  # default-Z cylinder axis -> world X (the panel normal)
            fixed=True,
        ),
        material=static,
        surface=materials.plastic("fixture", (0.95, 0.55, 0.10)),
        name="peg",
    )
    entity = scene.add_entity(
        tube_morph(mesh_path, rope),
        material=backend.material(),
        surface=materials.plastic("deformable", (0.20, 0.62, 0.32), vis_mode="visual"),
        name="band",
    )

    if str(fem.rest_shape) == "straight":
        backend.declare_rest_straight(entity, spawn_line)
    if bool(cfg.run.pin_top):
        backend.declare_anchor(
            entity,
            [peg_center + np.array([0.0, 0.0, float(band.loop_radius)])],
            float(band.loop_radius),
        )
    lobe = follow_near(
        entity,
        spawn_line[int(np.argmin(spawn_line[:, 2]))],
        float(cfg.run.band_radius),
        strength=float(fem.follow_strength),
    )

    scene.build()
    print(f"closed_band_spike band: {entity.n_vertices} FEM vertices, {entity.n_elements} tets")
    if stop_before_physics(cfg, scene, "closed_band_spike"):
        raise SystemExit(0)

    # --- centerline read-back -------------------------------------------------
    def positions() -> np.ndarray:
        pos = tensor_to_numpy(entity.get_state().pos)
        return pos[0] if pos.ndim == 3 else pos

    spawn_positions = positions()
    # Arc length per tet vertex, measured once on the spawn shape: tetgen does not
    # preserve order, so this is what recovers an ordered centerline afterwards.
    # Same device as untangle_continuous' `particle_arclength`, wrapped for a loop.
    arclength = np.mod(tube_material_coords(spawn_positions, spawn_line)[:, 0], frames.perimeter)
    bins = len(spawn_line)
    bin_index = np.clip((arclength / frames.perimeter * bins).astype(int), 0, bins - 1)
    members = [np.flatnonzero(bin_index == index) for index in range(bins)]
    empty = sum(1 for group in members if len(group) == 0)
    if empty:
        raise SystemExit(
            f"closed_band_spike: {empty} of {bins} arc-length bins are empty, so the "
            "centerline cannot be read back. Coarsen the bins or refine the tet mesh."
        )

    def read_centerline() -> np.ndarray:
        pos = positions()
        return np.asarray([pos[group].mean(axis=0) for group in members], dtype=float)

    def report(label: str, step: int, driver=None) -> None:
        line = read_centerline()
        hits = crossings_of(line)
        text = (
            f"closed_band_spike {label} step={step} crossings={len(hits)} "
            f"depth_gaps={[f'{hit.gap * 1000:.1f}' for hit in hits]}mm "
            f"bottom_z={line[:, 2].min() * 1000:.1f}mm"
        )
        if driver is not None:
            text += f" lobe_err={driver.tracking_error(positions()) * 1000:.2f}mm"
        print(text, flush=True)

    def run_steps(count: int, label: str, *, every: int = 25, driver=None, turn=None) -> None:
        started = time.perf_counter()
        for step in range(1, count + 1):
            if turn is not None:
                turn(step / count)
            scene.step()
            if step % every == 0 or step == count:
                report(label, step, driver)
        elapsed = max(time.perf_counter() - started, 1e-6)
        print(
            f"closed_band_spike {label}: {count} steps in {elapsed:.1f}s "
            f"({count / elapsed:.1f} steps/s)"
        )

    # --- settle ---------------------------------------------------------------
    previous = spawn_positions
    check_every = 10
    converged_at = None
    started = time.perf_counter()
    for step in range(1, int(cfg.run.settle_steps) + 1):
        scene.step()
        if step % check_every == 0:
            current = positions()
            moved = float(np.linalg.norm(current - previous, axis=1).max()) / check_every
            previous = current
            if cfg.run.verbose:
                print(f"closed_band_spike settle step={step} max_move={moved * 1000:.4f}mm/step")
            if moved < float(cfg.run.settle_tol):
                converged_at = step
                break
    settled = read_centerline()
    print(
        f"closed_band_spike settle: {time.perf_counter() - started:.1f}s, "
        + (f"converged at step {converged_at}" if converged_at else "NOT converged")
    )
    print(
        f"closed_band_spike settled O: crossings={len(crossings_of(settled))} (want 0), "
        f"z range [{settled[:, 2].min() * 1000:.1f}, {settled[:, 2].max() * 1000:.1f}]mm, "
        f"arc length {closed_arc_length(settled)[1] * 1000:.1f}mm "
        f"(spawn {frames.perimeter * 1000:.1f}mm), peg top at "
        f"{(peg_center[2] + float(band.peg_radius)) * 1000:.1f}mm"
    )
    if bool(cfg.run.pin_top):
        pins = resolved_pins(entity)
        print(f"closed_band_spike pinned {0 if pins is None else len(pins)} verts at the peg")

    def hold_viewer() -> None:
        if cfg.run.keep_open or cfg.run.viewer:
            print("closed_band_spike holding the viewer open; Ctrl+C to exit.")
            while True:
                scene.step()

    if str(cfg.run.test) == "settle":
        hold_viewer()
        return

    # --- wind the flat O up into the figure-8 ---------------------------------
    driver = LobeTwistDriver(
        lobe, peg_center, positions(), lift_per_half_turn=lift_per_half_turn
    )
    run_steps(
        int(cfg.run.drive_steps),
        f"wind->{wound_turns:+.1f}",
        driver=driver,
        turn=lambda alpha: driver.turn_by(wound_turns * alpha),
    )
    lobe.release()
    run_steps(int(cfg.run.flip_settle_steps), "release")
    wound = crossings_of(read_centerline())
    print(
        f"closed_band_spike wind verdict: {len(wound)} self-crossings just after release "
        f"(want 1), signs {[hit.sign for hit in wound]} -- "
        + (
            "PASS"
            if len(wound) == 1
            else "FAIL -- the wind-up did not produce a figure-8, so the hold and flip "
            "readings below say nothing about docx 3.3"
        )
    )

    # --- hold (U3) ------------------------------------------------------------
    before = read_centerline()
    run_steps(int(cfg.run.hold_steps), "hold", every=int(cfg.run.hold_sample_every))
    after_line = read_centerline()
    after = crossings_of(after_line)
    print(
        f"closed_band_spike hold verdict: crossings {len(wound)} -> {len(after)} over "
        f"{int(cfg.run.hold_steps)} steps, bottom_z {before[:, 2].min() * 1000:.1f} -> "
        f"{after_line[:, 2].min() * 1000:.1f} mm -- "
        + (
            "PASS -- the released figure-8 held"
            if len(after) == 1
            else f"FAIL -- a released figure-8 must stay at 1 crossing, read {len(after)}"
        )
    )
    if str(cfg.run.test) == "hold":
        hold_viewer()
        return

    # --- flip (U4) ------------------------------------------------------------
    correct = str(cfg.run.flip_side) == "correct"
    delta = -wound_turns if correct else wound_turns
    expected = 0 if correct else 2
    driver = LobeTwistDriver(
        lobe, peg_center, positions(), lift_per_half_turn=lift_per_half_turn
    )
    run_steps(
        int(cfg.run.drive_steps),
        f"flip:{cfg.run.flip_side}",
        driver=driver,
        turn=lambda alpha: driver.turn_by(delta * alpha),
    )
    lobe.release()
    run_steps(int(cfg.run.flip_settle_steps), "flip_settle")

    final_line = read_centerline()
    final = crossings_of(final_line)
    print(
        f"closed_band_spike flip verdict ({cfg.run.flip_side}): crossings {len(after)} -> "
        f"{len(final)} (want {expected}), bottom_z {final_line[:, 2].min() * 1000:.1f}mm, "
        f"arc length {closed_arc_length(final_line)[1] * 1000:.1f}mm -- "
        + ("PASS" if len(final) == expected else "FAIL")
    )
    hold_viewer()


if __name__ == "__main__":
    main()
