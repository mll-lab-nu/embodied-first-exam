"""P1 scene inspector for the continuous Untangle variant (no robot motion).

Generates a braid from ``--seed``, builds the ropes on the power strip, settles
them under gravity, and holds the scene in the viewer so the tangle can be
eyeballed against the braid word printed in the log.

This repo has no pytest suite, so ``--seeds`` doubles as the P0/P1 regression
gate: it builds every seed in a range headless and prints one self-check line
each (``braid.verify_braid_spec``), which is what a unit test would have
asserted. Run it after touching ``topogym/generation/braid.py``.

Configuration is Hydra (`configs/untangle_continuous_inspect.yaml`).

    python -m demos.entangle.untangle_continuous_inspect_demo run.viewer=true run.keep_open=true
    python -m demos.entangle.untangle_continuous_inspect_demo run.seeds=0-9 run.no_build=true
    python -m demos.entangle.untangle_continuous_inspect_demo task.rope.mesh.segment_length=0.004
    python -m demos.entangle.untangle_continuous_inspect_demo --cfg job
"""

from __future__ import annotations


import genesis as gs
import hydra
from omegaconf import DictConfig

from topogym.core import save_resolved_config
from topogym.generation.braid import verify_braid_spec
from topogym.utils import initialize_franka_controller
from topogym.supervision import stop_before_physics
from topogym.tasks_legacy import (
    UntangleContinuousLayout,
    UntangleContinuousSceneBuilder,
    settle_scene,
)
from topogym.supervision.untangle_continuous import crossing_lines, rope_health_lines
from topogym.verification import UntangleContinuousPuzzleEvaluator

def _seed_range(text: str) -> range:
    if "-" in text:
        low, high = text.split("-", 1)
        return range(int(low), int(high) + 1)
    return range(int(text), int(text) + 1)


def _verify(cfg, seed: int) -> bool:
    """Self-check one seed's braid without building a scene."""

    layout = UntangleContinuousLayout(cfg.task, seed=seed)
    spec = layout.braid_spec()
    workspace = cfg.common.manipulation_space.workspace
    report = verify_braid_spec(
        spec,
        rope_radius=float(cfg.task.rope.radius),
        particle_size=float(cfg.task.rope.particle_size),
        x_bounds=(float(workspace.x[0]), float(workspace.x[1])),
        y_bounds=(float(workspace.y[0]), float(workspace.y[1])),
    )
    print(
        f"untangle_continuous_braid seed={seed} word={spec.word} "
        f"crossings={len(spec.crossings)} "
        f"over_under={[(c.over_strand, c.under_strand) for c in spec.crossings]} {report}"
    )
    return report.ok


@hydra.main(version_base="1.3", config_path="../../configs", config_name="untangle_continuous_inspect")
def main(cfg: DictConfig) -> None:
    # Every scene and physics override is a config path now, e.g.
    #   task.braid.n_strands=2  task.rope.mesh.segment_length=0.004
    #   task.rope.model=fem_ipc_tube  task.rope.fem.E=200000.0
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"untangle_continuous_inspect_config -> {resolved}", flush=True)

    seeds = _seed_range(cfg.run.seeds) if cfg.run.seeds else range(cfg.run.seed, cfg.run.seed + 1)
    # Materialize the list so every seed prints its line, rather than `all`
    # short-circuiting on the first failure.
    ok = all([_verify(cfg, seed) for seed in seeds])
    if not ok:
        raise SystemExit("untangle_continuous_inspect braid self-check FAILED")
    if cfg.run.no_build:
        return

    if len(seeds) != 1:
        raise SystemExit(
            "untangle_continuous_inspect: run.seeds builds nothing; add run.no_build=true "
            "for the self-check sweep, or use run.seed for a single scene."
        )

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)])

    rope_scene = UntangleContinuousSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=cfg.run.seed,
    ).build(show_viewer=cfg.run.viewer, include_robot=not cfg.run.no_robot)

    if not cfg.run.no_robot:
        # MUST happen before any stepping. The scene builder only *adds* the arm;
        # joint PD gains and the home pose come from the controller. Without it the
        # arm is an unactuated linkage that collapses under gravity onto the table
        # -- and on the way down it sweeps the ropes, which looks exactly like the
        # ropes blowing up on their own.
        initialize_franka_controller(
            scene=rope_scene.scene,
            manifest=rope_scene.manifest,
            robot_cfg=cfg.robot_control,
        )

    # Before settling: can the rope's own particle spacing satisfy PBD
    # self-collision at all? Everything downstream depends on the answer.
    for line in rope_health_lines(rope_scene, particle_size=float(cfg.task.rope.particle_size)):
        print(line)

    steps, moved = settle_scene(rope_scene)
    print(
        "untangle_continuous_inspect seed=%d word=%s crossings_gt=%d "
        "settle_steps=%d max_particle_step=%.6f"
        % (cfg.run.seed, rope_scene.braid.word, len(rope_scene.braid.crossings), steps, moved)
    )

    # P2 acceptance gate: the geometric detector must see exactly the crossings the
    # braid word encodes. This is the whole evidence that the detector is credible;
    # it only holds on the freshly settled state, before anything moves the ropes.
    evaluator = UntangleContinuousPuzzleEvaluator.from_config(cfg.task)
    state = evaluator.classify(rope_scene)
    ok, detail = evaluator.matches_braid_ground_truth(rope_scene)
    print(
        "untangle_continuous_detect crossings=%d min_separation=%.4f terminal=%s "
        "gt_match=%s %s"
        % (state.crossing_count, state.min_separation, state.is_terminal, ok, detail)
    )
    if cfg.run.verbose:
        for line in crossing_lines(
                state,
                rope_radius=float(cfg.task.rope.radius),
                particle_size=float(cfg.task.rope.particle_size),
            ):
            print(line)
        for name, handle in rope_scene.rope_handles.items():
            print(
                f"  {name} anchored_particles={len(handle.start_indices)} "
                f"free_end={handle.end_center.round(4).tolist()}"
            )

    if stop_before_physics(cfg, rope_scene.scene, "untangle_continuous_inspect_demo"):
        return

    if cfg.run.keep_open or cfg.run.viewer:
        while True:
            rope_scene.scene.step()


if __name__ == "__main__":
    main()
