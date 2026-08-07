"""P1 scene inspector for the continuous Untangle variant (no robot motion).

Generates a braid from ``--seed``, builds the ropes on the power strip, settles
them under gravity, and holds the scene in the viewer so the tangle can be
eyeballed against the braid word printed in the log.

This repo has no pytest suite, so ``--seeds`` doubles as the P0/P1 regression
gate: it builds every seed in a range headless and prints one self-check line
each (``braid.verify_braid_spec``), which is what a unit test would have
asserted. Run it after touching ``topogym/generation/braid.py``.

    python -m prototypes.untangle_continuous_inspect_demo --viewer --keep-open
    python -m prototypes.untangle_continuous_inspect_demo --seeds 0-9 --no-build
"""

from __future__ import annotations

import argparse
from pathlib import Path

import genesis as gs
from omegaconf import OmegaConf

from topogym.core import add_common_config_arg, load_topogym_configs
from topogym.generation.braid import verify_braid_spec
from topogym.utils import initialize_franka_controller
from topogym.tasks import (
    UntangleContinuousLayout,
    UntangleContinuousSceneBuilder,
    settle_scene,
)
from topogym.supervision.untangle_continuous import crossing_lines, rope_health_lines
from topogym.verification import UntangleContinuousPuzzleEvaluator

CONFIG_ROOT = Path(__file__).resolve().parents[1] / "configs"
DEFAULT_COMMON_CONFIG = CONFIG_ROOT / "common_configs" / "manipulation_space_tabletop_v1.yaml"
DEFAULT_ENV_CONFIG = CONFIG_ROOT / "env_configs" / "world_tabletop_v1.yaml"
DEFAULT_ROBOT_CONFIG = CONFIG_ROOT / "robot_control_configs" / "franka_panda_position_ik.yaml"
DEFAULT_TASK_CONFIG = CONFIG_ROOT / "task_configs" / "untangle_continuous_topogym_tabletop_v1.yaml"

# braid.length per difficulty bucket. `easy` is 1 because that is what the
# config baseline is (braid.length: 1) -- a bucket that silently disagreed
# with the config is how a run asked for one crossing and got three.
# Passing no --difficulty uses the config value; the other two buckets are
# deliberately harder scenes, kept for the benchmark difficulty axis.
_DIFFICULTY_LENGTH = {"easy": 1, "default": 3, "hard": 5}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect the continuous Untangle braid scene (no robot motion)."
    )
    parser.add_argument("--env-config", type=Path, default=DEFAULT_ENV_CONFIG)
    parser.add_argument("--robot-config", type=Path, default=DEFAULT_ROBOT_CONFIG)
    parser.add_argument("--task-config", type=Path, default=DEFAULT_TASK_CONFIG)
    add_common_config_arg(parser, default=DEFAULT_COMMON_CONFIG)
    parser.add_argument("--backend", choices=("cpu", "gpu", "cuda"), default="gpu")
    parser.add_argument("--seed", type=int, default=0, help="Braid layout seed.")
    parser.add_argument(
        "--difficulty",
        choices=tuple(_DIFFICULTY_LENGTH),
        default=None,
        help=(
            "Override braid.length: easy=1 (the config baseline), default=3, hard=5. "
            "Omit it to use the config value."
        ),
    )
    parser.add_argument("--viewer", action="store_true", help="Open the Genesis viewer.")
    parser.add_argument("--keep-open", action="store_true", help="Step forever after settling.")
    parser.add_argument(
        "--no-robot",
        action="store_true",
        help="Leave the arm out entirely, to look at the ropes with nothing else in the scene.",
    )
    parser.add_argument(
        "--seeds",
        default=None,
        help="Range like '0-9': verify the braid for every seed instead of one.",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Only run the braid self-check; skip gs.init and scene build. Pairs with --seeds.",
    )
    parser.add_argument(
        "--strands",
        type=int,
        default=None,
        help=(
            "Override braid.n_strands. `--strands 2` is the simplified scene: same "
            "config in every other respect, one rope removed. A CLI override rather "
            "than a second config file so the two cannot drift apart."
        ),
    )
    parser.add_argument(
        "--radial-segments",
        type=int,
        default=None,
        help=(
            "Override rope.mesh.radial_segments, for sweeping the self-collision "
            "consistency experiment. Ring spacing is 2*radius*sin(pi/n), which must "
            "be >= particle_size; at radius 4mm / particle_size 4mm that means n<=6. "
            "Try 8 (the original, 100%% violating) vs 6 (exactly critical) vs 5 (with margin)."
        ),
    )
    parser.add_argument(
        "--segment-length",
        type=float,
        default=None,
        help=(
            "Override rope.mesh.segment_length (metres), the ring spacing ALONG the "
            "rope. This is the size of the holes in the collision barrier: PBD only "
            "pushes particles apart below particle_size, so a particle of the other "
            "rope landing between two rings feels nothing and slides in. At the "
            "default 9mm the holes are more than twice the 4mm repulsion radius, "
            "which is why two ropes settle 2.5mm apart instead of 12mm."
        ),
    )
    parser.add_argument(
        "--rope-model",
        choices=("pbd_elastic_tube", "fem_ipc_tube"),
        default=None,
        help=(
            "Override rope.model. 'fem_ipc_tube' selects the FEM+IPC backend; "
            "pair it with --env-config world_tabletop_fem_v1.yaml (substeps=1)."
        ),
    )
    parser.add_argument(
        "--fem-e",
        type=float,
        default=None,
        help=(
            "Override rope.fem.E (Pa). Spike default 1e5 holds the braid's rest "
            "shape but springs the spawn S-bend back over long settles, walking "
            "the free ends toward each other; lower it to reduce stored energy."
        ),
    )
    parser.add_argument(
        "--fem-friction-mu",
        type=float,
        default=None,
        help="Override rope.fem.friction_mu (default 0.3): rope<->table IPC friction.",
    )
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


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


