"""Does flipping `sim.n_envs` above 0 actually get us batched rendering?

The switch itself lives in `StandardTabletopSceneBuilder._select_renderer`: at
`n_envs=0` it returns None and Genesis applies its default rasterizer, so the
single-environment path is untouched; above 0 it selects Madrona's batch
renderer. This probe exists so that claim is measured rather than asserted, and
so the failure -- if there is one -- lands in a ten-line scene instead of inside a
task.

Three things get checked, in order of what breaks first:

1. **Build.** Does a scene with `n_envs > 0` construct with the batch renderer?
2. **Shape.** Does one `render()` come back with a leading batch dimension of
   `n_envs`? A single image would mean we got the fall-back path and never
   noticed.
3. **Cost.** Milliseconds per rendered environment, against the same scene at
   `n_envs=0`. This is the number that says whether batching is worth the
   port: `tests/render_bench.py` measured a frame as mostly fixed per-frame
   cost, so the prediction is that per-environment cost falls as n_envs rises.

What this does NOT show is that a TASK runs batched. Oracles, primitives and
verifiers read state through `.reshape(-1, 3)[0]` in 26 places, i.e. they all
look at environment 0. Those are the port; this probe is the groundwork under
it.

    python -m tests.batch_render_probe run.n_envs_sweep=[0,4,16] env.genesis.backend=cuda
    python -m tests.batch_render_probe run.n_envs_sweep=[8] run.bench_frames=50

Needs CUDA and `gs_madrona` (Linux x86-64). On a machine without them the
builder raises with the reason, which is the intended outcome rather than a
crash.
"""

from __future__ import annotations

import time

import genesis as gs
import hydra
import numpy as np
from omegaconf import DictConfig, OmegaConf

from topogym.core import save_resolved_config
from topogym.world import StandardTabletopSceneBuilder


def probe_once(cfg, n_envs: int, frames: int) -> None:
    """Build at one `n_envs` and report what the renderer gave back."""

    merged = OmegaConf.merge(cfg, {"env": {"sim": {"n_envs": int(n_envs)}}})
    env_cfg = merged.env

    builder = StandardTabletopSceneBuilder(env_cfg, cfg.robot_control)
    tabletop = builder.create(show_viewer=False, include_robot=True)
    builder.finalize(tabletop)
    scene = tabletop.scene
    renderer = type(getattr(scene, "renderer_options", None)).__name__

    name = str(cfg.run.camera)
    camera = tabletop.cameras.get(name)
    if camera is None:
        raise SystemExit(f"camera {name!r} not in env.cameras; available: {list(tabletop.cameras)}")

    rgb = camera.render(rgb=True)
    # `render` returns a tuple whose first element is the RGB buffer.
    frame = rgb[0] if isinstance(rgb, tuple) else rgb
    shape = tuple(np.asarray(frame).shape)
    # Batched output carries a leading environment axis; a 3-D array means one
    # image came back and the batch path is not live.
    batched = len(shape) == 4

    warmup = max(5, frames // 2)
    for _ in range(warmup):
        scene.step()
        camera.render(rgb=True)
    start = time.perf_counter()
    for _ in range(frames):
        scene.step()
        camera.render(rgb=True)
    per_frame_ms = 1e3 * (time.perf_counter() - start) / frames
    envs = max(1, int(n_envs))

    print(
        f"batch_probe n_envs={n_envs:3d} renderer={renderer:<14} "
        f"frame_shape={shape} batched={batched} "
        f"per_frame={per_frame_ms:7.2f}ms per_env={per_frame_ms / envs:7.3f}ms",
        flush=True,
    )
    if int(n_envs) > 0 and not batched:
        print(
            "[warn] n_envs > 0 but a single image came back: the batch path is not "
            "live and every number above is the single-environment one.",
            flush=True,
        )


@hydra.main(version_base="1.3", config_path="../configs", config_name="batch_render_probe")
def main(cfg: DictConfig) -> None:
    resolved = save_resolved_config(cfg)
    if resolved is not None:
        print(f"batch_render_probe_config -> {resolved}", flush=True)

    backends = {"cpu": gs.cpu, "gpu": gs.gpu, "cuda": gs.cuda}
    gs.init(backend=backends[str(cfg.env.genesis.backend)], precision=str(cfg.env.genesis.precision))

    sweep = [int(v) for v in OmegaConf.to_container(cfg.run.n_envs_sweep, resolve=True)]
    if len(sweep) != 1:
        raise SystemExit(
            "One n_envs per process: sweeping means rebuilding, and rebuilding means "
            "tearing Genesis down inside one process. Use "
            "bash_scripts/tests/batch_render_probe.sh for the sweep."
        )
    probe_once(cfg, sweep[0], int(cfg.run.bench_frames))


if __name__ == "__main__":
    main()
