# kinder-sweep-into-drawer-i00-privileged

| | |
|---|---|
| Benchmark | KinDER |
| Mode | privileged |
| Twin | `kinder-sweep-into-drawer-i00-standard` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `sweep-into-drawer` / seed 0 |
| Oracle | `none` — GPT-6 Luna's privileged-mode trajectory of 2026-10-04, run `codex-gpt6_luna-medium` on the results site, which today's privileged verifier scores 1 (it moves the base diagonally by up to 0.13 m a step, beyond standard mode's 0.1 m disc, so it is no standard-mode example); in standard mode, the graded episode of run `codex-gpt6_1_sol-high` of 2026-10-03 (960 control steps, no reset), which the standard service scored 1 (live, fresh replay, deterministic); human review in PR #8 |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
KinDER `kinder/SweepIntoDrawer3D-o5-v0` (Dynamic3D, TidyBot++), seed 0, privileged mode: the agent has the simulator and its state and
hands in one trajectory, replayed open-loop in a fresh process. Its standard-mode twin is `kinder-sweep-into-drawer-i00-standard`.

Task: get the five small dark-red cubes on top of the kitchen island into the middle drawer of the island's upper row of drawers, which starts closed; a wiper lies next to the cubes. The task succeeds the moment all five cubes' centres are inside that drawer, each at least 2.5 cm from the drawer's two side walls.

## Difficulty
Nonprehensile, tool use, dynamics: open a closed drawer, then sweep five small cubes off the counter into it with a wiper. KinDER's paper reports at most 0.14 success for its best method on this variant and 0.00 for sampling MPC on the true simulator.

## Reference solution
None. Solvability rests on the positive example in `oracle_evidence` (task.toml), checked by a human reviewer (docs/protocol/README.md §4).

## Verification
One open-loop replay of `/app/output/trajectory.npz` from `tests/instance.json` in a fresh process, in a container of
its own (`tests/Dockerfile`, no network): pass iff it reaches the goal within 1000 control steps. No oracle; human review in PR #8. `nop` scores 0.

Benchmark notes: `tasks/kinder/README.md`.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 16 | 7 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.
