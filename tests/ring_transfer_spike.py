"""ring_transfer spike: can a closed elastic loop be moved from post A onto post B
with the grasps the task specifies, before any robot is involved?

DIAGNOSTIC TOOL, not a demo. docx 2.6. The scene is the task's own
(`RingTransferSceneBuilder`, same config), the arm is left out, and the three
grasp bands are driven straight from the oracle's waypoints. Nothing here judges
the task; it answers whether the task can exist:

    mesh      the periodic tube is written; no solver         (no CUDA needed)
    settle    it loads as FEM+IPC around A and comes to rest  winding A=1, B=0
    stretch   hooked open on two bands, the far cap is swung  winding A=1, B=1,
              round A, carried over B and put down            loop stays on B
    transfer  the near cap is lifted over A's top and let go  winding A=0, B=1
    carry     (independent of the two above) the loop is       winding A=0, B=1
              hooked next to A, lifted, carried hanging and
              lassoed onto B from the side

Each test runs the ones before it and stops at the first failure. Verdicts are
enumerated, not booleans: `ok / penetrated / slipped_off_target / stayed_on_anchor
/ not_settled / diverged`, diverged first.

The stretch is the reading that decides the design. The offline gate
(`tests/check_ring_transfer_geometry.py`) proves the strands clear B's shaft on
a straight-strand model at 12 % stretch; what the solver has to confirm is that
the follow bands hold ~1 N of tension without drifting (`band_err`), that the
loop does not lift off A's top while it is pulled (`A top crossed` must stay
False until the transfer), and that the released loop is caught by B rather
than snapping back over it.

    python -B -m tests.ring_transfer_spike run.test=mesh
    python -B -m tests.ring_transfer_spike run.test=settle env.genesis.backend=gpu
    python -B -m tests.ring_transfer_spike run.test=stretch env.genesis.backend=gpu run.verbose=true
    python -B -m tests.ring_transfer_spike run.test=transfer env.genesis.backend=gpu \\
        recording=hq recording.path=runs/videos/ring_transfer/spike_transfer.mp4 \\
        recording.camera=[oblique,ring]

Hydra's `-m` sweep does not work: Genesis initialises once per process.
Requires `pip install pyuipc` (CUDA 12.6+) for everything but `mesh`.
"""

from __future__ import annotations

import time

import hydra
import numpy as np
from omegaconf import DictConfig

TESTS = ("mesh", "settle", "stretch", "transfer", "carry")


def require_pyuipc() -> None:
    try:
        import uipc  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "ring_transfer_spike: python module 'uipc' is missing -- the IPC coupler cannot run. "
            f"Install it in this venv with `pip install pyuipc` (needs CUDA 12.6+). Original error: {error}"
        )


