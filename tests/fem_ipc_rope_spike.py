"""FEM + IPC rope spike: can Genesis' IPC coupler hold two braided ropes apart?

DIAGNOSTIC TOOL, not a production demo. Kept for backend debugging (its
micro-tests isolate constraint layers the full task cannot); the production
path is the physical-handle / pinch demos, which run FEM by default since
2026-08-08.

Step 1 of the FEM+IPC vertical slice (docs/develop/physics/rope_backend_migration_zh.md).
Standalone scene -- a ground plane and the seed-0 braid's ropes as FEM entities
under the IPC coupler. No table preset, no robot, no changes to any existing
file. The braid geometry, tube meshing, and material knobs all come from the
same config + generator chain the PBD task uses, so the numbers printed here
compare directly against the PBD baseline (rest crossing gap 8.7mm, correct
value 12mm).

The scene runs dt=0.01 / substeps=1: the stock IPC coupler advances its world
once per *substep* but configures it with the full `sim.dt`
(ipc_coupler/utils.py:93), i.e. it is built for substeps=1. The locked
tabletop preset (substeps=4) is deliberately not used here.

Configuration is Hydra (`configs/fem_ipc_rope_spike.yaml`). The material knobs
that used to be CLI-only now live in `task.rope.fem`, single-sourced from
`prefabs.rope_fem` -- which is where this script's own calibration output landed.

    python -m tests.fem_ipc_rope_spike run.seed=0 run.verbose=true
    python -m tests.fem_ipc_rope_spike run.viewer=true run.keep_open=true
    python -m tests.fem_ipc_rope_spike task.rope.fem.E=2e5 task.rope.fem.contact_d_hat=0.001
    python -m tests.fem_ipc_rope_spike run.test=contact run.verbose=true
    python -m tests.fem_ipc_rope_spike -m task.rope.fem.E=1e5,2e5,4e5   # sweep

Requires `pip install pyuipc` (CUDA 12.6+). The import is checked up front so a
missing wheel fails with one clear line instead of a stack trace mid-build.
"""

from __future__ import annotations

import time

import hydra
import numpy as np
from omegaconf import DictConfig


def require_pyuipc() -> None:
    try:
        import uipc  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "fem_ipc_rope_spike: python module 'uipc' is missing -- the IPC "
            "coupler cannot run. Install it in this venv with `pip install "
            f"pyuipc` (needs CUDA 12.6+). Original error: {error}"
        )


def binned_centerline(vertices: np.ndarray, *, bin_size: float = 0.005) -> np.ndarray:
    """Crude centerline: bin surface+interior vertices by x, centroid per bin.

    Good enough for a rest-state gap measurement on lane-aligned braid ropes
    (they run mostly along x). Not valid once a rope is lifted into an arc --
    the step-3 demo replaces this with a proper adapter.
    """

    order = np.argsort(vertices[:, 0])
    verts = vertices[order]
    bins = np.floor(verts[:, 0] / bin_size).astype(int)
    samples = [verts[bins == b].mean(axis=0) for b in np.unique(bins)]
    return np.asarray(samples, dtype=float)


def pairwise_gap(line_a: np.ndarray, line_b: np.ndarray) -> tuple[float, float]:
    """(min centerline distance, signed z of a over b at the closest point)."""

    diff = line_a[:, None, :] - line_b[None, :, :]
    dist = np.linalg.norm(diff, axis=2)
    ia, ib = np.unravel_index(int(np.argmin(dist)), dist.shape)
    return float(dist[ia, ib]), float(line_a[ia, 2] - line_b[ib, 2])


