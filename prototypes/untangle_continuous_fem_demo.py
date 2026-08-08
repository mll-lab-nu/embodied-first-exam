"""Armless untangle_continuous on FEM + IPC ropes -- step 3 of the vertical slice.

DIAGNOSTIC TOOL, not a production demo. Kept for backend debugging (its
micro-tests isolate constraint layers the full task cannot); the production
path is the physical-handle / pinch demos, which run FEM by default since
2026-08-08.

Same braid, same tube meshes, same crossing detector as the PBD task; the rope
solver is FEM under Genesis' IPC coupler, the arm is replaced by driving the
grasp band directly along the same phase sequence the pinch demo uses
(grasp -> carry_up -> cross_over -> place_down -> settle). Two runs matter:

  # contact test: grasp the UNDER strand, lift. PBD tunnelled at step 1176;
  # here the crossing must never flip.
  python -m prototypes.untangle_continuous_fem_demo --seed 0 --grasp-strand 1 --trace

  # solve run: grasp the over strand (default), carry it across, place, settle.
  # The detector must report crossings 1 -> 0.
  python -m prototypes.untangle_continuous_fem_demo --seed 0 --trace

The trace file uses the same columns as the PBD runs (run11~14 in
docs/develop/physics/untangle/debug-log/) so the two solvers can be compared
line by line. `parked` is always 0 -- it counts particles clamped at the PBD
solver's domain corner, which has no FEM analog.

The free-end connectors are left out: under IPC they would be `needs_coup=False`
props (invisible to the ropes' contact), so they add a kinematic-write code path
without adding physics. They return with the robot arm integration.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "untangle_continuous_topogym_tabletop_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Armless continuous untangle on FEM+IPC ropes."
    )
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    parser.add_argument("--common-config", type=Path, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default="gpu")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--grasp-strand",
        type=int,
        default=None,
        help=(
            "Which strand to grasp. Default: the crossing's over strand (the "
            "solving move). Passing the under strand turns the run into the "
            "contact test."
        ),
    )
    parser.add_argument("--strands", type=int, default=None)
    parser.add_argument("--segment-length", type=float, default=None)
    # Material knobs, spike-calibrated defaults (run15: rest gap 9.66mm of 10).
    parser.add_argument("--e", type=float, default=1e5)
    parser.add_argument("--nu", type=float, default=0.45)
    parser.add_argument("--rho", type=float, default=650.0)
    parser.add_argument("--friction-mu", type=float, default=0.3)
    parser.add_argument("--d-hat", type=float, default=0.002)
    parser.add_argument("--strength", type=float, default=100.0)
    parser.add_argument("--band-radius", type=float, default=0.015)
    parser.add_argument("--lift", type=float, default=0.08, help="carry_up height (m).")
    parser.add_argument(
        "--place-margin",
        type=float,
        default=0.05,
        help=(
            "How far past the mirrored lane to place the grasped end (m). A "
            "plain mirror lands it ON the other strand's lane, ~10mm short of "
            "the 16mm separation the success criterion asks for."
        ),
    )
    parser.add_argument("--move-steps", type=int, default=280, help="Steps per motion phase.")
    parser.add_argument("--place-steps", type=int, default=400)
    parser.add_argument("--settle-steps", type=int, default=300)
    parser.add_argument(
        "--arm",
        action="store_true",
        help=(
            "Add the Franka and drive the grasp through it: IK moves the hand "
            "along the same waypoints, the rope band follows the commanded hand "
            "pose at a fixed offset. The robot is needs_coup=False -- outside "
            "IPC entirely -- matching the task's design (finger contact carries "
            "no signal, the grasp is a weld; design doc section 3.5)."
        ),
    )
    parser.add_argument("--trace", action="store_true", help="Write the rope trace file.")
    parser.add_argument("--viewer", action="store_true")
    parser.add_argument("--keep-open", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def require_pyuipc() -> None:
    try:
        import uipc  # noqa: F401
    except ImportError as error:
        raise SystemExit(
            "untangle_continuous_fem_demo: python module 'uipc' is missing. "
            f"`pip install pyuipc` in this venv (CUDA 12.6+). Original error: {error}"
        )


class FEMStrandScene:
    """Duck-typed stand-in for UntangleContinuousScene, enough for the evaluator.

    `strand_centerline` mirrors the task scene's implementation: vertices are
    unordered after tetrahedralization, so each vertex's normalized arc length
    -- assigned once at spawn, by nearest spawn-centerline sample -- bins it
    along the rope, and bin centroids are the centerline samples. Averaging a
    bin also averages away the tube's radial thickness.
    """

    def __init__(self, scene, braid, entities: list, spawn_centerlines: list[np.ndarray]) -> None:
        self.scene = scene
        self.braid = braid
        self.strand_entities = {index: entity for index, entity in enumerate(entities)}
        self._arclength: dict[int, np.ndarray] = {}
        for index, (entity, centerline) in enumerate(zip(entities, spawn_centerlines)):
            spawn = self._positions(entity)
            nearest = np.argmin(
                np.linalg.norm(spawn[:, None, :] - centerline[None, :, :], axis=2), axis=1
            )
            self._arclength[index] = nearest.astype(float) / max(len(centerline) - 1, 1)

    @staticmethod
    def _positions(entity) -> np.ndarray:
        from topogym.world.rope import tensor_to_numpy

        pos = tensor_to_numpy(entity.get_state().pos)
        return pos[0] if pos.ndim == 3 else pos

    def strand_particles(self, strand_index: int) -> np.ndarray:
        return self._positions(self.strand_entities[int(strand_index)])

    def strand_velocities(self, strand_index: int) -> np.ndarray:
        from topogym.world.rope import tensor_to_numpy

        vel = tensor_to_numpy(self.strand_entities[int(strand_index)].get_state().vel)
        return vel[0] if vel.ndim == 3 else vel

    def strand_centerline(self, strand_index: int, *, samples: int = 80) -> np.ndarray:
        positions = self.strand_particles(strand_index)
        arclength = self._arclength[int(strand_index)]
        edges = np.linspace(0.0, 1.0, int(samples) + 1)
        bucket = np.clip(np.digitize(arclength, edges[1:-1]), 0, int(samples) - 1)
        points = [
            positions[bucket == b].mean(axis=0)
            for b in range(int(samples))
            if np.any(bucket == b)
        ]
        return np.asarray(points, dtype=float)


class FEMTrace:
    """run11-compatible trace columns for FEM strands. `parked` is always 0."""

    def __init__(self, path: Path, strand_scene: FEMStrandScene, *, radius: float, notes: str) -> None:
        from topogym.supervision.rope_trace import height_over, min_bend_radius, polyline_gap

        self._height_over = height_over
        self._min_bend_radius = min_bend_radius
        self._polyline_gap = polyline_gap
        self.strand_scene = strand_scene
        self.radius = radius
        path.parent.mkdir(parents=True, exist_ok=True)
        self._file = path.open("w", encoding="utf-8")
        self._previous: dict[int, np.ndarray] = {}
        self.flips: dict[int, int] = {}
        self._last_sign: dict[int, float] = {}
        self._write("# untangle_continuous FEM+IPC rope trace   every=4 steps")
        self._write(f"# {notes}")
        self._write(
            "# step phase strand max_v(m/s) jump(mm/step) offset(mm) bend_r(mm) bend_at(s) "
            "bend_free(mm) pair_gap(mm) over_z(mm) minz(mm) parked"
        )
        self._write(
            "# over_z sign readable only while pair_gap is in the 6~15mm band "
            "(rope_contact doc section 9.6); flips counted only there"
        )

    def _write(self, line: str) -> None:
        self._file.write(line + "\n")
        self._file.flush()

    def note(self, text: str) -> None:
        self._write(f"# {text}")

    @staticmethod
    def _max_offset(points: np.ndarray, polyline: np.ndarray) -> float:
        start = polyline[:-1]
        direction = polyline[1:] - start
        length_sq = np.maximum(np.einsum("mj,mj->m", direction, direction), 1e-18)
        offset = points[:, None, :] - start[None, :, :]
        t = np.clip(np.einsum("nmj,mj->nm", offset, direction) / length_sq, 0.0, 1.0)
        closest = start[None, :, :] + t[:, :, None] * direction[None, :, :]
        return float(np.linalg.norm(points[:, None, :] - closest, axis=2).min(axis=1).max())

    def sample(self, step: int, phase: str) -> None:
        scene = self.strand_scene
        centerlines = {
            index: scene.strand_centerline(index, samples=80)
            for index in sorted(scene.strand_entities)
        }
        for index in sorted(scene.strand_entities):
            positions = scene.strand_particles(index)
            velocities = scene.strand_velocities(index)
            centerline = centerlines[index]
            others = [centerlines[j] for j in centerlines if j != index]
            pair_gap = min((self._polyline_gap(centerline, o) for o in others), default=float("nan"))
            over_z = (
                self._height_over(centerline, others[0]) if others else float("nan")
            )
            bend_r, bend_at = self._min_bend_radius(centerline)
            bend_free, _ = self._min_bend_radius(centerline[3:-3])
            previous = self._previous.get(index)
            jump = (
                float(np.linalg.norm(positions - previous, axis=1).max())
                if previous is not None and previous.shape == positions.shape
                else float("nan")
            )
            self._previous[index] = positions
            max_v = float(np.linalg.norm(velocities, axis=1).max())
            offset = self._max_offset(positions, centerline)
            # Sign-flip bookkeeping in the readable band only. |over_z| must also
            # be large enough to constitute a real over/under relationship: two
            # solved ropes lying side by side have pair_gap ~10mm with over_z
            # jittering around zero, and that jitter is not a pass-through
            # (2026-08-06 solve run counted 6 such non-events).
            if (
                others
                and 0.006 <= pair_gap <= 0.015
                and np.isfinite(over_z)
                and abs(over_z) > 0.002
            ):
                sign = float(np.sign(over_z))
                last = self._last_sign.get(index)
                if last is not None and sign != last:
                    self.flips[index] = self.flips.get(index, 0) + 1
                    self._write(f"# EVENT step={step} s{index} over_z sign flip in readable band")
                self._last_sign[index] = sign
            self._write(
                f"{step:6d} {phase:s} s{index} {max_v:9.4f} {jump * 1000:10.4f} "
                f"{offset * 1000:9.2f} {min(bend_r, 9.999) * 1000:9.1f} {bend_at:8.3f} "
                f"{min(bend_free, 9.999) * 1000:9.1f} {pair_gap * 1000:9.2f} "
                f"{over_z * 1000:+9.2f} {positions[:, 2].min() * 1000:8.2f} 0"
            )

    def close(self) -> None:
        self._write("# trace ended")
        self._file.close()


def main() -> None:
    args = parse_args()
    require_pyuipc()

    import genesis as gs
    from omegaconf import OmegaConf

    from topogym.core import load_topogym_configs
    from topogym.generation.braid import verify_braid_spec
    from topogym.primitives.fem_attachment import FEMRopeAttachment
    from topogym.tasks import UntangleContinuousLayout
    from topogym.verification import UntangleContinuousPuzzleEvaluator
    from topogym.world import materials
    from topogym.world.genesis_ipc_vertex_constraints import install, pin_near
    from topogym.world.rope import tensor_to_numpy, tube_morph, write_obj

    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    if args.strands is not None:
        cfg = OmegaConf.merge(cfg, {"task": {"braid": {"n_strands": args.strands}}})
    if args.segment_length is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"mesh": {"segment_length": args.segment_length}}}}
        )

    layout = UntangleContinuousLayout(cfg.task, seed=args.seed)
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
        f"untangle_continuous_fem seed={args.seed} word={braid.word} "
        f"over_under={[(c.over_strand, c.under_strand) for c in braid.crossings]} {report}"
    )
    if not report.ok:
        raise SystemExit("untangle_continuous_fem: braid self-check FAILED")

    crossing = braid.crossings[0]
    grasp_strand = (
        int(args.grasp_strand) if args.grasp_strand is not None else int(crossing.over_strand)
    )
    is_contact_test = grasp_strand == int(crossing.under_strand)
    other_strand = int(crossing.under_strand if grasp_strand == crossing.over_strand else crossing.over_strand)
    print(
        f"untangle_continuous_fem grasping s{grasp_strand} "
        f"({'contact test: the strand under the crossing' if is_contact_test else 'solve run: the over strand'})"
    )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[args.backend])
    install()

    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.01, substeps=1, gravity=(0.0, 0.0, -9.81)),
        coupler_options=gs.options.IPCCouplerOptions(contact_d_hat=float(args.d_hat)),
        fem_options=gs.options.FEMOptions(),
        viewer_options=gs.options.ViewerOptions(
            camera_pos=(0.55, -0.55, 0.45),
            camera_lookat=(0.0, 0.0, 0.03),
            camera_fov=45,
        ),
        show_viewer=args.viewer,
    )
    scene.add_entity(
        gs.morphs.Plane(),
        material=gs.materials.Rigid(coup_type="ipc_only"),
        name="ground",
    )
    manifest = None
    if args.arm:
        from topogym.core import EntityManifest

        manifest = EntityManifest()
        # Same mount pose relative to the ropes as the real tabletop scene:
        # robot_mount z equals the table surface there, and this scene's ropes
        # sit on z=0, so the base goes to (mount_x, mount_y, 0).
        mount = cfg.env.robot_mount.pos
        manifest.add(
            "robot",
            scene.add_entity(
                gs.morphs.MJCF(
                    file=cfg.robot_control.robot.asset,
                    pos=(float(mount[0]), float(mount[1]), 0.0),
                    euler=tuple(cfg.env.robot_mount.euler),
                ),
                # Outside IPC: the coupler skips needs_coup=False entities, so
                # the arm costs nothing in the Newton solve and cannot collide
                # with the FEM ropes -- which is the task's grasp design anyway.
                material=gs.materials.Rigid(needs_coup=False),
                name="robot",
            ),
        )
    rope_material = gs.materials.FEM.Elastic(
        model="stable_neohookean",
        E=float(args.e),
        nu=float(args.nu),
        rho=float(args.rho),
        friction_mu=float(args.friction_mu),
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

    anchor_radius = float(cfg.task.rope.anchor_radius)
    for entity, mesh in zip(rope_entities, rope_meshes):
        pin_near(entity, [mesh.endpoint_centers[0]], anchor_radius)
    attachment = FEMRopeAttachment(
        rope_entities[grasp_strand],
        rope_meshes[grasp_strand].endpoint_centers[1],
        float(args.band_radius),
        strength=float(args.strength),
    )

    scene.build()
    controller = None
    if args.arm:
        from topogym.utils import initialize_franka_controller

        # Before any stepping: without PD gains + home pose the arm is an
        # unactuated linkage that collapses onto the ropes.
        controller = initialize_franka_controller(
            scene=scene, manifest=manifest, robot_cfg=cfg.robot_control
        )
    strand_scene = FEMStrandScene(
        scene, braid, rope_entities, [mesh.centerline for mesh in rope_meshes]
    )
    evaluator = UntangleContinuousPuzzleEvaluator.from_config(cfg.task)

    trace = None
    if args.trace:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        trace_path = Path("runs") / f"untangle_continuous_fem_trace_{stamp}.log"
        trace = FEMTrace(
            trace_path,
            strand_scene,
            radius=float(cfg.task.rope.radius),
            notes=(
                f"seed={args.seed} word={braid.word} grasp_strand={grasp_strand} "
                f"E={args.e} nu={args.nu} rho={args.rho} friction_mu={args.friction_mu} "
                f"d_hat={args.d_hat} strength={args.strength} dt=0.01 substeps=1 "
                f"solver=FEM+IPC (genesis 1.2.1 + pyuipc)"
            ),
        )
        print(f"untangle_continuous_fem trace -> {trace_path}")

    # --- settle, verify detector against ground truth -------------------------
    started = time.perf_counter()
    total_steps = 0

    def run_phase(phase: str, steps: int, target_fn=None) -> None:
        nonlocal total_steps
        # Stdout marker so a viewer watcher knows which ~tens of seconds to look
        # at -- at ~7 steps/s the motion is ~2mm/s and easy to take for static.
        print(
            f"untangle_continuous_fem phase {phase}: {steps} steps "
            f"(~{steps / 7:.0f}s wall)",
            flush=True,
        )
        for local in range(1, steps + 1):
            if target_fn is not None:
                attachment.drive_to(target_fn(local / steps))
            scene.step()
            total_steps += 1
            if trace is not None and total_steps % 4 == 0:
                trace.sample(total_steps, phase)

    run_phase("settle0", 120)
    state = evaluator.classify(strand_scene)
    gt_ok, gt_detail = evaluator.matches_braid_ground_truth(strand_scene)
    print(
        f"untangle_continuous_fem detect crossings={len(state.crossings)} "
        f"min_separation={state.min_separation:.4f} gt_match={gt_ok} {gt_detail}"
    )
    if trace is not None:
        trace.note(f"detector vs braid ground truth: match={gt_ok} {gt_detail}")
    if not gt_ok:
        print("untangle_continuous_fem WARNING: detector disagrees with braid ground truth")

    # --- the move -------------------------------------------------------------
    start = attachment.band_center()
    radius = float(cfg.task.rope.radius)
    lift = float(args.lift)
    carry = start + np.array([0.0, 0.0, lift])
    # Mirror across the braid center lane, then keep going by --place-margin so
    # the ropes end up separated, not adjacent.
    place_y = -np.sign(start[1]) * (abs(start[1]) + float(args.place_margin))
    place_xy = np.array([start[0], place_y])
    cross = np.array([place_xy[0], place_xy[1], start[2] + lift])
    settle_z = radius + float(args.d_hat)
    place = np.array([place_xy[0], place_xy[1], settle_z])

    def lerp(a: np.ndarray, b: np.ndarray):
        return lambda alpha: a + (b - a) * alpha

    if controller is None:
        attachment.attach()
        if trace is not None:
            trace.note(
                f"move 1: grasping s{grasp_strand} free end, band "
                f"{len(attachment.indices)} verts at {np.round(start * 1000, 1).tolist()}mm"
            )
        run_phase("move1_grasp", 100, lambda alpha: start)
        run_phase("move1_carry_up", int(args.move_steps), lerp(start, carry))
        if not is_contact_test:
            run_phase("move1_cross_over", int(args.move_steps), lerp(carry, cross))
            run_phase("move1_place_down", int(args.place_steps), lerp(cross, place))
        else:
            # Contact test: hold at height, the way run11/run13 failed.
            run_phase("move1_carry_up", 200, lambda alpha: carry)
        attachment.release()
        if trace is not None:
            trace.note("attachment released")
        run_phase("move2_settle", int(args.settle_steps))
    else:
        # Arm mode: IK drives the hand, the band rides HAND_ABOVE below the
        # *commanded* hand pose (commanded, not measured: both the arm's PD loop
        # and the band's soft constraint then chase the same target, and the
        # animator gets the new target before the step that uses it).
        HAND_ABOVE = 0.103  # Franka hand frame to fingertip

        def hand_over(point: np.ndarray) -> np.ndarray:
            return point + np.array([0.0, 0.0, HAND_ABOVE])

        def run_arm_phase(phase: str, steps: int, hand_fn) -> None:
            nonlocal total_steps
            print(
                f"untangle_continuous_fem phase {phase}: {steps} steps (~{steps / 7:.0f}s wall)",
                flush=True,
            )
            for local in range(1, steps + 1):
                hand = hand_fn(local / steps)
                if attachment.active:
                    attachment.drive_to(hand - np.array([0.0, 0.0, HAND_ABOVE]))
                controller.move_ee_to(hand, steps=1, continuous_ik=True)
                total_steps += 1
                if trace is not None and total_steps % 4 == 0:
                    trace.sample(total_steps, phase)

        gripper_open = float(cfg.robot_control.gripper.open_qpos)
        gripper_closed = float(cfg.robot_control.gripper.closed_qpos)
        controller.set_gripper(gripper_open)
        hand0 = np.asarray(controller.hand_pos(), dtype=float)
        hover = hand_over(start) + np.array([0.0, 0.0, 0.10])
        run_arm_phase("move1_grasp", 150, lerp(hand0, hover))
        run_arm_phase("move1_grasp", 80, lerp(hover, hand_over(start)))
        controller.set_gripper(gripper_closed)
        run_arm_phase("move1_grasp", 40, lambda alpha: hand_over(start))
        attachment.attach()
        if trace is not None:
            trace.note(
                f"move 1 (arm): grasped s{grasp_strand}, band "
                f"{len(attachment.indices)} verts, hand at "
                f"{np.round(controller.hand_pos() * 1000, 1).tolist()}mm"
            )
        run_arm_phase("move1_carry_up", int(args.move_steps), lerp(hand_over(start), hand_over(carry)))
        if not is_contact_test:
            run_arm_phase("move1_cross_over", int(args.move_steps), lerp(hand_over(carry), hand_over(cross)))
            run_arm_phase("move1_place_down", int(args.place_steps), lerp(hand_over(cross), hand_over(place)))
            release_hand = hand_over(place)
        else:
            run_arm_phase("move1_carry_up", 200, lambda alpha: hand_over(carry))
            release_hand = hand_over(carry)
        attachment.release()
        controller.set_gripper(gripper_open)
        if trace is not None:
            trace.note("attachment released, gripper opened")
        run_arm_phase("move2_settle", 80, lerp(release_hand, release_hand + np.array([0.0, 0.0, 0.08])))
        run_phase("move2_settle", int(args.settle_steps))

    elapsed = time.perf_counter() - started
    print(
        f"untangle_continuous_fem run: {total_steps} steps in {elapsed:.1f}s "
        f"({total_steps / elapsed:.2f} steps/s, dt=0.01 substeps=1)"
    )

    # --- verdict --------------------------------------------------------------
    final = evaluator.classify(strand_scene)
    print(
        f"untangle_continuous_fem final crossings={len(final.crossings)} "
        f"min_separation={final.min_separation:.4f} terminal={final.is_terminal}"
    )
    if trace is not None:
        flips = {f"s{i}": n for i, n in trace.flips.items()}
        print(f"untangle_continuous_fem over_z sign flips in readable band: {flips or 'none'}")
    if is_contact_test:
        held = len(final.crossings) == len(state.crossings) and (
            trace is None or not trace.flips
        )
        print(
            "untangle_continuous_fem contact verdict: "
            + ("PASS -- crossing survived the lift, no flip" if held else "FAIL -- see trace")
        )
    else:
        print(
            "untangle_continuous_fem solve verdict: "
            + (
                "PASS -- crossings cleared"
                if len(final.crossings) == 0
                else f"NOT SOLVED -- {len(final.crossings)} crossing(s) remain"
            )
        )
    if trace is not None:
        trace.close()

    if args.keep_open or args.viewer:
        print("untangle_continuous_fem holding the viewer open; Ctrl+C to exit.")
        while True:
            scene.step()


if __name__ == "__main__":
    main()
