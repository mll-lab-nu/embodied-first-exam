"""Look at the Unlink C Ring stand, and watch whether the C stays on it.

Stage-0 demo: no robot motion, no extraction. `tests/check_c_ring_clearance.py`
already settles the geometry without a solver -- the opening fits the bar, and every
non-gateway trajectory jams. This demo answers the three things geometry cannot:

1. **Does the scene load without spawning inside itself?** Two chains of three dozen
   cylinders each, one of them threaded through the other, is exactly the shape that
   spawns interpenetrating. `run.static_only=true` looks at it before any stepping,
   so a build-time overlap cannot be hidden by the first settle.

2. **Does the C stay linked when nothing touches it?** A ring hanging on a bar can
   spin, and if the opening ever turns up to the bar the C drops off unaided and the
   task solves itself. The stub is sized to stop that (`_c_ring_geometry.TabSpec`),
   and the hold phase is the measurement that says whether it does: the linking
   number and the angle from the opening to the bar, sampled the whole way.

3. **What does a step cost?** The two chains give roughly 36 x 33 collision pairs,
   the only figure in this scene with no analytic answer. `run.bench_steps=N`.

    python -m demos.entangle.unlink_c_ring_inspect_demo run.static_only=true
    python -m demos.entangle.unlink_c_ring_inspect_demo run.verbose=true
    python -m demos.entangle.unlink_c_ring_inspect_demo run.viewer=true run.keep_open=true
    python -m demos.entangle.unlink_c_ring_inspect_demo run.bench_steps=200
    python -m demos.entangle.unlink_c_ring_inspect_demo --cfg job
"""

from __future__ import annotations

import os

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.supervision import stop_before_physics
from topogym.tasks import UnlinkCRingSceneBuilder
from topogym.tasks.entangle import _c_ring_geometry as ring_geometry
from topogym.utils.franka import initialize_franka_controller
from topogym.utils.recording import (
    apply_recording_camera_overrides,
    print_recording_saved,
    recording_session_from_config,
)
from topogym.verification import UnlinkCRingPuzzleEvaluator

# Below this the opening is close enough to the bar that the C can slip off, since
# half the opening subtends that much. Reported as a margin, not enforced.
FALL_OFF_MARGIN_DEG = 0.5


def reading(evaluator, ring_scene, frame=None) -> dict:
    """The verifier's readings, flattened for printing.

    The judge owns the readback -- `module_boundaries_zh.md` section 3 -- so this
    demo asks the evaluator rather than reconstructing the ring frame itself.
    Passing ``frame`` reads a hypothetical pose (the spawn pose, before any
    stepping); leaving it out reads the solver's current one.
    """

    state = evaluator.classify(ring_scene, frame=frame)
    return {
        "linking": state.linking,
        "opening_to_bar_deg": state.opening_to_bar_deg,
        "drift_mm": 1000.0 * state.center_drift,
        "tilt_deg": state.tilt_deg,
    }


def _hud(ring_scene, state):
    def render_lines():
        return [
            "task=unlink_c_ring",
            f"phase={state.get('phase', '-')}",
            f"Lk={state.get('linking', 0.0):+.1f}",
            f"opening_to_bar={state.get('opening_to_bar_deg', 0.0):.0f}deg",
        ]

    return render_lines


def hold(cfg, evaluator, ring_scene, state) -> None:
    """Step with nothing touching the C, and watch the interlock hold or not."""

    scene = ring_scene.scene
    every = max(1, int(cfg.run.hold_sample_every))
    worst_linking, worst_angle = np.inf, np.inf
    slipped_at = None

    for step in range(1, int(cfg.run.hold_steps) + 1):
        scene.step()
        if step % every and step != int(cfg.run.hold_steps):
            continue
        sample = reading(evaluator, ring_scene)
        state.update(sample)
        worst_linking = min(worst_linking, abs(sample["linking"]))
        worst_angle = min(worst_angle, sample["opening_to_bar_deg"])
        if slipped_at is None and abs(sample["linking"]) < 0.5:
            slipped_at = step
        if cfg.run.verbose:
            print(
                f"[unlink_c_ring step={step:4d}] Lk={sample['linking']:+.1f} "
                f"opening_to_bar={sample['opening_to_bar_deg']:6.2f}deg "
                f"drift={sample['drift_mm']:5.2f}mm tilt={sample['tilt_deg']:5.2f}deg",
                flush=True,
            )

    final = reading(evaluator, ring_scene)
    print(
        "unlink_c_ring hold "
        f"steps={int(cfg.run.hold_steps)} "
        f"min_abs_Lk={worst_linking:+.2f} "
        f"min_opening_to_bar={worst_angle:.2f}deg "
        f"final_opening_to_bar={final['opening_to_bar_deg']:.2f}deg "
        f"final_drift={final['drift_mm']:.2f}mm final_tilt={final['tilt_deg']:.2f}deg "
        f"slipped_at={slipped_at}",
        flush=True,
    )
    half_opening = 0.5 * float(cfg.task.c_ring.gap_deg)
    if slipped_at is not None:
        print(
            "[warn] the C unlinked itself with nothing touching it: the task solves "
            "itself. Lengthen task.c_ring.tab.length, which is what pulls the centre "
            "of mass below the ring, or move task.c_ring.gap_azimuth_deg further from "
            "the bar.",
            flush=True,
        )
    elif worst_angle < half_opening + FALL_OFF_MARGIN_DEG:
        print(
            f"[warn] the opening came within {worst_angle:.2f} deg of the bar, and "
            f"half the opening is {half_opening:.2f} deg -- it did not slip off this "
            "run, but there is no margin. Same two knobs as above.",
            flush=True,
        )


