# humanoidbench-loco-reach-i00-privileged

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | privileged |
| Twin | `humanoidbench-loco-reach-i00-standard` |
| Simulator / robot | `humanoidbench` / `unitree-h1` |
| Family / instance | `reach` / seed 0 |
| Oracle | `none` — GPT-6 Luna's privileged-mode trajectory (19184.07 / 12000), run `codex-gpt6_luna-medium` on the results site; today's privileged verifier scores it 1, and so does the standard service when it is sent through the client; human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-humanoidbench:0.1.6` |

## Task
HumanoidBench reach: produce one replayable trajectory that brings the Unitree H1's left hand to a target point and holds it there, frozen scene instance 00.

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 12000` over 1000 steps), not a
predicate on the final state.

- **Two regimes in one reward, and only the second clears the bar.** Getting within 1 m is worth 5 a
  step and is reachable by leaning; the last 5 cm is worth 10 more and needs precise, *held* placement.
  An agent that stops at the easy plateau lands around 10000 against a bar of 12000 and fails.
- **Holding is the hard part.** The bonus is paid per step inside the tolerance, not once on arrival, so
  the deliverable is a posture that stays put for hundreds of steps, not a reaching motion.
- **19 DoF makes this the cheap probe for its class**; the rest of C8 costs a walk across the room.
- **Upstream shipped trained policies for exactly this task** (`data/reach_*`, the hierarchical
  baseline's low level). They are deleted from the base image by
  `images/humanoidbench/scrub_oracles.py`; without that they would be a ready-made submission.

⚠️ **Instances of this family are not interchangeable.** The target is drawn uniformly from a ±2 m
box, so one seed can put it at the robot's feet and another 2.8 m away — a different task, not a
different sample of the same task. In this instance it sits **0.704 m from the left hand's starting
position** (0.88 m from the origin in the horizontal plane), i.e. reachable by leaning and a step
rather than by crossing the room. Any `i01`/`i02` must be filtered to a comparable distance band and
the band recorded here.

**Measured floors** (this instance, `scripts/humanoidbench/gen_tasks.py verify`): an all-zero
trajectory scores **275.22 / 12000**. The target sits 0.704 m from the left hand at the frozen pose.
Holding the starting pose instead — the floor a competent agent gets before writing a controller —
scores **5.1%** of the bar; that is the number this task was selected on (the give-away limit of
`gen_tasks.py verify`). **External evidence**: published RL results reach **69%** of the bar (paper
8280, FastTD3 8147, bar 12000) — training runs of millions of environment steps, not a one-hour
coding session, so treat it as proof that the task *has* a solution rather than as a target.

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
| Capability class | C8 · mobile manipulation (see `scripts/humanoidbench/subset.toml`) |

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
`tests/instance.npz`) is reproducible with `gen_tasks.py render reach`; the instance with
`gen_tasks.py instance reach` (seed 0, sha `8014759785fe`).
