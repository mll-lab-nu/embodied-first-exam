# kinder-constrained-cupboard-i00-privileged

| | |
|---|---|
| Benchmark | KinDER |
| Mode | privileged |
| Twin | `kinder-constrained-cupboard-i00-standard` |
| Simulator / robot | `kinder` / `tidybot-plus-plus` |
| Family / instance | `constrained-cupboard` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `none` — GPT-6 Luna's privileged-mode trajectory, run `codex-gpt6_luna-medium` on the results site, which today's privileged verifier scores 1; it moves the base diagonally by up to 0.14 m a step, beyond standard mode's 0.1 m disc, so it is no standard-mode example, and none is known yet; human review in PR #8 |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:kinder-0.1.6` |

## Task
KinDER `kinder/ConstrainedCupboard3D-o6-v0` (Dynamic3D, TidyBot++), seed 0, privileged mode: the agent has the simulator and its state and
hands in one trajectory, replayed open-loop in a fresh process. Its standard-mode twin is `kinder-constrained-cupboard-i00-standard`.

Task: put the six brown rods lying on the floor (30 cm long) into the six 40 cm-tall compartments of the row of eleven narrow cupboards standing side by side, one rod each, as the state names pair them: rod `cuboid_i` into cupboard `cupboard_i` for i = 0 to 5, whose tall compartment is the upper one in `cupboard_0` to `cupboard_2` and the lower one in `cupboard_3` to `cupboard_5`. The task succeeds the moment every rod's centre is inside its compartment: above that compartment's shelf, below the shelf over it, and within the cupboard's 10 cm width and 30 cm depth.

## Difficulty
Geometric: six identical rods, each into the one narrow compartment it is owed (standard mode names them by distance and by place in the row).

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
