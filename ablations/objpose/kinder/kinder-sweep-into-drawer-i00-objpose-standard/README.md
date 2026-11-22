# kinder-sweep-into-drawer-i00-standard

| | |
|---|---|
| Benchmark | KinDER |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `kinder-sweep-into-drawer-i00-privileged` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `sweep-into-drawer` / seed 0 |
| Oracle | `none` — GPT-6 Luna's privileged-mode trajectory of 2026-10-04, run `codex-gpt6_luna-medium` on the results site, which today's privileged verifier scores 1 (it moves the base diagonally by up to 0.13 m a step, beyond standard mode's 0.1 m disc, so it is no standard-mode example); in standard mode, the graded episode of run `codex-gpt6_1_sol-high` of 2026-10-03 (960 control steps, no reset), which the standard service scored 1 (live, fresh replay, deterministic); human review in PR #8 |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
Standard mode (robot as a service, `eai-standard/2.1`) of `kinder-sweep-into-drawer-i00-privileged`: the same KinDER instance (`kinder/SweepIntoDrawer3D-o5-v0`, seed
0) runs in the `sim` sidecar; the agent gets a client and the robot's own sensors -- two
cameras, joint encoders, the base's odometry -- and
never the scene's state or the goal check. No reset: one episode, which is graded.

Task: get the five small dark-red cubes on top of the kitchen island into the middle drawer of the island's upper row of drawers, which starts closed; a wiper lies next to the cubes. The task succeeds the moment all five cubes' centres are inside that drawer, each at least 2.5 cm from the drawer's two side walls.

## Difficulty
Nonprehensile, tool use, dynamics: open a closed drawer, then sweep five small cubes off the counter into it with a wiper. KinDER's paper reports at most 0.14 success for its best method on this variant and 0.00 for sampling MPC on the true simulator.

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
