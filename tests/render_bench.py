"""How long does a frame cost, and how does that compare to a physics step?

Written for a reviewer question: "what is the rendering speed, and can we batch
render across scenes for faster training rollouts?" Neither half was measurable
from anything the repo already produces. The `Running at N FPS` lines Genesis
prints are `scene.step()` rates, and every long run in `runs/` is headless with
no camera rendering at all, so they say nothing about frame cost.

What this measures, per camera and per resolution:

- **step**: `scene.step()` with nothing rendered. The floor.
- **render**: `camera.render(force_render=True)` alone, no stepping.
- **step+render**: what a rollout that records observations actually pays.

`both` should come out near `step + render`. A large gap means one of the two is
measuring something other than what its name says.

The ratio is the number that matters for training throughput. A physics step is
the same work whether or not anyone looks; if a frame costs several steps, the
renderer sets the rollout rate and batching it is where the speedup is.

Also reports which renderer is live. Genesis defaults `Scene(renderer=None)` to
`Rasterizer` (engine/scene.py:130), and this repo never passes one -- the
`renderer:` block in the env configs is read by nobody. The rasterizer goes
through OpenGL and falls back to software when EGL is unavailable, which is not
an edge case here: the WSL box hits `libEGL warning: failed to open
/dev/dri/renderD128: Permission denied` and drops to software, where the same
scene ran roughly ten times slower. The benchmark prints the context so a number
is never reported without saying which of the two produced it.

    python -m tests.render_bench run.verbose=true
    python -m tests.render_bench run.res=960 run.bench_frames=60
    bash bash_scripts/tests/render_bench.sh          # 扫分辨率, 每档一个进程
    python -m tests.render_bench task_configs@task=bar_through_hole_topogym_tabletop_v1

Batch rendering is NOT exercised here; see the report this accompanies for why
(it needs `n_envs > 0`, and the task/verifier layer indexes environment 0 in 26
places).
"""

from __future__ import annotations

import time

import genesis as gs
import hydra

from omegaconf import DictConfig, OmegaConf

from topogym.core import save_resolved_config
from topogym.world import StandardTabletopSceneBuilder


def time_it(fn, count: int) -> float:
    """Milliseconds per call, after a warm-up of the same shape.

    The first calls compile kernels and allocate buffers; `step_bench.py` found
    rates still drifting after a hundred steps, so the warm-up is not token.
    """

    # Half, matching `supervision/step_bench.py`: it measured rates still drifting
    # in both directions over the first 200 steps, so a token warm-up reports the
    # warm-up rather than the steady state.
    warmup = max(10, count // 2)
    for _ in range(warmup):
        fn()
    start = time.perf_counter()
    for _ in range(count):
        fn()
    return 1e3 * (time.perf_counter() - start) / count


@hydra.main(version_base="1.3", config_path="../configs", config_name="render_bench")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"render_bench_config -> {resolved}", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    frames = int(cfg.run.bench_frames)
    res = int(cfg.run.res)
    names = [str(v) for v in OmegaConf.to_container(cfg.run.cameras, resolve=True)]

    # One resolution per process. Camera resolution is fixed at construction, so a
    # sweep would mean rebuilding the scene, and rebuilding means tearing Genesis
    # down and re-initialising it inside one process -- avoidable risk for a
    # measurement whose whole value is being trustworthy. The sweep lives in
    # bash_scripts/tests/render_bench.sh, one process per row.
    overrides = {"env": {"cameras": {name: {"res": [res, res]} for name in names}}}
    env_cfg = OmegaConf.merge(cfg.env, OmegaConf.create(overrides))
    builder = StandardTabletopSceneBuilder(env_cfg, cfg.robot_control)
    tabletop = builder.create(show_viewer=False, include_robot=True)
    builder.finalize(tabletop)
    scene = tabletop.scene

    renderer = type(getattr(scene, "renderer_options", None)).__name__
    step_ms = time_it(scene.step, frames)

    for name in names:
        camera = tabletop.cameras.get(name)
        if camera is None:
            print(f"[warn] camera {name!r} not in this env config; skipped.", flush=True)
            continue

        # force_render=True is load-bearing. `update()` returns early when the
        # scene's clock has not advanced (rasterizer_context.py:1164), and this
        # loop deliberately does not step -- so without it, every frame after the
        # first would skip the scene-graph update and the number would leave out
        # the pose upload that a real recording pays on every frame.
        def render_once(cam=camera):
            cam.render(rgb=True, force_render=True)

        def both(cam=camera):
            scene.step()
            cam.render(rgb=True)

        render_ms = time_it(render_once, frames)
        both_ms = time_it(both, frames)
        print(
            f"render_bench res={res:4d} camera={name:<11} renderer={renderer} "
            f"backend={str(cfg.env.genesis.backend)} "
            f"step={step_ms:7.2f}ms render={render_ms:7.2f}ms both={both_ms:7.2f}ms "
            f"render_fps={1e3 / max(render_ms, 1e-9):7.1f} "
            f"rollout_fps={1e3 / max(both_ms, 1e-9):7.1f} "
            f"render_over_step={render_ms / max(step_ms, 1e-9):5.2f}x",
            flush=True,
        )

    print(
        "render_bench note: a rollout recording N cameras pays step + N*render per "
        "frame. Compare render/step above against N to see which side dominates.",
        flush=True,
    )


if __name__ == "__main__":
    main()