@hydra.main(version_base="1.3", config_path="../configs", config_name="ring_transfer_spike")
def main(cfg: DictConfig) -> None:
    if str(cfg.run.test) not in TESTS:
        raise SystemExit(f"ring_transfer_spike: run.test must be one of {TESTS}.")
    if str(cfg.run.test) != "mesh":
        require_pyuipc()

    import genesis as gs

    from topogym.core import save_resolved_config
    from topogym.supervision import stop_before_physics
    from topogym.tasks.routing import _ring_transfer_geometry as geo
    from topogym.tasks.routing.ring_transfer import (
        HOOK_BANDS,
        LIFT_BANDS,
        NEAR_BAND,
        RingTransferLayout,
        RingTransferSceneBuilder,
    )
    from topogym.utils.recording import print_recording_saved, recording_session_from_config
    from topogym.verification.ring_transfer_verifier import (
        enclosure_of,
        loop_centerline,
        post_contact_count,
        post_surface_gap,
        post_top_crossed,
        winding_signature,
    )
    from topogym.world import tabletop_frames_from_config
    from topogym.world.closed_band import closed_arc_length
    from topogym.world.rope import resolve_mesh_dir, write_obj

    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"ring_transfer_spike_config -> {resolved}", flush=True)

    task = cfg.task
    world_frames = tabletop_frames_from_config(cfg.env)
    layout = RingTransferLayout(task, task_origin=world_frames.task_origin)
    ring, posts, anchor, target = layout.ring, layout.posts, layout.anchor, layout.target
    path = layout.far_cap_path()
    print(layout.summary(), flush=True)
    print(
        "ring_transfer_spike far-cap path (task mm): "
        + " -> ".join(f"{label}{np.round(point * 1000).astype(int).tolist()}" for label, point in path),
        flush=True,
    )

    if str(cfg.run.test) == "mesh":
        frames, vertices, faces = geo.spawn_mesh(ring, layout.spawn)
        mesh_path = resolve_mesh_dir(task.rope.mesh.output_dir) / "ring_spike.obj"
        write_obj(mesh_path, vertices, faces)
        print(
            f"ring_transfer_spike mesh: perimeter {frames.perimeter:.4f} m, Lk {frames.self_linking} "
            f"at Tw {frames.twist_turns:+.4f}, {len(vertices)} skin verts -> {mesh_path}. "
            "tests/check_ring_transfer_geometry.py has the full gate."
        )
        return

    # --- scene ------------------------------------------------------------
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[cfg.env.genesis.backend], precision=str(cfg.env.genesis.precision))
    # A close-up on top of the env cameras (those frame the whole table). It goes
    # in through the builder because Genesis refuses cameras once the scene is built.
    camera_cfg = cfg.run.camera
    resolution = cfg.recording.res if cfg.recording.res is not None else camera_cfg.res
    built = RingTransferSceneBuilder(cfg.env, task, cfg.robot_control).build(
        show_viewer=bool(cfg.run.viewer),
        include_robot=bool(cfg.run.include_robot),
        extra_cameras={
            str(camera_cfg.name): {
                "pos": camera_cfg.pos,
                "lookat": camera_cfg.lookat,
                "fov": camera_cfg.fov,
                "res": resolution,
            }
        },
    )
    scene = built.scene
    cameras = built.cameras
    if stop_before_physics(cfg, scene, "ring_transfer_spike"):
        raise SystemExit(0)

    # --- readings -----------------------------------------------------------
    tolerance = float(task.success.winding_tolerance)
    wrap_band = {name: post.radius + 3.0 * ring.tube_radius for name, post in posts.items()}
    crossed = {name: False for name in posts}
    min_gap = {name: float("inf") for name in posts}
    hud_state = {"label": "spawn", "step": 0, "winding": {}, "ratio": 1.0}

    def centerline() -> np.ndarray:
        return loop_centerline(built.nodes(), built.members)

    def watch(nodes: np.ndarray) -> None:
        for name, post in posts.items():
            crossed[name] = crossed[name] or post_top_crossed(nodes, post, wrap_band=wrap_band[name])
            min_gap[name] = min(min_gap[name], post_surface_gap(nodes, post))

    def report(label: str, step: int, bands_active=()) -> dict:
        nodes = built.nodes()
        watch(nodes)
        line = centerline()
        winding, raw, integral = winding_signature(line, posts, tolerance=tolerance)
        # The sign is the loop's orientation (which way round it was spawned),
        # not a topological difference: |w| = 1 is "around the post".
        winding = {name: abs(value) for name, value in winding.items()}
        ratio = closed_arc_length(line)[1] / built.frames.perimeter
        contacts = {name: post_contact_count(nodes, post, tube_radius=ring.tube_radius) for name, post in posts.items()}
        gaps = {name: post_surface_gap(nodes, post) for name, post in posts.items()}
        errs = {
            name: float(np.linalg.norm(built.bands[name].band_center() - targets[name])) * 1000.0
            for name in bands_active
            if name in targets
        }
        hud_state.update(label=label, step=step, winding=winding, ratio=ratio)
        print(
            f"ring_transfer_spike {label} step={step} winding={winding} raw={ {k: round(v, 3) for k, v in raw.items()} } "
            f"{'' if integral else 'NON-INTEGRAL '}ratio={ratio:.3f} contacts={contacts} "
            f"gaps={ {k: f'{v * 1000:.1f}' for k, v in gaps.items()} }mm top_crossed={crossed} "
            f"top_z={line[:, 2].max() * 1000:.1f}mm"
            + (f" band_err={ {k: f'{v:.2f}' for k, v in errs.items()} }mm" if errs else ""),
            flush=True,
        )
        return {"winding": winding, "integral": integral, "ratio": ratio, "contacts": contacts, "gaps": gaps}

    def hud_line() -> list[str]:
        return [
            f"{hud_state['label']}  step {hud_state['step']}",
            f"winding {hud_state['winding']}   length x{hud_state['ratio']:.3f}",
        ]

    def diverged(nodes: np.ndarray) -> bool:
        return not np.all(np.isfinite(nodes)) or float(np.abs(nodes).max()) > 5.0

    targets: dict[str, np.ndarray] = {}

    def drive(band_names, goals: dict[str, np.ndarray], label: str, *, every: int = 25) -> None:
        """Move the named bands' centres to `goals` (task frame) at drive_speed."""

        starts = {name: built.bands[name].band_center() for name in band_names}
        goals_world = {name: layout.to_world(goals[name]) for name in band_names}
        distance = max(float(np.linalg.norm(goals_world[n] - starts[n])) for n in band_names)
        steps = max(int(task.transfer.min_segment_steps), int(np.ceil(distance / float(task.transfer.drive_speed))))
        started = time.perf_counter()
        for step in range(1, steps + 1):
            alpha = step / steps
            for name in band_names:
                targets[name] = starts[name] + alpha * (goals_world[name] - starts[name])
                built.bands[name].drive_to(targets[name])
            scene.step()
            if step % every == 0 or step == steps:
                report(label, step, band_names)
                if diverged(built.nodes_world()):
                    raise SystemExit(f"ring_transfer_spike {label}: DIVERGED")
        print(f"ring_transfer_spike {label}: {steps} steps in {time.perf_counter() - started:.1f}s", flush=True)

    def settle(count: int, label: str, *, every: int = 25) -> dict:
        previous = built.nodes_world()
        last = None
        for step in range(1, count + 1):
            scene.step()
            if step % 10 == 0:
                current = built.nodes_world()
                moved = float(np.linalg.norm(current - previous, axis=1).max()) / 10.0
                previous = current
                if cfg.run.verbose:
                    print(f"ring_transfer_spike {label} step={step} max_move={moved * 1000:.4f}mm/step", flush=True)
                if moved < float(task.success.settle_tol) and step >= 50:
                    last = report(label, step)
                    print(f"ring_transfer_spike {label}: converged at step {step}", flush=True)
                    return last
            if step % every == 0:
                last = report(label, step)
        last = report(label, count)
        print(f"ring_transfer_spike {label}: NOT converged in {count} steps", flush=True)
        return last

    def verdict(label: str, reading: dict, *, want: dict[str, int]) -> str:
        if any(gap < float(task.success.min_surface_gap) for gap in reading["gaps"].values()):
            code = "penetrated"
        elif reading["winding"] == want:
            code = "ok"
        elif reading["winding"].get(anchor.name) == 1 and reading["winding"].get(target.name) == 0:
            code = "stayed_on_anchor"
        elif reading["winding"].get(target.name) == 0:
            code = "slipped_off_target"
        else:
            code = "unexpected"
        print(
            f"ring_transfer_spike {label} verdict: {code} -- winding {reading['winding']} (want {want}), "
            f"min gaps {{ {', '.join(f'{k}: {v * 1000:.1f}mm' for k, v in min_gap.items())} }}, "
            f"top crossed {crossed}, length x{reading['ratio']:.3f}",
            flush=True,
        )
        return code

    def run_phases() -> None:
        # --- settle (loop around A) ---------------------------------------
        reading = settle(int(cfg.run.settle_steps), "settle")
        want_start = {name: (1 if name in ring.enclosure else 0) for name in posts}
        if verdict("settle", reading, want=want_start) != "ok":
            return
        if str(cfg.run.test) == "settle":
            return

        if str(cfg.run.test) == "carry":
            # --- carry: hook next to A, lift, carry hanging, lasso B ---------------
            for name in LIFT_BANDS:
                built.bands[name].attach()
            for name in LIFT_BANDS:
                targets[name] = built.bands[name].band_center()
            start_xy = 0.5 * (layout.to_task(built.bands[LIFT_BANDS[0]].band_center()) + layout.to_task(built.bands[LIFT_BANDS[1]].band_center()))
            path_c = layout.carry_path(start_xy=start_xy)
            heading = target.center - anchor.center
            across_c = np.array([-heading[1], heading[0], 0.0]) / float(np.linalg.norm(heading))
            half_c = 0.5 * float(task.carry.spread)
            print(
                "ring_transfer_spike carry path (task mm): "
                + " -> ".join(f"{label}{np.round(point * 1000).astype(int).tolist()}" for label, point in path_c),
                flush=True,
            )
            # Which band is on which side of the finger axis, from where they ARE
            # (band names follow the loop's own axis, not the A->B heading;
            # assigning by name drove them across each other on 2026-08-25).
            sides = {}
            for name in LIFT_BANDS:
                centre = layout.to_task(built.bands[name].band_center())
                sides[name] = 1.0 if float(np.dot(centre - np.array([start_xy[0], start_xy[1], 0.0]), across_c)) >= 0.0 else -1.0
            for label, point in path_c[1:]:
                goals = {name: point + sides[name] * half_c * across_c for name in LIFT_BANDS}
                drive(LIFT_BANDS, goals, f"carry:{label}")
            for name in LIFT_BANDS:
                built.bands[name].release()
                targets.pop(name, None)
            reading = settle(int(task.transfer.release_settle_steps), "carry:release")
            want_goal = {name: (1 if name == target.name else 0) for name in posts}
            code = verdict("carry", reading, want=want_goal)
            print(f"ring_transfer_spike carry enclosure {sorted(enclosure_of(reading['winding']))} (want [{target.name}]) -- {'PASS' if code == 'ok' else 'FAIL'}", flush=True)
            return

        # --- stretch: hook the far cap on two bands, follow the oracle path ----
        half = 0.5 * float(task.grasp.spread)
        for name in HOOK_BANDS:
            built.bands[name].attach()
        for name in HOOK_BANDS:
            targets[name] = built.bands[name].band_center()
        for label, point in path[1:]:
            direction = point[:2] - anchor.center
            direction = direction / float(np.linalg.norm(direction))
            across = np.array([-direction[1], direction[0], 0.0])
            goals = {
                HOOK_BANDS[0]: point + half * across,
                HOOK_BANDS[1]: point - half * across,
            }
            drive(HOOK_BANDS, goals, f"stretch:{label}")
            if label == "rise":
                print(
                    f"ring_transfer_spike stretch: model ratio at rise top {layout.stretch_ratio_at(point):.3f}",
                    flush=True,
                )
        for name in HOOK_BANDS:
            built.bands[name].release()
            targets.pop(name, None)
        reading = settle(int(task.transfer.release_settle_steps), "stretch:release")
        want_both = {name: 1 for name in posts}
        if verdict("stretch", reading, want=want_both) != "ok":
            return
        if crossed[anchor.name]:
            print(
                f"ring_transfer_spike stretch: WARNING the loop went over {anchor.name}'s top during the "
                "stretch -- the anchor did not hold it; the transfer reading below is not the task's",
                flush=True,
            )
        if str(cfg.run.test) == "stretch":
            return

        # --- transfer: lift the near cap over A's top -------------------------
        near = built.bands[NEAR_BAND]
        centre = layout.to_task(near.band_center())
        expected = anchor.center - (anchor.radius + ring.tube_radius) * (target.center - anchor.center) / float(
            np.linalg.norm(target.center - anchor.center)
        )
        print(
            f"ring_transfer_spike transfer: near band at {np.round(centre * 1000, 1).tolist()} mm, "
            f"expected at the anchor's outer surface {np.round(expected * 1000, 1).tolist()} mm "
            f"(drift {np.linalg.norm(centre[:2] - expected) * 1000:.1f} mm)",
            flush=True,
        )
        near.attach()
        targets[NEAR_BAND] = near.band_center()
        lift = np.array([centre[0], centre[1], layout.lift_z()])
        drive((NEAR_BAND,), {NEAR_BAND: lift}, "transfer:lift")
        toward = (target.center - anchor.center) / float(np.linalg.norm(target.center - anchor.center))
        shifted = lift + float(task.transfer.shift) * np.array([toward[0], toward[1], 0.0])
        drive((NEAR_BAND,), {NEAR_BAND: shifted}, "transfer:shift")
        near.release()
        targets.pop(NEAR_BAND, None)
        reading = settle(int(task.transfer.release_settle_steps), "transfer:release")
        want_goal = {name: (1 if name == target.name else 0) for name in posts}
        code = verdict("transfer", reading, want=want_goal)
        print(
            f"ring_transfer_spike transfer enclosure {sorted(enclosure_of(reading['winding']))} "
            f"(want [{target.name}]) -- {'PASS' if code == 'ok' else 'FAIL'}",
            flush=True,
        )

    with recording_session_from_config(scene, cameras, cfg.recording, hud=hud_line):
        run_phases()
    print_recording_saved(cfg.recording)

    if cfg.run.keep_open_no_step:
        print("ring_transfer_spike holding the viewer open (no stepping); Ctrl+C to exit.")
        while True:
            time.sleep(0.05)
    if cfg.run.keep_open or cfg.run.viewer:
        print("ring_transfer_spike holding the viewer open; Ctrl+C to exit.")
        while True:
            scene.step()


if __name__ == "__main__":
    main()
