"""Can a Franka manipulate PBD cloth in this repo without blowing it up?

DIAGNOSTIC TOOL, not a task. Stage 0 of the cloth plan: `topogym/tasks/deformation`
is the one empty category of the four, and its own docstring says the modelling
decision is still open. Four numbers decide it, and none of them has ever been
measured here, so this measures instead of arguing.

What is already settled and NOT re-litigated here: grasping is proximity-triggered
kinematic attachment, not finger friction. That is the field's standard (SoftGym's
picker and everything downstream of it) and it is already implemented in
`topogym/primitives/pbd_particle_pinch.py`. This script exists to size the guard
rails around it.

The questions, cheapest first, each able to change the design:

- ``settle``  The cloth left alone: does gravity act on it at all, and what does
               "flat and at rest" measure? Every success threshold in docx 1.1
               (flatness variance, layer count) is pulled out of thin air until
               this baseline exists. Run it from a HEIGHT (`task.cloth.z=0.050`):
               the 2026-08-17 run spawned the sheet exactly at its resting height
               and read every motion quantity as zero, which cannot distinguish
               "nothing to do" from "not simulated", so this now reports the drop.
- ``weld``    Tapered attachment weights against a hard weld. `ParticleAttachment`
               records that a uniform weld turns the held band into a rigid splint
               and pins the bend radius to 6-9 mm on a 4 mm rope, which then fires
               self-collision *inside* the material. A sheet should crease at the
               weld's edge for the same reason. Measured, not assumed.
- ``speed``   How fast can the hand drag an attached patch before the sheet
               diverges? Gives the constant for the speed-budget guard rail.
- ``pinch``   Fingers closing ON the cloth: the squeeze. The likeliest cause of
               the crash that started this work, and the one thing `contact` does
               not cover, because it descends with the fingers already shut.
- ``contact`` Does a closed gripper descending onto PBD cloth still crash?
               On Genesis 1.1.0 it was a **native segfault**, not a solver
               blow-up (`docs/develop/physics/peeling/peeling_segfault_debug_zh.md`
               localised it between `after_approach` and `after_descend`), and the
               fix was to stop doing it. Re-measured 2026-08-17 on 1.2.1: it
               survived to zero clearance, so "keep real contact and harden it" is
               back on the table -- though the fingers did push cloth 2.5 mm
               through the table, so it is not clean.

`contact` is deliberately excluded from ``run.test=all``: if it segfaults it takes
the whole process with it, and anything queued behind it dies unmeasured. Run it
on its own.

    python -m tests.pbd_cloth_spike run.test=settle task.cloth.z=0.050 run.verbose=true
    python -m tests.pbd_cloth_spike run.test=contact run.verbose=true
    python -m tests.pbd_cloth_spike run.test=weld run.taper=false
    python -m tests.pbd_cloth_spike -m run.test=speed run.drag_speed=0.004,0.012,0.024
    python -m tests.pbd_cloth_spike -m run.test=pinch run.pinch_qpos=0.001,0.003,0.006
    python -m tests.pbd_cloth_spike run.bench_steps=100        # per-step cost
    python -m tests.pbd_cloth_spike run.viewer=true run.keep_open=true

Prints one `pbd_cloth_spike <test>` summary line per test, plus sampled lines
under `run.verbose=true`. Every per-step line is flushed, so a native crash still
leaves the state it died at on stdout.
"""

from __future__ import annotations

import os
from pathlib import Path

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.primitives.attachment import ParticleAttachment
from topogym.primitives.pick_place import HAND_TO_PAD_Z
from topogym.supervision import stop_before_physics
from topogym.utils import initialize_franka_controller
from topogym.world import StandardTabletopSceneBuilder, materials


def _as_numpy(value) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu().numpy()
    return np.asarray(value)


def particles(cloth) -> np.ndarray:
    positions = _as_numpy(cloth.get_particles_pos())
    if positions.ndim == 3:
        positions = positions[0]
    return np.asarray(positions, dtype=float)


def velocities(cloth) -> np.ndarray:
    values = _as_numpy(cloth.get_particles_vel())
    if values.ndim == 3:
        values = values[0]
    return np.asarray(values, dtype=float)


