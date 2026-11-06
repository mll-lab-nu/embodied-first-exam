# humanoidbench-loco-hurdle-i00-privileged

| | |
|---|---|
| Benchmark | HumanoidBench |
| Mode | privileged |
| Twin | `humanoidbench-loco-hurdle-i00-standard` |
| Simulator / robot | `humanoidbench` / `unitree-h1` |
| Family / instance | `hurdle` / seed 0 |
| Oracle | `none` — no rollout of this instance; published RL passes the bar (FastTD3 887 / 700); human review in PR #9 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:humanoidbench-0.2.0` |

## Task
HumanoidBench hurdle: produce one replayable trajectory that runs the Unitree H1 down a walled track past a line of hurdles, frozen scene instance 00.

## Difficulty
The pass mark is a **threshold on the whole episode's return** (`>= 700` over 1000 steps), not a
predicate on the final state.

- **A multiplicative gate, not a penalty.** Contact with the side or back walls discounts the whole step
  by ×0.1 (the hurdles themselves are not gated).
  Approaches that trade a little contact for a lot of speed do not work here; the gate has to be
  respected exactly.
- **Running, not walking.** The speed term is scaled to 5 m/s, so a comfortable walking gait leaves most
  of the per-step reward on the table even when nothing is hit.
- **Sprinting over solid hurdles.** The reward never looks at the hurdles, but each one is a solid box
  37.5 cm high across the track: the robot has to clear it at speed or it trips.

**Measured floors** (this instance): an all-zero
trajectory scores **18.05 / 700**. Holding the starting pose instead — the floor a competent agent
gets before writing a controller — scores **3.3%** of the bar; that is the number this task was
selected on (the benchmark's give-away limit). **External evidence**: published RL
results reach **127%** of the bar (paper 143, FastTD3 887, bar 700) — training runs of millions of
environment steps, not a one-hour coding session, so treat it as proof that the task *has* a
solution rather than as a target.

**The agent does not see the reward function.** It is deleted from the image and restored only
inside the verifier (`images/humanoidbench/scrub_oracles.py`, `tests/rcb_rewards.py`), so the
numbers above are upstream's own scoring (on our physics: see *Physics vs upstream*) while the agent
works from the task statement and the physical state alone.

## Reference solution
None. Requiring one would cap the benchmark at what we can already solve, which systematically
removes the interesting tasks. What replaces it (docs/protocol/README.md §4): the floor above
(doing nothing cannot pass), the evidence that the task has a solution (`oracle_evidence` in
task.toml), and a human reviewer.

## Verification
In its own container, built from `tests/Dockerfile` (no network): the agent's container is gone by
then, and only `/app/output/` crosses over. Open-loop replay of `/app/output/trajectory.npz` from
`tests/instance.npz` in a fresh process, once; pass iff the replay's episode return reaches
`success_bar`. `tests/grade.py` also
writes `/logs/verifier/replay.mp4` and, because Harbor promotes every `reward.json` key to a
leaderboard metric, keeps the per-task numbers (`episode_return`, `success_bar`) in
`/logs/verifier/diagnostics.json`. No oracle; human review in PR #9. `nop` scores 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 20 GiB | 2048 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Capability class | C2 · constrained gait |
| Physics vs upstream | upstream's model (HumanoidBench cb11890) on MuJoCo 3.3.7, not the 3.1.6 upstream pins, whose convex collision reported wrong contacts; results on image 0.1.6 or earlier are other physics and are reported apart (tasks/humanoidbench/README.md, Physics). |

### GPU
Optional, and passing never depends on it: MuJoCo physics is CPU-only, so a GPU only speeds up the
agent's own offscreen rendering (osmesa ~130 ms/frame, egl ~0.4 ms). Hand one to the agent's
container with `--extra-docker-compose environment/gpu.docker-compose.yaml`; `rcb_hb.py` then picks
EGL by itself unless `MUJOCO_GL` says otherwise. The overlay is not named `docker-compose.yaml`
because Harbor would load that on every machine, and a device reservation the host cannot satisfy
stops the container from starting.

### Provenance
The instance (`environment/instance.npz` and its byte copy `tests/instance.npz`) is seed 0 (sha `f86d05d210aa`).
