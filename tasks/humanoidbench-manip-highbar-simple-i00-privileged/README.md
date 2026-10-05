# humanoidbench-manip-highbar-simple-i00-privileged

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | privileged |
| Twin | `humanoidbench-manip-highbar-simple-i00-standard` |
| Simulator / robot | `humanoidbench` / `unitree-h1` |
| Family / instance | `highbar_simple` / seed 0 |
| Oracle | `none` — none known: no run has passed it, and no published RL result covers it (neither upstream's curves (which cover only highbar_hard) nor FastTD3 (h1hand only) report this family); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-humanoidbench:0.1.6` |

## Task
HumanoidBench highbar_simple: produce one replayable trajectory that swings the Unitree H1 up on a high bar, frozen scene instance 00.

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 750` over 1000 steps), not a
predicate on the final state.

- **Energy injection, not stabilisation and not a gait.** Reaching an inverted pose from a hang takes
  pumping: small oscillations amplified by applying torque at the right phase. The code an agent has to
  write is a timed, large-amplitude joint trajectory — structurally unlike the feedback controllers of
  C3 or the contact schedules of C1/C2.
- **Hanging quietly scores zero.** Because the uprightness term is negated, the do-nothing basin is not
  a local optimum worth defending — it is exactly 0 (measured: 0.08/750 over a full 1000 steps), so
  there is no partial credit to coast on.
- **A receding horizon does not contain the answer.** Pumping pays off only after several swing cycles,
  so a planner optimising the next few dozen steps sees nothing but wasted effort. This is the clearest
  structural reason the task survives the CEM-MPC approach that solved `walk`.
- **This is the subset's ceiling, and it is kept on purpose.** A benchmark whose every task is solved
  saturates the moment models improve. Note the evidence here is the thinnest of the subset: neither upstream's
  curves (which cover only `highbar_hard`, whose best final return is 12 of 750) nor FastTD3 (h1hand only)
  report this family, so "very hard" is a reasonable prior but not an established fact.
- **Cleanest determinism in the subset**: 19 DoF, no objects, and upstream forces the reset noise to
  zero for this family — see the caveat below.

⚠️ **This family can only ever have one instance.** `HighBarBase.reset_model()` sets the
environment's `randomness` to 0, so every reset produces the identical pose. There is no `i01`/`i02`
to generate; that is upstream behaviour, not a defect in the instance.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **0.08 / 750**. Holding the starting pose instead — the floor a competent agent
gets before writing a controller — scores **0.0%** of the bar; that is the number this task was
selected on (the give-away limit of `gen_tasks.py verify`). **External evidence**: published RL
results reach **an unknown fraction** of the bar (neither upstream's curves (which cover only
highbar_hard) nor FastTD3 (h1hand only) report this family) — training runs of millions of
environment steps, not a one-hour coding session, so treat it as proof that the task *has* a
solution rather than as a target.

**The agent does not see the reward function.** It is deleted from the image and restored only
inside the verifier (`images/humanoidbench/scrub_oracles.py`, `tests/rcb_rewards.py`), so the
numbers above are comparable with the paper while the agent works from the task statement and the
physical state alone.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically
removes the interesting tasks. What replaces it (docs/PROTOCOL.md §2.7): the floor above (doing
nothing cannot pass), the evidence that the task has a solution (`oracle_evidence` in task.toml),
and a human reviewer.

## Verification
In its own container, built from `tests/Dockerfile` (no network): the agent's container is gone by
then, and only `/app/output/` crosses over. Open-loop replay of `/app/output/trajectory.npz` from
`tests/instance.npz` in a fresh process, twice; pass iff every replay's episode return reaches
`success_bar` **and** the final-state hashes agree (bit-exact determinism). `tests/grade.py` also
writes `/logs/verifier/replay.mp4` and, because Harbor promotes every `reward.json` key to a
leaderboard metric, keeps the per-task numbers (`episode_return`, `success_bar`) in
`/logs/verifier/diagnostics.json`. No oracle; human review in PR #9. `nop` scores 0.

## Details
| | |
|---|---|
| Capability class | C5 · whole-body power and momentum (see `scripts/humanoidbench/subset.toml`) |

### GPU
Optional, and passing never depends on it: MuJoCo physics is CPU-only, so a GPU only speeds up the
agent's own offscreen rendering (osmesa ~130 ms/frame, egl ~0.4 ms). Hand one to the agent's
container with `--extra-docker-compose environment/gpu.docker-compose.yaml`; `rcb_hb.py` then picks
EGL by itself unless `MUJOCO_GL` says otherwise. The overlay is not named `docker-compose.yaml`
because Harbor would load that on every machine, and a device reservation the host cannot satisfy
stops the container from starting.

### Provenance
Generated by `scripts/humanoidbench/gen_tasks.py` from `scripts/humanoidbench/subset.toml`.
Everything in this directory except the instance (`environment/instance.npz` and its byte copy
`tests/instance.npz`) is reproducible with `gen_tasks.py render highbar_simple`; the instance with
`gen_tasks.py instance highbar_simple` (seed 0, sha `9cbea1804a71`).
