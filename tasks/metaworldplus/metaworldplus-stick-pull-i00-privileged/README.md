# metaworldplus-stick-pull-i00-privileged

| | |
|---|---|
| Benchmark | MetaWorld+ |
| Mode | privileged |
| Twin | `metaworldplus-stick-pull-i00-standard` |
| Simulator / robot | `mujoco` / `sawyer` |
| Family / instance | `metaworld/stick-pull` / seed 1 (allowed seeds: [1, 2, 3]; PROTOCOL §2) |
| Oracle | `full` |
| Agent time budget | 1800 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:metaworld-0.1.0` |

## Task
A Sawyer arm at a table, Meta-World's `stick-pull-v3` (reward v2) on one frozen instance: Use the stick to pull the target object. The agent writes a
trajectory of Meta-World's native actions with full privileged state and unlimited resets; it is graded by replay on
the state after the last action. Benchmark notes in
`tasks/metaworldplus/README.md`.

## Difficulty
Full privileged state, unlimited resets and self-replay: this mode is the control for the standard twin
(`metaworldplus-stick-pull-i00-standard`). It is reported, but not in the main (standard-mode) table, because it is
saturated under final-state grading (decision on the benchmark proposal, #10). What remains hard here is planning the
contacts (grasp, push, turn) with a mocap-driven hand whose wrist does not rotate, within 500 actions.

## Reference solution
Meta-World's scripted policy for `stick-pull-v3` (`metaworld/policies/`, removed from the image), run on this instance up to
its first success: 119 actions in `solution/oracle.npz`.

In this environment the success state does not persist on its own: after the oracle's last action, holding still for 10 control steps loses it. Graded on the final state, a trajectory must end at that moment.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay in a fresh process from the verifier's own copy of
the instance; `success` = success on the final state. Oracle: a fresh-process replay ends in the
live episode's state (hash `16d2898c4471…`) and succeeds. `nop`: no trajectory, reward 0; the instance is
not solved at the start.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 5 GiB | 1024 | no GPU | 10 GiB |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| source | [Meta-World](https://github.com/Farama-Foundation/Metaworld) @ 59fc34d (MIT) on MuJoCo 3.3.0; image `efe:metaworld-0.1.0` |
| instance | Meta-World's reset randomization with seed 1; MuJoCo state, model arrays, env caches and RNG frozen in `instance.npz` (SHA-256 `feb8f30ea035…`, checked on load) |
| deliverable | `(T, 4)` native actions `[dx, dy, dz, grip]`, 1 ≤ T ≤ 500 (Meta-World's `max_path_length`) |
| success | Meta-World's own check (`evaluate_state`) on the state after the last action. The thermos's handle (the loop the stick goes into) is within 12 cm of the target point AND the stick is still in the handle: the stick's far end is at or beyond the handle in x, within 4 cm of it in y and within 6 cm of it in z. A thermos that is at the target with the stick pulled out does not count. |
| actions | no `joint_position`: Meta-World's Sawyer has no arm actuators (the hand is a mocap body, the arm follows it) |
