# kinder-constrained-cupboard-i00-standard

| | |
|---|---|
| Benchmark | KinDER |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `kinder-constrained-cupboard-i00-privileged` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `constrained-cupboard` / seed 0 |
| Oracle | `none` — GPT-6 Luna's privileged-mode trajectory, run `codex-gpt6_luna-medium` on the results site, which today's privileged verifier scores 1; it moves the base diagonally by up to 0.14 m a step, beyond standard mode's 0.1 m disc, so it is no standard-mode example, and none is known yet; human review in PR #8 |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `kinder-constrained-cupboard-i00-privileged`: the same KinDER instance (`kinder/ConstrainedCupboard3D-o6-v0`, seed
0) runs in the `sim` sidecar; the agent gets a client and the robot's own sensors -- two
cameras, joint encoders, the base's odometry -- and
never the scene's state or the goal check. No reset: one episode, which is graded.

Task: put the six brown rods lying on the floor (30 cm long) into the row of eleven narrow cupboards standing side by side ahead of the robot, one rod each, each into a cupboard's 40 cm-tall compartment: taking the rods in order of their distance from where the centre of the robot's base starts, nearest first, they go into the 11th, 5th, 2nd, 8th, 4th and 1st cupboard of the row, counted from the robot's left as it faces the row at the start. The task succeeds the moment every rod's centre is inside its compartment: above that compartment's shelf, below the shelf over it, and within the cupboard's 10 cm width and 30 cm depth.

## Difficulty
Geometric: six identical rods, each into the one narrow compartment it is owed (standard mode names them by distance and by place in the row).

## Reference solution
None. Solvability rests on the positive example in `oracle_evidence` (task.toml), checked by a human reviewer (docs/protocol/README.md §4).

## Verification
The sidecar judges the episode as it runs (KinDER's goal check at every control step; the episode ends there) and,
when the collect hook ends the trial, writes that verdict to `/data/final.json` (`graded_by = "live"`): nothing is
replayed to grade it (owner, 2026-10-17). The scene's start is checked against the frozen instance's
recorded state (`scene_sha`) when the episode begins (a mismatch is `instance_mismatch`, infrastructure).
`tests/grade.py` grades `final.json` in a container of its own with no network: success = live success. The video
(`replay.mp4`) is rendered from `trajectory.npz` in one pass after the verdict and never changes it.
No oracle; human review in PR #8. `nop` scores 0.

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