def grid_mesh(size, center, z, cols: int, rows: int, path: Path):
    """A flat rectangular triangle grid, written as OBJ.

    Same construction as the legacy peeling film (`tasks/legacy/peeling_physical.py`
    `cloth_mesh`) minus its peel-corner blending, which this does not need. It is
    only the CONTROL mesh: Genesis remeshes it isotropically to
    ``PBDOptions.particle_size``, so the particle count is usually larger.
    """

    xs = np.linspace(-0.5 * float(size[0]), 0.5 * float(size[0]), int(cols))
    ys = np.linspace(-0.5 * float(size[1]), 0.5 * float(size[1]), int(rows))
    vertices = np.array(
        [[float(center[0]) + x, float(center[1]) + y, float(z)] for y in ys for x in xs],
        dtype=float,
    )
    faces = []
    for row in range(int(rows) - 1):
        for col in range(int(cols) - 1):
            lower_left = row * int(cols) + col
            lower_right = lower_left + 1
            upper_left = (row + 1) * int(cols) + col
            upper_right = upper_left + 1
            faces.append([lower_left, lower_right, upper_right])
            faces.append([lower_left, upper_right, upper_left])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for vertex in vertices:
            handle.write(f"v {vertex[0]:.6f} {vertex[1]:.6f} {vertex[2]:.6f}\n")
        for face in faces:
            handle.write(f"f {face[0] + 1} {face[1] + 1} {face[2] + 1}\n")
    return vertices, np.asarray(faces, dtype=int)


class Watchdog:
    """Blow-up detector, shared by every test.

    Records rather than defends: the point of the spike is to find the conditions
    that trip it. The production task turns the same four signals into an episode
    that is marked failed so it never reaches the dataset.
    """

    def __init__(self, cfg, cloth, table_z: float, *, reference: float = 0.0) -> None:
        self.cloth = cloth
        self.table_z = float(table_z)
        self.max_step_disp = float(cfg.run.max_step_disp)
        self.disp_ratio = float(cfg.run.disp_ratio)
        # Metres the DRIVER moves per step in this test: the commanded drag speed
        # where there is one, 0 where the test commands nothing.
        self.reference = float(reference)
        self.max_speed = float(cfg.run.max_speed)
        self.min_z_below = float(cfg.run.min_z_below)
        self._previous = particles(cloth)
        self.worst_step_disp = 0.0
        self.worst_speed = 0.0
        self.lowest_z = float("inf")
        self.tripped: str | None = None

    def limit(self) -> float:
        """The step-displacement a particle is allowed, for this test's drive rate.

        A fixed number cannot separate "moving fast because we commanded it" from
        "diverging": the 2026-08-17 sweep dragged the hand at 8 mm a step, so
        every particle legitimately moved ~8 mm, and a 20 mm ceiling could never
        fire while a 3 mm ceiling would fire on every run. What divergence
        actually means is the material outrunning its driver, so the ceiling is a
        multiple of the commanded motion, with an absolute floor for the tests
        that command nothing (settle) or almost nothing (contact).
        """

        return max(self.max_step_disp, self.disp_ratio * self.reference)

    def check(self, step: int) -> str | None:
        current = particles(self.cloth)
        if not np.all(np.isfinite(current)):
            self.tripped = f"nan_at_step={step}"
            return self.tripped
        disp = float(np.max(np.linalg.norm(current - self._previous, axis=1)))
        speed = float(np.max(np.linalg.norm(velocities(self.cloth), axis=1)))
        low = float(current[:, 2].min()) - self.table_z
        self._previous = current
        self.worst_step_disp = max(self.worst_step_disp, disp)
        self.worst_speed = max(self.worst_speed, speed)
        self.lowest_z = min(self.lowest_z, low)
        ceiling = self.limit()
        if disp > ceiling:
            self.tripped = f"step_disp={disp:.4f}>{ceiling:.4f}@{step}"
        elif speed > self.max_speed:
            self.tripped = f"speed={speed:.3f}>{self.max_speed:.3f}@{step}"
        elif low < self.min_z_below:
            self.tripped = f"below_table={low:.4f}<{self.min_z_below:.4f}@{step}"
        return self.tripped

    def summary(self) -> str:
        return (
            f"worst_step_disp={self.worst_step_disp:.5f} "
            f"disp_limit={self.limit():.5f} "
            f"worst_speed={self.worst_speed:.3f} "
            f"lowest_z_above_table={self.lowest_z:+.5f} "
            f"blowup={self.tripped or 'none'}"
        )


