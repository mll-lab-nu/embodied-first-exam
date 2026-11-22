# kinder-sweep-simple-i01-standard

| | |
|---|---|
| Benchmark | KinDER |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `kinder-sweep-simple-i01-privileged` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `sweep-simple` / seed 0 |
| Oracle | `none` — none yet: no positive example is known for this instance (human review pending) |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `kinder-sweep-simple-i01-privileged`: the same KinDER instance (`kinder/SweepSimple3D-o50-sweep_the_blocks_to_the_right_side_of_the_kitchen_island-v0`, seed
0) runs in the `sim` sidecar; the agent gets a client and the robot's own sensors -- two
cameras, joint encoders, the base's odometry -- and
never the scene's state or the goal check. No reset: one episode, which is graded.

Task: get the fifty small dark-red cubes scattered on the floor into the translucent grey box marked on the floor at the end of the kitchen island (the free-standing white-topped counter) nearest the robot; a wiper stands on the floor near the cubes. The task succeeds the moment all fifty cubes' centres are inside that box.

## Difficulty
Nonprehensile, tool use: fifty small cubes spread over 2 m² of floor into a box marked at the kitchen island's end, with a wiper standing about 1.7 m from where the robot starts. The variant is upstream's o50 (both cube families use theirs, tasks/kinder/README.md); of its three goals, the one upstream's README gives as the family's example.

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
