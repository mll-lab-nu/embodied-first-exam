# kinder-scoop-pour-i01-standard

| | |
|---|---|
| Benchmark | KinDER |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `kinder-scoop-pour-i01-privileged` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `scoop-pour` / seed 0 |
| Oracle | `none` — none yet: no positive example is known for this instance (human review pending) |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `kinder-scoop-pour-i01-privileged`: the same KinDER instance (`kinder/ScoopPour3D-o50-v0`, seed
0) runs in the `sim` sidecar; the agent gets a client and the robot's own sensors -- two
cameras, joint encoders, the base's odometry -- and
never the scene's state or the goal check. No reset: one episode, which is graded.

Task: move all 50 small dark-red cubes from the yellow bin into the green bin; a scoop is in the scene. The task succeeds the moment every cube's centre is inside the green bin, at least 1 cm from each of its inner walls and at least 0.5 cm below its rim.

## Difficulty
Nonprehensile, tool use, dynamics: move 50 small cubes from one bin to another with a scoop, each ending well inside the target bin. The variant is upstream's o50 (both cube families use theirs, tasks/kinder/README.md).

## Reference solution
None, and no positive example yet: the task is unvalidated (`validated = false`, docs/protocol/README.md §2, §4) until a human review records one.

## Verification
The sidecar judges the episode as it runs (KinDER's goal check at every control step; the episode ends there) and,
when the collect hook ends the trial, writes that verdict to `/data/final.json` (`graded_by = "live"`): nothing is
replayed to grade it (owner, 2026-10-17). The scene's start is checked against the frozen instance's
recorded state (`scene_sha`) when the episode begins (a mismatch is `instance_mismatch`, infrastructure).
`tests/grade.py` grades `final.json` in a container of its own with no network: success = live success. The video
(`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and never changes it.
No oracle; no positive example yet (human review pending). `nop` scores 0.

Benchmark notes: `tasks/kinder/README.md`.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 16 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any 8 GB+ NVIDIA GPU (RTX 4090 / L4).