def flatness(cloth, table_z: float) -> tuple[float, float]:
    """(height-field variance, peak height) of the sheet above the table.

    docx 1.1 uses flatness as the constraint that separates a real fold from
    crumpling the cloth into a ball, and 1.2 uses peak height to separate an
    unfolded pleat from a flattened one. Both need this baseline to have a number.
    """

    z = particles(cloth)[:, 2] - float(table_z)
    return float(np.var(z)), float(z.max())


def rest_graph(nodes: np.ndarray, neighbours: int = 4):
    """Nearest-neighbour pairs of the SIMULATED particles, and their rest lengths.

    Built from the particles themselves rather than from the control mesh's
    triangles, because Genesis remeshes: the 2026-08-17 run put 1089 control
    vertices in and got 1398 particles out, so control-mesh edge indices address
    whatever particle happens to sit at that number. The first version of this
    test did exactly that and its `worst_edge_strain` was measuring nothing --
    the guard for it only caught the case where remeshing REDUCED the count.

    Indices are stable within one run, so a graph captured at rest stays valid
    for the whole test. Symmetric duplicates are removed.
    """

    delta = nodes[:, None, :] - nodes[None, :, :]
    distance = np.linalg.norm(delta, axis=2)
    np.fill_diagonal(distance, np.inf)
    nearest = np.argsort(distance, axis=1)[:, : int(neighbours)]
    rows = np.repeat(np.arange(len(nodes)), int(neighbours))
    pairs = np.sort(np.stack([rows, nearest.reshape(-1)], axis=1), axis=1)
    pairs = np.unique(pairs, axis=0)
    lengths = np.linalg.norm(nodes[pairs[:, 0]] - nodes[pairs[:, 1]], axis=1)
    return pairs, lengths


def edge_strain(nodes: np.ndarray, pairs: np.ndarray, rest: np.ndarray) -> float:
    """Worst relative stretch over the rest graph.

    The crease proxy for the weld test: a hard weld cannot bend inside the held
    patch, so the deformation piles onto the ring of pairs at its boundary and
    shows up here before it shows up anywhere visual.
    """

    lengths = np.linalg.norm(nodes[pairs[:, 0]] - nodes[pairs[:, 1]], axis=1)
    return float(np.max(np.abs(lengths - rest) / np.maximum(rest, 1e-9)))


def remesh_report(control: np.ndarray, simulated: np.ndarray) -> str:
    """Did Genesis keep the input vertices, in order, at the front?

    Worth a line of its own because the answer reaches far past this spike. Every
    judge in docx 1.1-1.3 that names a MATERIAL point -- where the fold line
    ended up, which layer a particle belongs to, "total spread length ~= material
    length" -- needs to follow the same piece of cloth over time. If the ordering
    is not preserved, those judges need a different way to establish material
    identity, and that is a task-design problem, not a spike problem.
    """

    if len(simulated) < len(control):
        return (
            f"order_preserved=NO control={len(control)} simulated={len(simulated)} "
            "(fewer particles than input vertices)"
        )
    head = simulated[: len(control)]
    offset = float(np.max(np.linalg.norm(head - control, axis=1)))
    return (
        f"order_preserved={'yes' if offset < 1e-6 else 'NO'} "
        f"control={len(control)} simulated={len(simulated)} "
        f"max_offset_mm={offset * 1e3:.3f}"
    )


def weld_indices(nodes: np.ndarray, center, radius: float):
    """Particles inside the weld disc, and their tapered grip weights.

    The taper is the whole point: `ParticleAttachment`'s own notes record that
    driving every held particle absolutely makes the patch a rigid splint, which
    pinned a 4 mm rope's bend radius at 6-9 mm and drove Genesis' rest-distance
    self-collision rule into firing inside the material. Weight 1 at the centre
    falling to 0 at the rim removes the discontinuity.
    """

    offsets = nodes[:, :2] - np.asarray(center, dtype=float)[:2]
    distance = np.linalg.norm(offsets, axis=1)
    indices = np.flatnonzero(distance <= float(radius))
    if indices.size == 0:
        raise SystemExit(
            f"weld_radius={radius} caught no particles; the cloth's particle "
            "spacing is larger than the disc."
        )
    weights = 1.0 - distance[indices] / max(float(radius), 1e-9)
    return indices, np.clip(weights, 0.0, 1.0)


def hand_for(point) -> np.ndarray:
    return np.asarray(point, dtype=float) + np.array([0.0, 0.0, HAND_TO_PAD_Z])


