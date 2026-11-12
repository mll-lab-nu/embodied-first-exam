# kinder-dynamo-i00-standard

| | |
|---|---|
| Benchmark | KinDER |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `kinder-dynamo-i00-privileged` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `dynamo` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `kinder-dynamo-i00-privileged`: the same KinDER instance (`kinder/Dynamo3D-o3-v0`, seed
0) runs in the `sim` sidecar; the agent gets a client and the robot's own sensors -- two
cameras, joint encoders, the base's odometry -- and
never the scene's state or the goal check. No reset: one episode, which is graded.

Task: drive the robot into the translucent green square marked on the floor; three chairs stand in the way and can be pushed. The task succeeds the moment the centre of the robot's base is inside the square. (The red, blue and yellow squares only mark where the chairs started.)

## Difficulty
Nonprehensile: three chairs stand between the robot and the floor square, and the base can push them. The benchmark's fixture: the pipeline check, with an oracle in both modes.

## Reference solution
`solution/oracle_replay.py` sends the privileged oracle's 101 moves, turned into the odometry frame (`solution/oracle_actions.npy`), through the client: success at step 101, no privileged information at run time.

## Verification
The sidecar judges the episode as it runs (KinDER's goal check at every control step; the episode ends there) and,
when the collect hook ends the trial, writes that verdict to `/data/final.json` (`graded_by = "live"`): nothing is
replayed to grade it (owner, 2026-10-17). The scene's start is checked against the frozen instance's
recorded state (`scene_sha`) when the episode begins (a mismatch is `instance_mismatch`, infrastructure).
`tests/grade.py` grades `final.json` in a container of its own with no network: success = live success. The video
(`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and never changes it.
The oracle (`solution/solve.sh`) scores 1; `nop` scores 0.

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