@hydra.main(version_base="1.3", config_path="../configs", config_name="fem_ipc_rope_spike")
def main(cfg: DictConfig) -> None:
    require_pyuipc()

    import genesis as gs

    from topogym.core import save_resolved_config
    from topogym.generation.braid import verify_braid_spec
    from topogym.supervision import stop_before_physics
    from topogym.tasks import UntangleContinuousLayout
    from topogym.world import materials
    from topogym.world.rope import tensor_to_numpy, tube_morph, write_obj

    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"fem_ipc_spike_config -> {resolved}", flush=True)
    fem = cfg.task.rope.fem

    # task frame with origin (0,0,0): braid.base_z=0.007 puts the ropes just above
    # z=0, so a ground plane through the origin plays the tabletop's role.
    layout = UntangleContinuousLayout(cfg.task, seed=cfg.run.seed)
    braid = layout.braid_spec()
    workspace = cfg.common.manipulation_space.workspace
    report = verify_braid_spec(
        braid,
        rope_radius=float(cfg.task.rope.radius),
        particle_size=float(cfg.task.rope.particle_size),
        x_bounds=(float(workspace.x[0]), float(workspace.x[1])),
        y_bounds=(float(workspace.y[0]), float(workspace.y[1])),
    )
    print(
        f"fem_ipc_spike seed={cfg.run.seed} word={braid.word} "
        f"over_under={[(c.over_strand, c.under_strand) for c in braid.crossings]} {report}"
    )
    if not report.ok:
        raise SystemExit("fem_ipc_spike: braid self-check FAILED")

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[cfg.env.genesis.backend])

    if cfg.run.test != "settle":
        # Must run before gs.Scene(): the simulator constructs its coupler there,
        # and the patch swaps which coupler class it constructs.
        from topogym.primitives.fem_attachment import FEMRopeAttachment
        from topogym.world.genesis_ipc_vertex_constraints import (
            install,
            pin_near,
            resolved_pins,
        )

        install()

    coupler_kwargs = {"contact_d_hat": float(fem.contact_d_hat)}
    if cfg.run.contact_resistance is not None:
        coupler_kwargs["contact_resistance"] = float(cfg.run.contact_resistance)
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=float(cfg.run.dt),
            substeps=1,
            gravity=(0.0, 0.0, -9.81),
        ),
        coupler_options=gs.options.IPCCouplerOptions(**coupler_kwargs),
        fem_options=gs.options.FEMOptions(),
        viewer_options=gs.options.ViewerOptions(
            camera_pos=(0.55, -0.55, 0.45),
            camera_lookat=(0.0, 0.0, 0.03),
            camera_fov=45,
        ),
        show_viewer=cfg.run.viewer,
    )

    # coup_type must be explicit: a Plane entity carries a base joint, so the IPC
    # coupler's auto-select picks 'external_articulation' -- which its own plane
    # handler then rejects (only 'ipc_only' is supported for plane geoms).
    scene.add_entity(
        gs.morphs.Plane(),
        material=gs.materials.Rigid(coup_type="ipc_only"),
        name="ground",
    )

    rope_material = gs.materials.FEM.Elastic(
        model="stable_neohookean",
        E=float(fem.E),
        nu=float(fem.nu),
        rho=float(fem.rho),
        friction_mu=float(fem.friction_mu),
    )
    rope_entities = []
    rope_meshes = []
    for strand_index in range(layout.n_strands):
        mesh = layout.rope_mesh(strand_index, braid.control_points[strand_index])
        write_obj(mesh.path, mesh.vertices, mesh.faces)
        entity = scene.add_entity(
            tube_morph(mesh.path, cfg.task.rope),
            material=rope_material,
            surface=materials.plastic(
                "deformable", layout.strand_color(strand_index), vis_mode="visual"
            ),
            name=layout.strand_name(strand_index),
        )
        rope_entities.append(entity)
        rope_meshes.append(mesh)
        if cfg.run.verbose:
            print(
                f"fem_ipc_spike {layout.strand_name(strand_index)}: "
                f"surface_mesh {len(mesh.vertices)} verts, "
                f"centerline {len(mesh.centerline)} samples"
            )

    # Constraint capacity is declared pre-build; the patched coupler resolves the
    # selectors against the tet-mesh vertices during scene.build().
    attachment = None
    grasp_strand = None
    if cfg.run.test != "settle":
        anchor_radius = float(cfg.task.rope.anchor_radius)
        for entity, mesh in zip(rope_entities, rope_meshes):
            pin_near(entity, [mesh.endpoint_centers[0]], anchor_radius)
        if cfg.run.test in ("follow", "contact"):
            if cfg.run.test == "contact":
                if layout.n_strands < 2:
                    raise SystemExit("fem_ipc_spike: contact test needs >= 2 strands.")
                # The PBD-losing configuration: grasp the strand the other one
                # rests on. Lifting it must not tunnel it through.
                grasp_strand = int(braid.crossings[0].under_strand)
            else:
                grasp_strand = 0
            attachment = FEMRopeAttachment(
                rope_entities[grasp_strand],
                rope_meshes[grasp_strand].endpoint_centers[1],
                float(cfg.run.band_radius),
                strength=float(fem.follow_strength),
            )
            print(
                f"fem_ipc_spike test={cfg.run.test}: will grasp s{grasp_strand} "
                f"free end at {np.round(rope_meshes[grasp_strand].endpoint_centers[1] * 1000, 1).tolist()}mm"
            )

    scene.build()
    for entity in rope_entities:
        print(
            f"fem_ipc_spike {entity.name}: {entity.n_vertices} FEM vertices, "
            f"{entity.n_elements} tets"
        )

    # 与 demo 用同一支度量。本脚本是最小对照场景：没有桌子、没有机械臂、
    # 没有 connector latch，且 substeps=1，用来判断每次 IPC advance 的
    # 固定开销来自场景内容还是来自 libuipc/环境本身。
    if stop_before_physics(cfg, scene, "fem_ipc_spike"):
        raise SystemExit(0)

    def positions(entity) -> np.ndarray:
        pos = tensor_to_numpy(entity.get_state().pos)
        return pos[0] if pos.ndim == 3 else pos

    spawn_positions = [positions(entity) for entity in rope_entities]

    # --- settle ---------------------------------------------------------------
    previous = [positions(entity) for entity in rope_entities]
    started = time.perf_counter()
    steps_run = 0
    check_every = 10
    converged_at = None
    for step in range(1, cfg.run.settle_steps + 1):
        scene.step()
        steps_run = step
        if step % check_every == 0:
            current = [positions(entity) for entity in rope_entities]
            moved = max(
                float(np.linalg.norm(cur - prev, axis=1).max())
                for cur, prev in zip(current, previous)
            ) / check_every
            previous = current
            if cfg.run.verbose:
                print(f"fem_ipc_spike settle step={step} max_move={moved * 1000:.4f}mm/step")
            if moved < cfg.run.settle_tol:
                converged_at = step
                break
    elapsed = time.perf_counter() - started
    print(
        f"fem_ipc_spike settle: {steps_run} steps in {elapsed:.1f}s "
        f"({steps_run / elapsed:.1f} steps/s), "
        + (f"converged at step {converged_at}" if converged_at else "NOT converged")
    )

    # --- measurements ---------------------------------------------------------
    all_pos = [positions(entity) for entity in rope_entities]
    radius = float(cfg.task.rope.radius)
    lines = [binned_centerline(pos) for pos in all_pos]
    for a in range(len(lines)):
        for b in range(a + 1, len(lines)):
            gap, over_z = pairwise_gap(lines[a], lines[b])
            surface_gap = gap - 2.0 * radius
            print(
                f"fem_ipc_spike s{a}~s{b}: centreline_gap={gap * 1000:.2f}mm "
                f"(surfaces {'+' if surface_gap >= 0 else ''}{surface_gap * 1000:.2f}mm apart; "
                f"PBD baseline 8.7mm centreline, target >= {2 * radius * 1000 + fem.contact_d_hat * 1000:.0f}mm) "
                f"s{a} over_z={over_z * 1000:+.2f}mm"
            )
            min_vertex = float(
                np.min(
                    np.linalg.norm(
                        all_pos[a][:, None, :] - all_pos[b][None, :, :], axis=2
                    )
                )
            )
            print(f"fem_ipc_spike s{a}~s{b}: min inter-vertex distance {min_vertex * 1000:.2f}mm")
    for index, pos in enumerate(all_pos):
        print(
            f"fem_ipc_spike s{index}: z range [{pos[:, 2].min() * 1000:.2f}, "
            f"{pos[:, 2].max() * 1000:.2f}]mm (resting centreline should sit ~{radius * 1000:.0f}mm)"
        )

    # --- constraint tests -----------------------------------------------------
    if cfg.run.test != "settle":
        for index, (entity, spawn) in enumerate(zip(rope_entities, spawn_positions)):
            pins = resolved_pins(entity)
            if pins is None or len(pins) == 0:
                print(f"fem_ipc_spike anchor s{index}: FAIL no pinned vertices resolved")
                continue
            drift = np.linalg.norm(positions(entity)[pins] - spawn[pins], axis=1)
            verdict = "PASS" if float(drift.max()) < 1e-3 else "FAIL"
            print(
                f"fem_ipc_spike anchor s{index}: {len(pins)} pinned verts, "
                f"max drift through settle {drift.max() * 1000:.3f}mm ({verdict} vs 1mm)"
            )

    if attachment is not None:
        center = attachment.attach()
        print(
            f"fem_ipc_spike attach s{grasp_strand}: band {len(attachment.indices)} verts, "
            f"center {np.round(center * 1000, 1).tolist()}mm"
        )
        lift = 0.06 if cfg.run.test == "follow" else 0.08
        braid_layout = layout.braid_layout()
        crossing_x = float(braid_layout.x_start) + float(
            braid.crossings[0].position_frac
        ) * (float(braid_layout.x_end) - float(braid_layout.x_start))

        def crossing_state() -> tuple[float, float]:
            p0 = positions(rope_entities[0])
            p1 = positions(rope_entities[1])
            m0 = p0[np.abs(p0[:, 0] - crossing_x) < 0.02]
            m1 = p1[np.abs(p1[:, 0] - crossing_x) < 0.02]
            dz = float(m0[:, 2].mean() - m1[:, 2].mean())
            min_dist = float(
                np.min(np.linalg.norm(p0[:, None, :] - p1[None, :, :], axis=2))
            )
            return dz, min_dist

        over = int(braid.crossings[0].over_strand)
        under = int(braid.crossings[0].under_strand)
        flips = 0
        drive_started = time.perf_counter()
        total_drive = int(cfg.run.drive_steps) + 200
        for step in range(1, total_drive + 1):
            alpha = min(1.0, step / float(cfg.run.drive_steps))  # lift, then hold 200
            attachment.drive_to(center + np.array([0.0, 0.0, lift * alpha]))
            scene.step()
            if step % 20 == 0 or step == total_drive:
                target = center + np.array([0.0, 0.0, lift * alpha])
                err = float(np.linalg.norm(attachment.band_center() - target))
                line = (
                    f"fem_ipc_spike drive step={step} target_z=+{lift * alpha * 1000:.1f}mm "
                    f"track_err={err * 1000:.2f}mm"
                )
                if cfg.run.test == "contact":
                    dz, min_dist = crossing_state()
                    if dz < 0.0:
                        flips += 1
                    line += (
                        f" crossing dz(s{over}-s{under})={dz * 1000:+.2f}mm "
                        f"min_dist={min_dist * 1000:.2f}mm"
                    )
                print(line)
        drive_elapsed = time.perf_counter() - drive_started
        print(
            f"fem_ipc_spike drive: {total_drive} steps in {drive_elapsed:.1f}s "
            f"({total_drive / drive_elapsed:.1f} steps/s)"
        )
        if cfg.run.test == "contact":
            print(
                f"fem_ipc_spike contact verdict: "
                + (
                    "PASS -- crossing never flipped (PBD flipped at step 1176)"
                    if flips == 0
                    else f"FAIL -- dz went negative on {flips} sampled steps"
                )
            )

    if cfg.run.keep_open or cfg.run.viewer:
        print("fem_ipc_spike holding the viewer open; Ctrl+C to exit.")
        while True:
            scene.step()


if __name__ == "__main__":
    main()