def glide(controller, target, *, quat, steps: int, sync=None) -> None:
    """Move the hand there over ``steps``, one IK solve per step.

    Interpolated rather than a single `move_ee_to(steps=N)`, which solves once for
    a distant target and then holds it: the arm crosses the whole gap as fast as
    the controller can drive it. Near cloth that is itself a disturbance, and it
    would be one this spike could not tell apart from the effect it is measuring.
    """

    begin = np.asarray(controller.hand_pos(), dtype=float)
    target = np.asarray(target, dtype=float)
    steps = max(1, int(steps))
    for index in range(1, steps + 1):
        alpha = index / steps
        controller.move_ee_to(
            (1.0 - alpha) * begin + alpha * target,
            quat=quat,
            steps=1,
            continuous_ik=True,
        )
        if sync is not None:
            sync()


# --------------------------------------------------------------------- tests


def run_settle(cfg, ctx) -> None:
    """Leave it alone. Flatness baseline, self-drift, and resting cost."""

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    dog = Watchdog(cfg, cloth, table_z)
    start = particles(cloth)
    steps = int(cfg.run.settle_steps)
    for step in range(1, steps + 1):
        scene.step()
        tripped = dog.check(step)
        if verbose and step % max(1, int(cfg.run.sample_every)) == 0:
            variance, peak = flatness(cloth, table_z)
            print(
                f"[cloth_settle step={step:4d}] var={variance:.3e} "
                f"peak={peak:.5f} {dog.summary()}",
                flush=True,
            )
        if tripped:
            break
    variance, peak = flatness(cloth, table_z)
    drift = float(np.linalg.norm(particles(cloth).mean(axis=0) - start.mean(axis=0)))
    # Did gravity ever act on this sheet? The 2026-08-17 run read every motion
    # quantity as exactly zero, which is equally consistent with "spawned at its
    # resting height, nothing to do" and with "not simulated at all" -- and those
    # two have completely different consequences for the task. `ctx.spawn_peak`
    # is the height before ANY stepping, so the drop is visible even though the
    # presettle happens before this test.
    fell = ctx.spawn_peak - peak
    print(
        f"pbd_cloth_spike settle steps={steps} particles={len(start)} "
        f"flatness_var={variance:.3e} peak_above_table={peak:.5f} "
        f"centroid_drift_mm={drift * 1e3:.3f} "
        f"spawn_peak={ctx.spawn_peak:.5f} fell_mm={fell * 1e3:.2f} "
        f"gravity={'fell' if fell > 1e-4 else 'STATIC(spawn==rest? or not simulated)'} "
        f"{dog.summary()}",
        flush=True,
    )


def run_contact(cfg, ctx) -> None:
    """Close the fingers and walk them down onto the cloth.

    The one test that needs the arm to actually reach the cloth, and the one that
    may not return: on 1.1.0 this path segfaulted. Every step is flushed with the
    clearance it reached, so a crash still says where it happened.
    """

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    controller = ctx.controller
    if controller is None:
        raise SystemExit("run.test=contact needs the robot; it was built without one.")

    surface = float(particles(cloth)[:, 2].max())
    above = np.asarray(ctx.grasp_point, dtype=float).copy()
    above[2] = surface + float(cfg.run.contact_start_clearance)

    controller.set_gripper(0.0, steps=int(cfg.task.physical.gripper_steps))
    glide(
        controller,
        hand_for(above),
        quat=ctx.ee_quat,
        steps=int(cfg.task.physical.move_steps),
    )
    # After staging, not before: the watchdog's per-step displacement is measured
    # against the previous sample, and the approach itself would otherwise show up
    # as one enormous first step.
    dog = Watchdog(
        cfg, cloth, table_z, reference=float(cfg.run.contact_step) / 4.0
    )
    print(
        f"pbd_cloth_spike contact staged clearance="
        f"{float(cfg.run.contact_start_clearance):.4f} "
        f"fingers_closed=True cloth_top={surface:.5f}",
        flush=True,
    )

    clearance = float(cfg.run.contact_start_clearance)
    step_size = float(cfg.run.contact_step)
    floor = float(cfg.run.contact_min_clearance)
    reached = clearance
    step = 0
    while clearance > floor:
        clearance = max(floor, clearance - step_size)
        target = above.copy()
        target[2] = surface + clearance
        controller.move_ee_to(
            hand_for(target), quat=ctx.ee_quat, steps=4, continuous_ik=True
        )
        step += 1
        # Recorded, NOT a break. This test's question is "does the process
        # survive", so it has to keep descending to the floor even after the
        # cloth starts moving hard; stopping at the first trip would answer a
        # different question and hide the clearance the fingers actually reached.
        dog.check(step)
        reached = clearance
        # Flushed every step ON PURPOSE: if the process dies inside Genesis this
        # line is the whole record of how close it got.
        print(
            f"[cloth_contact step={step:3d}] clearance={clearance:.4f} "
            f"pad_z={float(controller.hand_pos()[2]) - HAND_TO_PAD_Z:.5f} "
            f"{dog.summary()}",
            flush=True,
        )
    print(
        f"pbd_cloth_spike contact survived=True reached_clearance={reached:.4f} "
        f"steps={step} {dog.summary()}",
        flush=True,
    )


