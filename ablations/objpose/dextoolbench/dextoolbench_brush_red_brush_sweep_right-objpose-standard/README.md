# dextoolbench_brush_red_brush_sweep_right-standard

| | |
|---|---|
| Benchmark | DexToolBench |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `dextoolbench_brush_red_brush_sweep_right-privileged` |
| Simulator / robot | `mujoco` / `kuka-iiwa14-sharpa-ha4` |
| Family / instance | `dextoolbench/brush/red_brush/sweep_right` / seed 0 |
| Oracle | `partial` — SimToolReal's pretrained policy, replayed in this scene, reaches 19/38 goals (solution/; README of dextoolbench_brush_red_brush_sweep_right-privileged) |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:mujoco-0.1.2` |

## Task
Standard-mode twin of `dextoolbench_brush_red_brush_sweep_right-privileged` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol eai-standard/2.1, tooling `rcb_dtb`). The agent sees camera RGB-D and proprioception only.

## Difficulty
Same scene, instance and success rule as `dextoolbench_brush_red_brush_sweep_right-privileged` (see its Difficulty). In standard mode the agent loses privileged state and planning primitives, and has 20 resets instead of unlimited ones: it sees camera images and proprioception only, acts through the client, and every try is a real episode from the same start, of which only the last is graded.

## Reference solution
`solution/`: the privileged-mode oracle's recorded targets submitted through the client (one row per control step)

## Verification
the live episode's verdict (`graded_by = "live"`, no grading replay): the last episode (every control step since the last reset) passes when the goal tracker, run on every executed control step, has reached every goal (`progress` = goals reached / goals in `reward.json`). The frozen start is checked when the episode begins (`RCB_START_SHA`)

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 3 | 16 GiB | 1024 | no GPU | 11 GiB |
| `sim` | 4 | 4 GiB | 1024 | 5 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).

## Details
| | |
|---|---|
| video | `replay.mp4`: one render pass over the trajectory from the frozen start after the verdict (in the sidecar, EGL on its GPU); it never changes the verdict |
