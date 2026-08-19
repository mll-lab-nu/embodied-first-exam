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
- ``grip``    Four ways of holding the cloth, compared on one straight lift:
               how much of the commanded height the cloth actually follows, and
               how much the material has to stretch to pay for it. Measured
               2026-08-19: the default hold followed only four tenths.
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
    python -m tests.pbd_cloth_spike -m run.test=grip task.grasp.attach_mode=overwrite_graded,link_patch,link_single
    python -m tests.pbd_cloth_spike -m run.test=speed run.drag_speed=0.004,0.012,0.024
    python -m tests.pbd_cloth_spike -m run.test=pinch run.pinch_qpos=0.001,0.003,0.006
    python -m tests.pbd_cloth_spike run.bench_steps=100        # per-step cost
    python -m tests.pbd_cloth_spike run.viewer=true run.keep_open=true
    python -m tests.pbd_cloth_spike run.test=fold recording=hq recording.path=runs/videos/cloth_fold.mp4

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
from topogym.utils import (
    apply_recording_camera_overrides,
    initialize_franka_controller,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.world import StandardTabletopSceneBuilder, materials
from topogym.verification.cloth_fold_verifier import ClothFoldEvaluator
from topogym.world.rope import TabletopParticleFriction


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


class Grip:
    """One way of making the cloth follow the gripper, behind one interface.

    Four of them, because which one to use is a measurement and not an argument.
    They differ along two axes:

    HOW the particles are made to follow ---------------------------------------
    ``overwrite``  the solver runs a step, then we set those particles' positions
                   from Python. The solver never learns they are held, so it goes
                   on trying to move them and their neighbours receive
                   contradictory pushes. This is what `ParticleAttachment` does.
    ``link``       `fix_particles_to_link` tells the solver, before it runs, that
                   these particles ride a rigid body. The constraint is inside the
                   solve, and it carries the body's rotation too. It is what the
                   rope tasks have always used (`rope_backends/pbd.py`), and it is
                   the same idea as SoftGym's picker giving its held particle
                   infinite mass.

    HOW MANY, and how hard ------------------------------------------------------
    ``graded``     every particle in the disc, each held only as hard as its
                   distance from the centre allows (1 at the middle, 0 at the rim).
                   Measured 2026-08-19: the hand rose 40 mm and the cloth 16.4,
                   because the average hold is about a third.
    ``patch``      every particle in the disc, each held completely.
    ``single``     only the nearest particle, held completely -- SoftGym's own
                   configuration.
    """

    def __init__(self, mode: str, entity, indices, attachment=None) -> None:
        self.mode = str(mode)
        self.entity = entity
        self.indices = np.asarray(indices, dtype=int)
        self.attachment = attachment

    def sync(self) -> None:
        # Nothing to do for the `link` modes: the solver is already carrying them.
        if self.attachment is not None:
            self.attachment.sync()

    def release(self) -> None:
        if self.attachment is not None:
            self.attachment.release(sync=False)
        else:
            self.entity.release_particle(particles_idx_local=list(self.indices))


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
        # Metres the DRIVER moves per step right now: the commanded rate while
        # something is carrying the cloth, 0 where the test commands nothing.
        # Settable mid-run, because the regime changes -- see `set_reference`.
        self.reference = float(reference)
        self.max_speed = float(cfg.run.max_speed)
        self.min_z_below = float(cfg.run.min_z_below)
        # A copy, not the array itself. `np.asarray` does not copy an array
        # that is already float64, so if the backend ever handed back a view
        # of live memory, `_previous` would track it and every displacement
        # would read as zero -- the detector silently doing nothing, which is
        # the one failure it must not have.
        self._previous = np.array(particles(cloth), copy=True)
        self.worst_step_disp = 0.0
        self.worst_speed = 0.0
        self.lowest_z = float("inf")
        # FIRST trip only. It used to be overwritten by every later one, so the
        # 2026-08-19 fold reported `@1201` when it first went over at 1191 -- the
        # summary said nothing about when things actually started going wrong.
        self.tripped: str | None = None
        self.tripped_phase: str | None = None
        self.phase: str = "start"

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

    def set_reference(self, reference: float, phase: str) -> None:
        """Change the drive rate the limit is measured against, and say why.

        A single constant cannot serve a whole episode. While the hand carries
        the cloth the drive rate is the hand's own step (0.36 mm on the 2026-08-19
        fold); once the cloth is let go there is no driver at all and it is simply
        falling, which is legitimately an order of magnitude faster. That run used
        the same 6 mm limit for both, so it could not have caught a divergence
        mid-fold (17x headroom) and it flagged the landing as one.
        """

        self.reference = float(reference)
        self.phase = str(phase)

    def check(self, step: int) -> str | None:
        current = particles(self.cloth)
        if not np.all(np.isfinite(current)):
            if self.tripped is None:
                self.tripped = f"nan_at_step={step}"
                self.tripped_phase = self.phase
            return self.tripped
        disp = float(np.max(np.linalg.norm(current - self._previous, axis=1)))
        speed = float(np.max(np.linalg.norm(velocities(self.cloth), axis=1)))
        low = float(current[:, 2].min()) - self.table_z
        self._previous = np.array(current, copy=True)
        self.worst_step_disp = max(self.worst_step_disp, disp)
        self.worst_speed = max(self.worst_speed, speed)
        self.lowest_z = min(self.lowest_z, low)
        if self.tripped is not None:
            return self.tripped
        ceiling = self.limit()
        if disp > ceiling:
            self.tripped = f"step_disp={disp:.4f}>{ceiling:.4f}@{step}"
        elif speed > self.max_speed:
            self.tripped = f"speed={speed:.3f}>{self.max_speed:.3f}@{step}"
        elif low < self.min_z_below:
            self.tripped = f"below_table={low:.4f}<{self.min_z_below:.4f}@{step}"
        if self.tripped is not None:
            self.tripped_phase = self.phase
        return self.tripped

    def summary(self) -> str:
        return (
            f"worst_step_disp={self.worst_step_disp:.5f} "
            f"disp_limit={self.limit():.5f} "
            f"worst_speed={self.worst_speed:.3f} "
            f"lowest_z_above_table={self.lowest_z:+.5f} "
            f"blowup={self.tripped or 'none'}"
            + ("" if self.tripped is None else f" blowup_phase={self.tripped_phase}")
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

    The crease proxy for the `grip` test: a patch whose every particle is held
    completely cannot bend at all, so the bending the motion demands piles onto
    the ring of material just outside it, and shows up here before it shows up
    anywhere visual.
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


def attached_indices(nodes: np.ndarray, center, radius: float, *, single: bool = False):
    """Which particles the gripper takes, and how hard it holds each one.

    The weights matter: `ParticleAttachment`'s own notes record that holding every
    particle completely leaves the patch unable to bend, which pinned a 4 mm
    rope's bend radius at 6-9 mm and drove Genesis' rest-distance self-collision
    rule into firing inside the material. Falling from 1 at the centre to 0 at
    the rim removes that edge, at the cost of holding weakly -- which is the
    trade the `grip` test measures.
    """

    offsets = nodes[:, :2] - np.asarray(center, dtype=float)[:2]
    distance = np.linalg.norm(offsets, axis=1)
    if single:
        indices = np.array([int(np.argmin(distance))])
        return indices, np.ones(1)
    indices = np.flatnonzero(distance <= float(radius))
    if indices.size == 0:
        raise SystemExit(
            f"attach_radius={radius} caught no particles; the cloth's particle "
            "spacing is larger than the disc."
        )
    weights = 1.0 - distance[indices] / max(float(radius), 1e-9)
    return indices, np.clip(weights, 0.0, 1.0)


def self_contact_gap(rest_nodes: np.ndarray, nodes: np.ndarray, radius: float) -> float:
    """Closest approach between particles that were NOT neighbours at rest.

    The physics-side twin of `layer_report`: two particles from far-apart parts of
    the sheet should never come closer than about one particle. Pairs that were
    already close at rest are excluded, because their closeness is the material,
    not a contact. Chunked over rows so the pairwise distances never have to
    exist all at once.
    """

    worst = float("inf")
    chunk = 256
    for start in range(0, len(nodes), chunk):
        stop = min(start + chunk, len(nodes))
        rest_d = np.linalg.norm(rest_nodes[start:stop, None, :] - rest_nodes[None, :, :], axis=2)
        live_d = np.linalg.norm(nodes[start:stop, None, :] - nodes[None, :, :], axis=2)
        live_d[rest_d <= radius] = np.inf
        worst = min(worst, float(live_d.min()))
    return worst


def grasp_and_target(cfg, origin, cloth_cfg):
    """Where to grab the sheet, and where that point has to end up.

    ``corner``   the corner furthest from the arm, folded onto the diagonally
                 opposite one -- the triangle fold, and the one a person does
                 first because a corner is the only part of a sheet lying flat
                 that a gripper can get under.
    ``edge_mid`` the near edge's midpoint, mirrored across the centre line -- a
                 half fold. What the 2026-08-18 run used.

    `grasp_inset` keeps the attached disc inside the material: centred exactly on a
    corner, half the disc would hang off the cloth and catch fewer particles on
    one side than the other, which tilts the patch as soon as it is lifted.
    """

    centre = np.asarray(origin, dtype=float)[:2] + np.asarray(
        list(cloth_cfg.center), dtype=float
    )
    half = 0.5 * np.asarray(list(cloth_cfg.size), dtype=float)
    inset = float(cfg.run.grasp_inset)
    mode = str(cfg.run.grasp_at)
    if mode == "corner":
        offset = np.array([half[0] - inset, half[1] - inset])
    elif mode == "edge_mid":
        offset = np.array([half[0] - inset, 0.0])
    else:
        raise SystemExit(
            f"run.grasp_at must be 'corner' or 'edge_mid', got {mode!r}."
        )
    z = float(origin[2]) + float(cloth_cfg.z)
    return (
        np.array([centre[0] + offset[0], centre[1] + offset[1], z]),
        np.array([centre[0] - offset[0], centre[1] - offset[1], z]),
    )


def cloth_state(nodes, rest, table_z: float, lift_threshold: float) -> str:
    """One line saying where the sheet is and what shape it is in.

    Printed at every phase boundary so a viewer session can be read back
    afterwards: the 2026-08-18 fold recorded only the first and last positions,
    which could not separate "carried away during the arc" from "skated after
    release".

    `moved_mean_mm` is the honest "did the sheet go somewhere" number -- the
    average distance every particle is from where it started. `lifted` counts
    what is actually off the table, which is how you see the difference between
    hinging one half over and picking the whole thing up.
    """

    lo, hi = nodes[:, :2].min(axis=0), nodes[:, :2].max(axis=0)
    above = nodes[:, 2] - table_z
    shift = np.linalg.norm(nodes[:, :2] - rest[:, :2], axis=1)
    return (
        f"bbox_x=[{lo[0]:+.3f},{hi[0]:+.3f}] bbox_y=[{lo[1]:+.3f},{hi[1]:+.3f}] "
        f"centroid=({nodes[:, 0].mean():+.3f},{nodes[:, 1].mean():+.3f}) "
        f"lifted={int((above > lift_threshold).sum())}/{len(nodes)} "
        f"top_mm={above.max() * 1e3:.1f} "
        f"moved_mean_mm={shift.mean() * 1e3:.1f} moved_max_mm={shift.max() * 1e3:.1f}"
    )


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


#: Which way the held corner is taken. `fold` is the task; the other two are the
#: wrong executions docx 1.1 names, kept here so the judges' thresholds have a
#: failure reference and not only a success one -- a threshold set from one side
#: is a guess.
MOTIONS = ("fold", "drag", "crumple")


def motion_target(motion: str, t: float, centre_xy, direction, radius: float, base):
    """Where the hand should be, a fraction ``t`` through the motion.

    ``fold``     half a turn about the fold line: the corner rises to the fold
                 line's height and comes down on the far side. The task.
    ``drag``     the same path in plan, but never leaving the surface. docx 1.1's
                 "sliding it along without lifting": the outline ends up in
                 roughly the right place while the sheet is pushed into wrinkles.
    ``crumple``  the corner is spiralled inward to the middle, staying low, so
                 the material gathers instead of folding. docx 1.1's "bunching it
                 up halves the area too" -- the case that coverage alone cannot
                 tell from a real fold, which is why flatness and layer count are
                 judged with it.
    """

    base = np.asarray(base, dtype=float)
    centre_xy = np.asarray(centre_xy, dtype=float)
    direction = np.asarray(direction, dtype=float)
    if motion == "fold":
        theta = np.pi * float(t)
        xy = centre_xy + direction * (radius * float(np.cos(theta)))
        return np.array([xy[0], xy[1], base[2] + radius * float(np.sin(theta))])
    if motion == "drag":
        theta = np.pi * float(t)
        xy = centre_xy + direction * (radius * float(np.cos(theta)))
        return np.array([xy[0], xy[1], base[2]])
    # crumple: one full turn inward, at the height it started from.
    angle = 2.0 * np.pi * float(t)
    reach = radius * (1.0 - float(t))
    turned = np.array(
        [
            direction[0] * np.cos(angle) - direction[1] * np.sin(angle),
            direction[0] * np.sin(angle) + direction[1] * np.cos(angle),
        ]
    )
    xy = centre_xy + turned * reach
    return np.array([xy[0], xy[1], base[2]])


def pinned_indices(nodes, centre_xy, direction, mode: str):
    """Particles held down on the table for the run, if any.

    A discriminator, not a feature. Two things can stop a sheet folding and they
    look identical from outside: the material may be too stiff to hinge, or
    nothing may be holding the far half down so the whole sheet is towed. Pinning
    the far half removes the second one. If it folds pinned, the material is fine
    and the work is on friction and weight; if it still will not fold, the
    material is the problem.

    ``far_half``    everything on the other side of the fold line
    ``far_quarter`` only the outer half of that -- closer to what friction over a
                    large area would do, and it leaves the material near the fold
                    line free to lift as the top layer lands on it
    """

    if mode == "none":
        return np.array([], dtype=int)
    along = (np.asarray(nodes, dtype=float)[:, :2] - centre_xy) @ direction
    if mode == "far_half":
        return np.flatnonzero(along < 0.0)
    if mode == "far_quarter":
        return np.flatnonzero(along < 0.5 * float(along.min()))
    raise SystemExit(
        f"run.pin must be none / far_half / far_quarter, got {mode!r}."
    )


def phase(cfg, ctx, name: str, dog=None) -> None:
    """Report the sheet's state, and hold here if this is the stop point.

    `run.stop_after=<name>` with a viewer freezes the run at that boundary and
    keeps stepping so the camera can be moved -- the same idea as the
    `debug_stop_after` markers the peeling primitives grew during their own
    native-crash hunt (`pbd_particle_pinch.py`). Headless it just exits, so a
    stop point left in a batch script cannot hang a queue.
    """

    nodes = particles(ctx.cloth)
    line = cloth_state(nodes, ctx.rest_nodes, ctx.table_z, float(cfg.run.lift_threshold))
    print(
        f"pbd_cloth_spike phase={name} {line}"
        + ("" if dog is None else f" {dog.summary()}"),
        flush=True,
    )
    if str(cfg.run.stop_after or "") != name:
        return
    if not ctx.show_viewer:
        print(
            f"pbd_cloth_spike stop_after={name}; headless, exiting here.", flush=True
        )
        raise SystemExit(0)
    print(
        f"pbd_cloth_spike stop_after={name}; holding the viewer. Ctrl+C to quit.",
        flush=True,
    )
    while True:
        ctx.scene.step()


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


def run_fold(cfg, ctx) -> None:
    """The task motion, split into phases you can stop at and look at.

    This is the one test that can still kill the PBD plan, and the 2026-08-18 run
    came back inconclusive: the sheet did not fold, it ended up flat and 372 mm
    away, so the question it exists to answer -- do two layers stay separate --
    was never reached. Two candidate causes could not be told apart from what was
    logged, which is why the motion is now cut into named phases with the sheet's
    state printed at each boundary:

      attached  the cloth is held, nothing has moved yet
      lifted    a PURE VERTICAL lift, no travel. If the whole sheet comes up
                here, the material is too stiff or too light and the arc is
                innocent -- this is the phase that separates those.
      apex      halfway across, at the top of the arc
      placed    back down on the far side, still held
      released  the cloth is let go
      done      after settling

    Stop at any of them with `run.stop_after=<phase> run.viewer=true`.
    """

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    controller = ctx.controller
    cloth_cfg = cfg.task.cloth
    particle_size = float(cloth_cfg.particle_size)
    cell = 2.0 * particle_size

    rest_nodes = ctx.rest_nodes
    # Optionally hold the far half down, to separate "the material cannot fold"
    # from "nothing is stopping the sheet being towed". See `pinned_indices`.
    pin_centre = np.asarray(ctx.origin, dtype=float)[:2] + np.asarray(
        list(cloth_cfg.center), dtype=float
    )
    pin_span = np.asarray(ctx.grasp_point, dtype=float)[:2] - pin_centre
    pinned = pinned_indices(
        rest_nodes, pin_centre, pin_span / max(float(np.linalg.norm(pin_span)), 1e-9),
        str(cfg.run.pin),
    )
    if len(pinned):
        cloth.fix_particles(particles_idx_local=[int(i) for i in pinned])
        print(
            f"pbd_cloth_spike pin mode={str(cfg.run.pin)} pinned={len(pinned)}"
            f"/{len(rest_nodes)}",
            flush=True,
        )

    grip = ctx.attach(cfg)
    dog = Watchdog(cfg, cloth, table_z)
    phase(cfg, ctx, "attached", dog)

    # The path is a ROTATION ABOUT THE FOLD LINE, not a translation with a height
    # curve bolted on. The cloth between the fold line and the grasped corner has
    # a fixed length, so the corner can only travel on the circle of that radius:
    # anywhere outside it the sheet is being stretched (and the rest of it gets
    # towed in), anywhere well inside it the sheet is slack and lies back down on
    # the table, where the hand then drags it sideways.
    #
    # The 2026-08-19 run did both at once. Its straight 40 mm lift put the hand
    # 147 mm from the fold line against 141.4 mm of available cloth -- 5.6 mm of
    # over-reach, which is why the cloth only rose 16.9 mm of a commanded 42 and
    # why it had already begun to slide. Its apex was 80 mm where the material
    # allows 141, so the folded-over half never left the table and got towed:
    # every particle moved 62.5 mm on average by the top of the arc.
    #
    # With the radius taken from the cloth instead of from two free parameters,
    # `fold_lift` and `fold_arc_height` stop existing -- they were never free.
    centre_xy = np.asarray(ctx.origin, dtype=float)[:2] + np.asarray(
        list(cloth_cfg.center), dtype=float
    )
    span = np.asarray(ctx.grasp_point, dtype=float)[:2] - centre_xy
    material = float(np.linalg.norm(span))
    if material < 1e-6:
        raise SystemExit("the grasp point is on the fold line; there is nothing to fold.")
    direction = span / material
    # A little inside the circle, so the cloth is carried rather than stretched.
    radius = material * float(cfg.run.fold_slack)
    base = np.asarray(controller.hand_pos(), dtype=float)
    # How fast, not how many. The calibration is a SPEED (3.6 mm a step, from the
    # 120/180/240 sweep on a 435 mm arc); a fixed step count turns into a
    # different speed the moment the arc changes length, and the edge-midpoint
    # fold docx 1.1 asks for has a 308 mm arc rather than the corner fold's 435.
    # `fold_steps` stays as an override so the sweep can still ask for a count.
    steps = (
        max(4, int(cfg.run.fold_steps))
        if cfg.run.fold_steps
        else max(4, int(round(np.pi * radius / float(cfg.run.fold_step_m))))
    )
    print(
        f"pbd_cloth_spike fold_path material_mm={material * 1e3:.1f} "
        f"radius_mm={radius * 1e3:.1f} apex_mm={radius * 1e3:.1f} "
        f"arc_len_mm={np.pi * radius * 1e3:.0f} steps={steps} "
        f"step_mm={np.pi * radius / steps * 1e3:.2f} "
        f"per_step_mm={np.pi * radius / steps * 1e3:.2f}",
        flush=True,
    )

    # Where the named stops fall on the half turn.
    # The fold's stops are named for what they are; the wrong executions have no
    # apex to speak of, so theirs are just progress markers.
    if str(cfg.run.motion) == "fold":
        names = ("lifted", "apex", "placed")       # 30 / 90 / 180 degrees
    else:
        names = ("q1", "mid", "placed")
    marks = {
        max(1, int(round(steps / 6))): names[0],
        max(2, int(round(steps / 2))): names[1],
        steps: names[2],
    }
    # What the cloth may legitimately do in one step, in ANY phase: fall. A point
    # released at the apex reaches sqrt(2*g*h) ~ 1.6 m/s, i.e. ~16 mm a step, and
    # gravity does not wait for the hand to let go -- the part of the sheet that
    # is not yet supported is already falling mid-carry.
    #
    # Deriving the ceiling from the HAND's rate instead is what aborted the
    # 600/1200-step folds and both wrong-motion runs (2026-08-20). The measured
    # reason: the cloth's peak speed does not drop when the hand slows down, it
    # RISES (0.41 / 0.79 / 0.99 m/s at 240 / 600 / 1200 steps) because a slower
    # carry leaves the unsupported part falling for longer. A hand-derived
    # ceiling therefore tightens exactly where the cloth is moving fastest.
    fall_step = float(
        np.sqrt(2.0 * abs(float(cfg.env.sim.gravity[2])) * max(radius, 1e-9))
    ) * float(cfg.env.sim.dt)
    dog.set_reference(fall_step, "carried")
    motion = str(cfg.run.motion)
    if motion not in MOTIONS:
        raise SystemExit(f"run.motion must be one of {sorted(MOTIONS)}, got {motion!r}.")
    completed = False
    for index in range(1, steps + 1):
        controller.move_ee_to(
            motion_target(motion, index / steps, centre_xy, direction, radius, base),
            quat=ctx.ee_quat,
            steps=1,
            continuous_ik=True,
        )
        grip.sync()
        tripped = dog.check(index)
        if verbose and index % max(1, int(cfg.run.sample_every)) == 0:
            print(
                f"[cloth_{motion} step={index:4d}] at={100.0 * index / steps:5.1f}% "
                f"{dog.summary()}",
                flush=True,
            )
        if index in marks:
            dog.phase = marks[index]
            phase(cfg, ctx, marks[index], dog)
        if tripped:
            # Report where it got to before giving up. The 2026-08-19 run broke
            # out at step 1191 of 1200 and never printed `placed`, so the record
            # had a hole at exactly the moment the fold completes.
            if "placed" not in [marks[k] for k in marks if k <= index]:
                phase(cfg, ctx, "aborted", dog)
            break
    else:
        completed = True

    # 3. Let go, and let it lie. A fold that only exists while the hand holds it
    #    is not a fold.
    # Snapshot before the release: past this point the numbers are a falling
    # sheet's, which says nothing about how the carry went.
    carry_peak = float(dog.worst_speed)
    hand_mps = (np.pi * radius / steps) / float(cfg.env.sim.dt)
    carry_seconds = steps * float(cfg.env.sim.dt)

    grip.release()
    # Same ceiling, and now nothing is driving the cloth at all -- only the label
    # changes, so a trip can be read back to the phase it happened in.
    dog.set_reference(fall_step, "released")
    phase(cfg, ctx, "released", dog)
    for index in range(1, max(1, int(cfg.run.fold_settle_steps)) + 1):
        scene.step()
        dog.check(steps + index)
    phase(cfg, ctx, "done", dog)

    # The judges are the PRODUCTION ones, imported rather than reimplemented: the
    # numbers this spike prints are the numbers the task will gate on, or the
    # calibration is against something the task does not measure.
    nodes = particles(cloth)
    state = ClothFoldEvaluator.from_config(cfg.task).classify(
        rest_nodes, nodes, table_z=table_z, fold_point=centre_xy, fold_normal=direction
    )
    contact_gap = self_contact_gap(
        rest_nodes, nodes, float(cfg.run.neighbour_radius_scale) * particle_size
    )
    print(
        f"pbd_cloth_spike fold motion={motion} grasp_at={str(cfg.run.grasp_at)} "
        f"pin={str(cfg.run.pin)} pinned={len(pinned)} steps={steps} "
        f"radius_mm={radius * 1e3:.1f} cell_mm={cell * 1e3:.1f} "
        f"completed={completed} "
        f"{state.summary()} "
        f"self_contact_gap_mm={contact_gap * 1e3:.2f} "
        f"(particle_size_mm={particle_size * 1e3:.1f}) "
        # Quasi-static or not, as a ratio. Nothing on the cloth can outrun the
        # grasped corner in a fold done slowly enough -- that corner is the point
        # furthest from the fold line, so every other point travels less. A ratio
        # far above 1 means some part of the sheet is snapping rather than being
        # carried, which is the dynamic regime this category is meant to avoid.
        f"hand_mps={hand_mps:.4f} carry_peak_mps={carry_peak:.4f} "
        f"speed_ratio={carry_peak / max(hand_mps, 1e-9):.1f} "
        # And creep against inertia: a slide that is proportional to how long the
        # carry lasted is creep under a sustained pull, not momentum.
        f"carry_s={carry_seconds:.2f} "
        f"slide_rate_mm_s={state.anchor_shift * 1e3 / max(carry_seconds, 1e-9):.2f} "
        f"{dog.summary()}",
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
    steps = max(1, int(cfg.task.physical.gripper_steps))
    print(
        f"pbd_cloth_spike pinch staging qpos={qpos:.4f} "
        f"half_thickness={half_thickness:.4f} "
        f"ratio={qpos / max(half_thickness, 1e-9):.2f} pads_at={centre[2]:.5f}",
        flush=True,
    )
    # Baseline AFTER the staging and BEFORE the closing, then close one step at a
    # time. The 2026-08-17 run did `set_gripper(qpos, steps=60)` and checked once
    # afterwards, folding 60 steps of finger travel into a single sample: every
    # cell tripped at "step 0" with the same 37 mm, including the ones whose gap
    # was wider than the cloth. That measured the closing motion, not the squeeze.
    opening = float(controller.current_gripper_qpos)
    dog = Watchdog(cfg, cloth, table_z)
    for index in range(1, steps + 1):
        controller.set_gripper(opening + (qpos - opening) * index / steps, steps=1)
        if dog.check(index):
            break
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
    grip = ctx.attach(cfg)
    # After the attach staging, so the approach is not counted as one huge step.
    dog = Watchdog(cfg, cloth, table_z, reference=float(cfg.run.drag_speed))

    speed = float(cfg.run.drag_speed)
    lift = float(cfg.run.lift_delta)
    # FIXED step count; the distance follows from it. With a fixed distance the
    # 2026-08-17 sweep ran 45 steps at the slowest speed and 4 at the fastest --
    # and a divergence needs several steps to develop, so the top of that sweep
    # could not have found one however unstable it was. Every cell now gets the
    # same number of chances.
    drag_steps = max(2, int(cfg.run.drag_steps))
    lift_steps = max(2, int(round(lift / max(speed, 1e-9))))
    distance = speed * drag_steps
    start = np.asarray(controller.hand_pos(), dtype=float)

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
            grip.sync()
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
        f"substep_dt={substep_dt:.5f} mode={grip.mode} "
        f"attached={len(grip.indices)} completed={ok} "
        f"flatness_var={variance:.3e} {dog.summary()}",
        flush=True,
    )


def run_grip(cfg, ctx) -> None:
    """Does the cloth actually come with the hand, and what does it cost?

    A straight vertical lift, nothing else, so the only thing under test is how
    the cloth is held. Two numbers decide it:

    `followed_mm` -- how far the cloth's top rose against how far the hand was
    told to rise. Measured 2026-08-19 with the default hold: the hand went up
    40 mm and the cloth 16.4, i.e. it followed four tenths of the command. A hold
    that works reads close to the full amount.

    `worst_edge_strain` -- how much the material has to stretch somewhere. Holding
    every particle of the patch completely stops that patch bending at all, so
    the bending the motion demands piles onto the ring of material just outside
    it. This is the cost side of holding harder, and the reason the graded hold
    existed in the first place.

    Run the four modes and read them together: the one to keep is the one that
    follows the command without paying too much strain for it.
    """

    scene, cloth, table_z, verbose = ctx.scene, ctx.cloth, ctx.table_z, ctx.verbose
    controller = ctx.controller
    grip = ctx.attach(cfg)
    # After the staging move, so the approach is not counted as one huge step.
    dog = Watchdog(cfg, cloth, table_z, reference=float(cfg.run.drag_speed))

    pairs, rest = ctx.rest_pairs, ctx.rest_lengths
    before_top = float(particles(cloth)[:, 2].max()) - table_z
    # The hand's OWN rise, not just what it was told to do. Without it a low
    # follow ratio cannot say whether the cloth failed to follow the hand or
    # the arm failed to reach the command -- and those need different fixes.
    before_hand = float(controller.hand_pos()[2])

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
        grip.sync()
        tripped = dog.check(index)
        worst_strain = max(worst_strain, edge_strain(particles(cloth), pairs, rest))
        if verbose and index % max(1, int(cfg.run.sample_every)) == 0:
            print(
                f"[cloth_grip step={index:4d}] worst_edge_strain={worst_strain:.4f} "
                f"top_mm={(particles(cloth)[:, 2].max() - table_z) * 1e3:.1f} "
                f"{dog.summary()}",
                flush=True,
            )
        if tripped:
            break
    nodes = particles(cloth)
    variance, peak = flatness(cloth, table_z)
    rose = (float(nodes[:, 2].max()) - table_z) - before_top
    hand_rose = float(controller.hand_pos()[2]) - before_hand
    print(
        f"pbd_cloth_spike grip mode={grip.mode} attached={len(grip.indices)} "
        f"commanded_mm={lift * 1e3:.1f} hand_rose_mm={hand_rose * 1e3:.1f} "
        f"followed_mm={rose * 1e3:.1f} "
        f"follow_ratio={rose / max(hand_rose, 1e-9):.2f} "
        f"reach_ratio={hand_rose / max(lift, 1e-9):.2f} "
        f"worst_edge_strain={worst_strain:.4f} rest_pairs={len(pairs)} "
        f"lifted={int(((nodes[:, 2] - table_z) > float(cfg.run.lift_threshold)).sum())}"
        f"/{len(nodes)} "
        f"flatness_var={variance:.3e} peak_above_table={peak:.5f} "
        f"{dog.summary()}",
        flush=True,
    )



TESTS = {
    "settle": run_settle,
    "fold": run_fold,
    "pinch": run_pinch,
    "contact": run_contact,
    "speed": run_speed,
    "grip": run_grip,
}
# `contact` is excluded on purpose: a segfault there would take everything queued
# behind it down unmeasured.
# `pinch` is last in ALL: it is the one that squeezes, so it is the likeliest
# of these four to diverge, and anything queued behind a diverging cell wastes
# its build time. `contact` stays out entirely -- see above.
ALL = ("settle", "grip", "fold", "speed", "pinch")


#: The four ways of holding the cloth that `_Context.attach` can build.
MODES = ("overwrite_graded", "overwrite_rigid", "link_patch", "link_single")


class _Context:
    def __init__(
        self, cfg, scene, cloth, controller, table_z, grasp_point, ee_quat,
        rest_pairs, rest_lengths, origin, rest_nodes, fold_target, show_viewer,
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
        self.origin = np.asarray(origin, dtype=float)
        # Particle positions once the sheet has settled and before anything
        # touches it: every 'did it move' number is measured against these.
        self.rest_nodes = np.asarray(rest_nodes, dtype=float)
        self.fold_target = np.asarray(fold_target, dtype=float)
        self.show_viewer = bool(show_viewer)
        # Peak height before any stepping; set by `main` right after build.
        self.spawn_peak = 0.0
        self.verbose = bool(cfg.run.verbose)

    def attach(self, cfg, *, mode: str | None = None) -> Grip:
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
        mode = str(mode if mode is not None else cfg.task.grasp.attach_mode)
        if mode not in MODES:
            raise SystemExit(
                f"task.grasp.attach_mode must be one of {sorted(MODES)}, got {mode!r}."
            )
        nodes = particles(self.cloth)
        indices, weights = attached_indices(
            nodes,
            self.grasp_point,
            float(cfg.task.grasp.attach_radius),
            single=(mode == "link_single"),
        )
        # The pads stop this far ABOVE the cloth and stay open: the fingers never
        # touch it in any of the four modes, so the comparison is only about how
        # the particles are carried.
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
        if mode.startswith("link"):
            # Bound to the hand link, so the solver carries them. No offset to
            # keep: the binding is made where the particles already are.
            self.cloth.fix_particles_to_link(
                controller.ee_link.idx, particles_idx_local=[int(i) for i in indices]
            )
            grip = Grip(mode, self.cloth, indices)
            offset_mm = 0.0
        else:
            attachment = ParticleAttachment(
                entity=self.cloth,
                indices=indices,
                parent_pos_fn=controller.hand_pos,
                offset=(0.0, 0.0, -(HAND_TO_PAD_Z + clearance)),
                # `graded` holds each particle only as hard as its distance
                # allows; `rigid` holds every one of them completely.
                weights=(weights if mode == "overwrite_graded" else None),
            )
            attachment.attach()
            grip = Grip(mode, self.cloth, indices, attachment)
            offset_mm = float(np.linalg.norm(attachment.anchor_offset)) * 1e3
        print(
            f"pbd_cloth_spike attach mode={mode} attached={len(indices)} "
            f"attach_radius={float(cfg.task.grasp.attach_radius):.4f} "
            f"touch_clearance={clearance:.4f} attach_offset_mm={offset_mm:.2f}",
            flush=True,
        )
        return grip


@hydra.main(version_base="1.3", config_path="../configs", config_name="pbd_cloth_spike")
def main(cfg: DictConfig) -> None:
    # Camera resolution has to reach the env before the scene is built.
    cfg = apply_recording_camera_overrides(cfg)
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

    # Friction against the TABLE, which Genesis does not provide for a body that
    # is merely resting: its deformable-vs-rigid friction scales with the normal
    # velocity and only runs while a particle is moving INTO the surface, so a
    # sheet already lying on the table gets essentially none however high the
    # table's `coup_friction` is set (`world/rope.py` TabletopParticleFriction,
    # and `docs/develop/physics/pbd_tabletop_friction_zh.md`). The 2026-08-19
    # folds slid the whole sheet across the table for exactly this reason: there
    # was no sustained-contact friction at all, not merely too little.
    #
    # The model suits a sheet without changes. Particles above `contact_band` are
    # left alone, so the half being carried is untouched while the half on the
    # table is held; and its load factor (particles / touching particles) is 1
    # for a flat sheet, which is the textbook mu*g.
    friction_cfg = getattr(cloth_cfg, "tabletop_friction", None)
    table_friction = None
    if friction_cfg is not None and bool(friction_cfg.enabled):
        table_friction = TabletopParticleFriction(
            scene,
            [cloth],
            surface_z=table_z,
            contact_band=float(friction_cfg.contact_band),
            static_mu=float(friction_cfg.static_mu),
            kinetic_mu=float(friction_cfg.kinetic_mu),
            dt=float(cfg.env.sim.dt),
            gravity=abs(float(cfg.env.sim.gravity[2])),
            max_load_factor=float(friction_cfg.max_load_factor),
        ).install()

    controller = initialize_franka_controller(
        scene=scene, manifest=tabletop.manifest, robot_cfg=cfg.robot_control, settle_steps=0
    )
    ee_quat = controller.default_ee_quat

    grasp_point, fold_target = grasp_and_target(cfg, origin, cloth_cfg)
    substep_dt = float(cfg.env.sim.dt) / max(1, int(cfg.env.sim.substeps))
    print(
        f"pbd_cloth_spike setup control_vertices={len(vertices)} "
        f"simulated_particles={len(particles(cloth))} "
        f"particle_size={float(cloth_cfg.particle_size):.4f} "
        f"size={list(cloth_cfg.size)} dt={float(cfg.env.sim.dt):.4f} "
        f"substeps={int(cfg.env.sim.substeps)} substep_dt={substep_dt:.5f} "
        f"grasp_at={str(cfg.run.grasp_at)} "
        f"table_friction={'off' if table_friction is None else f'{float(friction_cfg.kinetic_mu):.2f}/{float(friction_cfg.static_mu):.2f}'} "
        f"grasp=({grasp_point[0]:+.3f},{grasp_point[1]:+.3f}) "
        f"target=({fold_target[0]:+.3f},{fold_target[1]:+.3f}) "
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
        rest_pairs, rest_lengths, origin, particles(cloth), fold_target, show_viewer,
    )
    context.spawn_peak = spawn_peak
    # Recording wraps the tests only. The build, the settle and the rest-graph
    # pass happen before it opens, so a video is the motion and not two minutes
    # of a still sheet.
    with recording_session_from_config(scene, tabletop.cameras, cfg.recording):
        for name in names:
            TESTS[name](cfg, context)
    print_recording_saved(cfg.recording)

    while cfg.run.keep_open and show_viewer:
        scene.step()


if __name__ == "__main__":
    main()