def run_pinch(cfg, ctx) -> None:
    """Close the fingers ON the cloth. The squeeze case, which nothing else covers.

    Interpenetration blows a PBD body up two ways, and only one of them has been
    ruled out. Tunnelling -- something crossing the cloth in a single step -- needs
    the driver to move more than half a particle per substep, and the 2026-08-17
    sweep showed the demo speeds are an order of magnitude under that. The other
    way is a squeeze: two fingers close to a gap narrower than the cloth, the
    particles between them have no legal position at all, and the solver answers
    with a correction that grows without bound. `contact` never tested it -- it
    descends with the fingers ALREADY closed and never closes them on anything.

    So this is the mechanism most likely to be behind the crash that started this
    whole line of work, and it is the one that turns the "closing gap must be at
    least one cloth thickness" guard rail from a derivation into a measurement.

    Sweep `run.pinch_qpos` across `cloth.particle_size / 2` (the half-gap at which
    the pads exactly touch a one-particle-thick sheet) and find where it goes.
    """

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    controller = ctx.controller
    if controller is None:
        raise SystemExit("run.test=pinch needs the robot; it was built without one.")

    qpos = float(cfg.run.pinch_qpos)
    half_thickness = 0.5 * float(cfg.task.cloth.particle_size)
    nodes = particles(cloth)
    # Pads straddling the sheet, not hovering above it: this is the one test that
    # is SUPPOSED to have cloth between the fingers.
    centre = np.asarray(ctx.grasp_point, dtype=float).copy()
    centre[2] = float(nodes[:, 2].max())
    controller.open_gripper(int(cfg.task.physical.gripper_steps))
    glide(
        controller,
        hand_for(centre),
        quat=ctx.ee_quat,
        steps=int(cfg.task.physical.move_steps),
    )
    dog = Watchdog(cfg, cloth, table_z)

    steps = max(1, int(cfg.task.physical.gripper_steps))
    print(
        f"pbd_cloth_spike pinch staging qpos={qpos:.4f} "
        f"half_thickness={half_thickness:.4f} "
        f"ratio={qpos / max(half_thickness, 1e-9):.2f} pads_at={centre[2]:.5f}",
        flush=True,
    )
    controller.set_gripper(qpos, steps=steps)
    dog.check(0)
    # Hold closed: a squeeze does not diverge on the closing step, it diverges
    # while the solver keeps failing to satisfy a constraint set with no solution.
    hold = max(1, int(cfg.run.pinch_hold_steps))
    for index in range(1, hold + 1):
        scene.step()
        tripped = dog.check(index)
        if verbose and index % max(1, int(cfg.run.sample_every)) == 0:
            print(f"[cloth_pinch step={index:4d}] {dog.summary()}", flush=True)
        if tripped:
            break
    variance, peak = flatness(cloth, table_z)
    print(
        f"pbd_cloth_spike pinch qpos={qpos:.4f} half_thickness={half_thickness:.4f} "
        f"ratio={qpos / max(half_thickness, 1e-9):.2f} hold_steps={hold} "
        f"flatness_var={variance:.3e} peak_above_table={peak:.5f} "
        f"{dog.summary()}",
        flush=True,
    )