@hydra.main(version_base="1.3", config_path="../../configs", config_name="unlink_c_ring")
def main(cfg: DictConfig) -> None:
    cfg = apply_recording_camera_overrides(cfg)
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"unlink_c_ring_config -> {resolved}", flush=True)

    has_display = os.name == "nt" or bool(
        os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")
    )
    show_viewer = bool(cfg.run.viewer and has_display)
    if cfg.run.viewer and not show_viewer:
        print("[warn] no display detected; falling back to headless.", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    builder = UnlinkCRingSceneBuilder(cfg.env, cfg.task, cfg.robot_control)
    ring_scene = builder.build(show_viewer=show_viewer)
    geometry = ring_scene.geometry

    # The Franka takes no part in this demo but is still in the scene, and with no
    # joint targets it collapses under gravity on the first step. Settling to home is
    # also the moment a stand taller than the home pose would be discovered, which is
    # why the stand's height is one of the layout's checked inequalities.
    initialize_franka_controller(
        scene=ring_scene.scene,
        manifest=ring_scene.manifest,
        robot_cfg=cfg.robot_control,
        settle_steps=0 if cfg.run.static_only else int(cfg.run.settle_steps),
    )

    print(
        "unlink_c_ring setup "
        f"closed_ring R={geometry.fixed.major_radius:.3f} r={geometry.fixed.tube_radius:.3f} "
        f"C R={geometry.c_ring.major_radius:.3f} r={geometry.c_ring.tube_radius:.3f} "
        f"opening={geometry.c_ring.gap_deg:.0f}deg clear={geometry.c_ring.gap_clear_width * 1000:.2f}mm "
        f"hang={geometry.hang_offset * 1000:.1f}mm extract={geometry.extract_travel * 1000:.1f}mm "
        f"top_z={geometry.top_z:.4f} home_margin="
        f"{(ring_geometry.HOME_FINGERTIP_Z - geometry.top_z) * 1000:.1f}mm",
        flush=True,
    )
    evaluator = UnlinkCRingPuzzleEvaluator.from_config(cfg.task)
    spawn = reading(evaluator, ring_scene, frame=geometry.c_spawn_frame)
    # The projection is part of the judging contract (`task_taxonomy_zh.md` 4.3), and
    # it is derived from the layout rather than configured, so the run has to say
    # which one it used.
    viewer = geometry.projection[2]
    print(
        f"unlink_c_ring spawn Lk={spawn['linking']:+.1f} "
        f"opening_to_bar={spawn['opening_to_bar_deg']:.2f}deg "
        f"projection_viewer=({viewer[0]:+.3f},{viewer[1]:+.3f},{viewer[2]:+.3f}) "
        f"stand_yaw={float(cfg.task.stand.yaw_deg):.1f}deg",
        flush=True,
    )

    if stop_before_physics(cfg, ring_scene.scene, "unlink_c_ring_inspect_demo"):
        raise SystemExit(0)

    state = {"phase": "settle", **spawn}
    with recording_session_from_config(
        ring_scene.scene, ring_scene.cameras, cfg.recording, hud=_hud(ring_scene, state)
    ):
        if cfg.run.static_only:
            print("unlink_c_ring static_only=true; not stepping.", flush=True)
        else:
            settled = reading(evaluator, ring_scene)
            print(
                f"unlink_c_ring settled Lk={settled['linking']:+.1f} "
                f"opening_to_bar={settled['opening_to_bar_deg']:.2f}deg "
                f"drift={settled['drift_mm']:.2f}mm tilt={settled['tilt_deg']:.2f}deg",
                flush=True,
            )
            state.update(settled)
            state["phase"] = "hold"
            hold(cfg, evaluator, ring_scene, state)
        state["phase"] = "done"

    print_recording_saved(cfg.recording)
    while cfg.run.keep_open and show_viewer:
        ring_scene.scene.step()


if __name__ == "__main__":
    main()