def main() -> None:
    args = parse_args()
    cfg = load_topogym_configs(
        common_config=args.common_config,
        env_config=args.env_config,
        robot_config=args.robot_config,
        task_config=args.task_config,
    )
    if args.difficulty is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"braid": {"length": _DIFFICULTY_LENGTH[args.difficulty]}}}
        )
    if args.strands is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"braid": {"n_strands": args.strands}}}
        )
    if args.radial_segments is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"mesh": {"radial_segments": args.radial_segments}}}}
        )
    if args.segment_length is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"mesh": {"segment_length": args.segment_length}}}}
        )
    if args.rope_model is not None:
        cfg = OmegaConf.merge(cfg, {"task": {"rope": {"model": args.rope_model}}})
    if args.fem_e is not None:
        cfg = OmegaConf.merge(cfg, {"task": {"rope": {"fem": {"E": args.fem_e}}}})
    if args.fem_friction_mu is not None:
        cfg = OmegaConf.merge(
            cfg, {"task": {"rope": {"fem": {"friction_mu": args.fem_friction_mu}}}}
        )

    seeds = _seed_range(args.seeds) if args.seeds else range(args.seed, args.seed + 1)
    # Materialize the list so every seed prints its line, rather than `all`
    # short-circuiting on the first failure.
    ok = all([_verify(cfg, seed) for seed in seeds])
    if not ok:
        raise SystemExit("untangle_continuous_inspect braid self-check FAILED")
    if args.no_build:
        return

    if len(seeds) != 1:
        raise SystemExit(
            "untangle_continuous_inspect: --seeds builds nothing; add --no-build "
            "for the self-check sweep, or use --seed for a single scene."
        )

    cfg = OmegaConf.merge(cfg, {"env": {"genesis": {"backend": args.backend}}})
    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[cfg.env.genesis.backend])

    rope_scene = UntangleContinuousSceneBuilder(
        cfg.env,
        cfg.task,
        cfg.robot_control,
        seed=args.seed,
    ).build(show_viewer=args.viewer, include_robot=not args.no_robot)

    if not args.no_robot:
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
        % (args.seed, rope_scene.braid.word, len(rope_scene.braid.crossings), steps, moved)
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
    if args.verbose:
        for line in crossing_lines(
                state,
                rope_radius=float(cfg.task.rope.radius),
                particle_size=float(cfg.task.rope.particle_size),
            ):
            print(line)
    if args.verbose:
        for name, handle in rope_scene.rope_handles.items():
            print(
                f"  {name} anchored_particles={len(handle.start_indices)} "
                f"free_end={handle.end_center.round(4).tolist()}"
            )

    if args.keep_open or args.viewer:
        while True:
            rope_scene.scene.step()


if __name__ == "__main__":
    main()