def run_speed(cfg, ctx) -> None:
    """Attach a patch, lift it, drag it, and see what speed the sheet tolerates."""

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    controller = ctx.controller
    attachment, offsets, weights = ctx.attach(cfg, taper=bool(cfg.run.taper))
    # After the attach staging, so the approach is not counted as one huge step.
    dog = Watchdog(cfg, cloth, table_z, reference=float(cfg.run.drag_speed))

    speed = float(cfg.run.drag_speed)
    distance = float(cfg.run.drag_distance)
    lift = float(cfg.run.lift_delta)
    steps = max(1, int(round((distance + lift) / max(speed, 1e-9))))
    start = np.asarray(controller.hand_pos(), dtype=float)
    # Up first, then across: the same lift-move shape the fold task will use.
    lift_steps = max(1, int(round(lift / max(speed, 1e-9))))
    drag_steps = max(1, steps - lift_steps)

    def advance(target, count, label):
        begin = np.asarray(controller.hand_pos(), dtype=float)
        for index in range(1, count + 1):
            alpha = index / count
            controller.move_ee_to(
                (1.0 - alpha) * begin + alpha * np.asarray(target, dtype=float),
                quat=ctx.ee_quat,
                steps=1,
                continuous_ik=True,
            )
            attachment.sync()
            tripped = dog.check(index)
            if verbose and index % max(1, int(cfg.run.sample_every)) == 0:
                print(f"[cloth_{label} step={index:4d}] {dog.summary()}", flush=True)
            if tripped:
                return False
        return True

    ok = advance(start + np.array([0.0, 0.0, lift]), lift_steps, "lift")
    if ok:
        ok = advance(
            np.asarray(controller.hand_pos(), dtype=float)
            + np.array([-distance, 0.0, 0.0]),
            drag_steps,
            "drag",
        )
    variance, peak = flatness(cloth, table_z)
    substep_dt = float(cfg.env.sim.dt) / max(1, int(cfg.env.sim.substeps))
    print(
        f"pbd_cloth_spike speed drag_speed={speed:.4f} "
        f"m_per_substep={speed / max(1, int(cfg.env.sim.substeps)):.5f} "
        f"tunnel_threshold={float(cfg.task.cloth.particle_size) / 2:.5f} "
        f"substep_dt={substep_dt:.5f} taper={bool(cfg.run.taper)} "
        f"welded={len(offsets)} completed={ok} "
        f"flatness_var={variance:.3e} {dog.summary()}",
        flush=True,
    )


def run_weld(cfg, ctx) -> None:
    """Tapered weld against a hard one, on the same lift.

    Reports the worst edge strain, which is where a rigid splint shows up first:
    the held patch cannot bend, so the whole demand lands on the ring of edges at
    its boundary.
    """

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    controller = ctx.controller
    taper = bool(cfg.run.taper)
    attachment, offsets, weights = ctx.attach(cfg, taper=taper)
    # After the attach staging, so the approach is not counted as one huge step.
    dog = Watchdog(cfg, cloth, table_z, reference=float(cfg.run.drag_speed))

    pairs, rest = ctx.rest_pairs, ctx.rest_lengths

    lift = float(cfg.run.lift_delta)
    speed = float(cfg.run.drag_speed)
    count = max(1, int(round(lift / max(speed, 1e-9))))
    start = np.asarray(controller.hand_pos(), dtype=float)
    worst_strain = 0.0
    for index in range(1, count + 1):
        alpha = index / count
        controller.move_ee_to(
            start + np.array([0.0, 0.0, lift * alpha]),
            quat=ctx.ee_quat,
            steps=1,
            continuous_ik=True,
        )
        attachment.sync()
        tripped = dog.check(index)
        worst_strain = max(worst_strain, edge_strain(particles(cloth), pairs, rest))
        if verbose and index % max(1, int(cfg.run.sample_every)) == 0:
            print(
                f"[cloth_weld step={index:4d}] worst_edge_strain={worst_strain:.4f} "
                f"{dog.summary()}",
                flush=True,
            )
        if tripped:
            break
    variance, peak = flatness(cloth, table_z)
    print(
        f"pbd_cloth_spike weld taper={taper} welded_particles={len(offsets)} "
        f"weight_min={float(weights.min()) if weights is not None else 1.0:.3f} "
        f"worst_edge_strain={worst_strain:.4f} rest_pairs={len(pairs)} "
        f"flatness_var={variance:.3e} peak_above_table={peak:.5f} "
        f"{dog.summary()}",
        flush=True,
    )


TESTS = {
    "settle": run_settle,
    "pinch": run_pinch,
    "contact": run_contact,
    "speed": run_speed,
    "weld": run_weld,
}
# `contact` is excluded on purpose: a segfault there would take everything queued
# behind it down unmeasured.
# `pinch` is last in ALL: it is the one that squeezes, so it is the likeliest
# of these four to diverge, and anything queued behind a diverging cell wastes
# its build time. `contact` stays out entirely -- see above.
ALL = ("settle", "weld", "speed", "pinch")


