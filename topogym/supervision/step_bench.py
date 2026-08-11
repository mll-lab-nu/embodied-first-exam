"""Stop before physics: build-only checks, and a per-step cost measurement.

Both modes exist because one untangle move costs 46 minutes (2026-08-11: 1755
steps at 1.57 s/step, FEM+IPC, three ropes). That is too slow to iterate against,
and reading source could not say where the time goes -- the rope surface meshes
are ~370 vertices each, the robot is already out of IPC (`needs_coup=False`), and
rigid-rigid contact is already off. So this measures instead of arguing.

``run.build_only=true`` stops right before the physics loop. Everything a config
or migration change touches -- composition, ``derive_config``, scene build,
contract validation, primitive construction -- has already run by then.

``run.bench_steps=N`` steps the built scene N times and reports the rate. The
scene is at rest and the arm is not commanded, so the number is the floor cost of
one ``scene.step()``: IPC solve plus whatever per-step hooks are installed
(attachment manager, one connector latch per endpoint, the FEM follow-band sync).
Compare it against the rate during a real move to separate the two:

- bench rate ~= moving rate -> the cost is the resting solve. Look at the IPC
  budget (``task.rope.fem.newton_max_iterations`` / ``newton_tolerance``) and at
  mesh resolution (``run.lite=true``).
- bench rate >> moving rate -> the cost appears only under contact, i.e. Newton
  needs many more iterations once the gripper loads the rope. The budget knobs
  are then the direct lever.

The report also splits the step into ``solver`` and ``hooks``, and divides the
solver share by ``env.sim.substeps`` to give the cost of one ``_ipc_world.advance()``
(``couple()`` runs once per substep, ``coupler.py:818``). First measurement,
2026-08-11, untangle at rest: 663 ms/step total.

A warmup segment is excluded from the timing: Genesis/quadrants JIT-compile
kernels on first use and libuipc assembles its contact structures on the first
advance, so the opening steps are not representative.
"""

from __future__ import annotations

import time


def stop_before_physics(cfg, scene, label: str) -> bool:
    """Honour ``run.bench_steps`` then ``run.build_only``.

    Returns True when the caller must not run its physics loop.
    """
    bench = int(getattr(cfg.run, "bench_steps", 0) or 0)
    if bench > 0:
        # 10 步不够：2026-08-11 的实测里，前 200 步的速率在 19->7.7 与 3->8.2 之间
        # 两个方向都漂过，稳定要几十步。取一半，并且至少 10 步。
        warmup = max(10, bench // 2)
        for _ in range(warmup):
            scene.step()

        def timed(step_fn) -> float:
            started = time.perf_counter()
            for _ in range(bench):
                step_fn()
            return time.perf_counter() - started

        hooked = timed(scene.step)
        # Every per-step hook in this repo installs itself as an *instance*
        # attribute (`scene.step = wrapped`), so the class method is the
        # unwrapped one. Calling it bypasses the attachment manager, the one
        # connector latch per endpoint, and the FEM follow-band sync, leaving
        # the solver alone. The difference is what our own Python + GPU
        # round-trips cost. The scene is discarded right after, so skipping the
        # latch syncs for this segment does not matter.
        raw = timed(lambda: type(scene).step(scene))

        overhead = hooked - raw
        # 两段之间仍有漂移，hooks 出现负值就说明这次的噪声大于被测量。
        noise = "（负值=本次噪声大于钩子开销）" if overhead < 0 else ""
        # 必须取**场景实际**的 substeps，不是配置里的。fem_ipc_rope_spike 自建 scene
        # 时硬编码 substeps=1，与它加载的 env 配置（4）不一致；2026-08-11 曾按配置值
        # 除，把该脚本的每次 advance 耗时报小了 4 倍，并据此得出错误结论。
        substeps = int(getattr(getattr(scene, "sim", None), "_substeps", 0)) or int(cfg.env.sim.substeps)
        print(
            f"{label} bench steps={bench} warmup={warmup} "
            f"backend={cfg.env.genesis.backend} "
            f"per_step={hooked / bench * 1000:.0f}ms rate={bench / hooked:.2f}steps/s "
            f"solver={raw / bench * 1000:.0f}ms hooks={overhead / bench * 1000:.0f}ms "
            f"hooks_share={overhead / hooked * 100:.0f}%{noise} "
            f"substeps={substeps} "
            f"per_ipc_advance={raw / bench / max(1, substeps) * 1000:.0f}ms",
            flush=True,
        )
        return True

    if bool(getattr(cfg.run, "build_only", False)):
        print(f"{label} build_only; 物理未执行", flush=True)
        return True

    return False