class _Context:
    def __init__(
        self, cfg, scene, cloth, controller, table_z, grasp_point, ee_quat,
        rest_pairs, rest_lengths,
    ):
        self.cfg = cfg
        self.scene = scene
        self.cloth = cloth
        self.controller = controller
        self.table_z = table_z
        self.grasp_point = grasp_point
        self.ee_quat = ee_quat
        self.rest_pairs = rest_pairs
        self.rest_lengths = rest_lengths
        # Peak height before any stepping; set by `main` right after build.
        self.spawn_peak = 0.0
        self.verbose = bool(cfg.run.verbose)

    def attach(self, cfg, *, taper: bool):
        """Weld the patch under the hand, the way the production primitive does.

        Two properties are copied from `PBDParticleAttachmentDragPrimitive`
        deliberately: the pads stop `touch_clearance` ABOVE the cloth (nothing
        ever touches it), and `ParticleAttachment` carries the attach offset so
        the patch follows the hand's MOTION instead of being teleported onto it
        on the first sync -- a 13 mm jump in one 10 ms step is 1.3 m/s handed to
        a patch whose neighbours are at rest.
        """

        controller = self.controller
        if controller is None:
            raise SystemExit("this test needs the robot; it was built without one.")
        nodes = particles(self.cloth)
        indices, weights = weld_indices(
            nodes, self.grasp_point, float(cfg.task.grasp.weld_radius)
        )
        clearance = float(cfg.task.grasp.touch_clearance)
        touch = np.asarray(self.grasp_point, dtype=float).copy()
        touch[2] = float(nodes[indices, 2].max()) + clearance
        controller.open_gripper(int(cfg.task.physical.gripper_steps))
        glide(
            controller,
            hand_for(touch),
            quat=self.ee_quat,
            steps=int(cfg.task.physical.move_steps),
        )
        attachment = ParticleAttachment(
            entity=self.cloth,
            indices=indices,
            parent_pos_fn=controller.hand_pos,
            offset=(0.0, 0.0, -(HAND_TO_PAD_Z + clearance)),
            weights=(weights if taper else None),
        )
        attachment.attach()
        print(
            f"pbd_cloth_spike attach welded={len(indices)} taper={taper} "
            f"weld_radius={float(cfg.task.grasp.weld_radius):.4f} "
            f"touch_clearance={clearance:.4f} "
            f"attach_offset_mm="
            f"{float(np.linalg.norm(attachment.anchor_offset)) * 1e3:.2f}",
            flush=True,
        )
        return attachment, indices, (weights if taper else None)


@hydra.main(version_base="1.3", config_path="../configs", config_name="pbd_cloth_spike")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"pbd_cloth_spike_config -> {resolved}", flush=True)

    selected = str(cfg.run.test)
    names = list(ALL) if selected == "all" else [selected]
    if any(name not in TESTS for name in names):
        raise SystemExit(
            f"Unknown run.test={selected!r}; expected one of {list(TESTS)} or 'all'."
        )

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(
        backend=backends[str(cfg.env.genesis.backend)],
        precision=str(cfg.env.genesis.precision),
    )

    cloth_cfg = cfg.task.cloth
    builder = StandardTabletopSceneBuilder(
        cfg.env,
        cfg.robot_control,
        pbd_options=gs.options.PBDOptions(
            particle_size=float(cloth_cfg.particle_size)
        ),
    )
    tabletop = builder.create(show_viewer=show_viewer, include_robot=True)
    scene = tabletop.scene
    origin = np.asarray(tabletop.frames.task_origin, dtype=float)
    table_z = float(origin[2])

    path = Path(str(cloth_cfg.mesh.output_dir)) / "cloth_fold_sheet.obj"
    # Faces go into the OBJ; only the vertices are needed here, for the remesh
    # probe. The strain proxy is built from the simulated particles instead.
    vertices, _faces = grid_mesh(
        list(cloth_cfg.size),
        origin[:2] + np.asarray(list(cloth_cfg.center), dtype=float),
        table_z + float(cloth_cfg.z),
        int(cloth_cfg.mesh.cols),
        int(cloth_cfg.mesh.rows),
        path,
    )
    cloth = scene.add_entity(
        gs.morphs.Mesh(
            file=str(path),
            pos=(0.0, 0.0, 0.0),
            scale=1.0,
            decimate=False,
            convexify=False,
            fixed=False,
            file_meshes_are_zup=True,
        ),
        material=gs.materials.PBD.Cloth(
            rho=float(cloth_cfg.rho),
            static_friction=float(cloth_cfg.static_friction),
            kinetic_friction=float(cloth_cfg.kinetic_friction),
            stretch_compliance=float(cloth_cfg.stretch_compliance),
            bending_compliance=float(cloth_cfg.bending_compliance),
            stretch_relaxation=float(cloth_cfg.stretch_relaxation),
            bending_relaxation=float(cloth_cfg.bending_relaxation),
            air_resistance=float(cloth_cfg.air_resistance),
        ),
        surface=materials.plastic("deformable", list(cloth_cfg.color), vis_mode="visual"),
        name=str(cloth_cfg.name),
    )
    tabletop.manifest.add(str(cloth_cfg.name), cloth)
    builder.finalize(tabletop)

    controller = initialize_franka_controller(
        scene=scene, manifest=tabletop.manifest, robot_cfg=cfg.robot_control, settle_steps=0
    )
    ee_quat = controller.default_ee_quat

    # Grasp the right edge's midpoint, which is where docx 1.1 puts the pinch.
    grasp_point = origin + np.array(
        [
            float(cloth_cfg.center[0]) + 0.5 * float(cloth_cfg.size[0]) - 0.010,
            float(cloth_cfg.center[1]),
            float(cloth_cfg.z),
        ]
    )
    substep_dt = float(cfg.env.sim.dt) / max(1, int(cfg.env.sim.substeps))
    print(
        f"pbd_cloth_spike setup control_vertices={len(vertices)} "
        f"simulated_particles={len(particles(cloth))} "
        f"particle_size={float(cloth_cfg.particle_size):.4f} "
        f"size={list(cloth_cfg.size)} dt={float(cfg.env.sim.dt):.4f} "
        f"substeps={int(cfg.env.sim.substeps)} substep_dt={substep_dt:.5f} "
        f"tests={names}",
        flush=True,
    )
    # Can a material point be followed at all? Reported before any stepping, and
    # reported unconditionally: the answer governs far more than this spike.
    print(
        f"pbd_cloth_spike remesh {remesh_report(vertices, particles(cloth))}",
        flush=True,
    )
    if stop_before_physics(cfg, scene, "pbd_cloth_spike"):
        raise SystemExit(0)

    # Where the sheet is BEFORE anything steps, so the settle test can say
    # whether it ever fell rather than only where it ended up.
    spawn_peak = flatness(cloth, table_z)[1]

    # Let the sheet land before anything is measured. It spawns `cloth.z` above
    # the table and drops; without this every test's first samples are that drop,
    # and `weld`'s rest lengths would be taken mid-fall.
    presettle = max(0, int(cfg.run.presettle_steps))
    for _ in range(presettle):
        scene.step()
    variance, peak = flatness(cloth, table_z)
    print(
        f"pbd_cloth_spike presettle steps={presettle} "
        f"flatness_var={variance:.3e} peak_above_table={peak:.5f} "
        f"lowest_above_table={float(particles(cloth)[:, 2].min()) - table_z:+.5f} "
        f"spawn_peak={spawn_peak:.5f} fell_mm={(spawn_peak - peak) * 1e3:.2f}",
        flush=True,
    )

    # Rest graph for the weld test's strain proxy: taken from the SIMULATED
    # particles once they have settled, so it survives Genesis' remeshing.
    rest_pairs, rest_lengths = rest_graph(
        particles(cloth), int(cfg.run.rest_neighbours)
    )
    print(
        f"pbd_cloth_spike rest_graph pairs={len(rest_pairs)} "
        f"median_rest_mm={float(np.median(rest_lengths)) * 1e3:.2f} "
        f"neighbours={int(cfg.run.rest_neighbours)}",
        flush=True,
    )

    context = _Context(
        cfg, scene, cloth, controller, table_z, grasp_point, ee_quat,
        rest_pairs, rest_lengths,
    )
    context.spawn_peak = spawn_peak
    for name in names:
        TESTS[name](cfg, context)

    while cfg.run.keep_open and show_viewer:
        scene.step()


if __name__ == "__main__":
    main()
