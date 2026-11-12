# myosuite-soccer-i00-privileged

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | privileged |
| Twin | `myosuite-soccer-i00-standard` |
| Simulator / robot | `myosuite` / `myolegs` |
| Family / instance | `soccer` / seed 0 (allowed seeds: [0, 1, 2]; PROTOCOL §2) |
| Oracle | `none` — a successful model trial on this frozen instance: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06), trial `myosuite-soccer-i00-privileged__DuXNvn4` (308 rows); today's verifier scores its trajectory 1 in two fresh trials (tasks/myosuite/README.md); human review in PR #65 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `myoChallengeSoccerP1-v0` (MyoLegs, a free-standing musculoskeletal model of a human torso and both legs, 290 muscles): Score a goal: kick the ball into the goal, past the goalkeeper, within 10 s of simulated time (MyoChallenge 2025 Soccer P1: the ball's centre crosses the goal line between the posts and under the bar). Failure (the episode ends): the pelvis below 0.2 m (fallen), or the time limit.
A musculoskeletal body with two legs stands on a soccer pitch; a ball lies in front of it and a goalkeeper guards the goal. The deliverable is one replayable trajectory of actuator commands (`/app/output/trajectory.npz`, `(T, 290)`, one row per 10 ms control step).

## Difficulty
First-pass rating: hard. The action is muscle-level (290 muscles, each only pulling, several crossing more than one joint, with activation delays): the agent has to build its own joint control from muscle excitations. Success is the challenge's own event; nothing short of it counts, and the challenge's failure conditions and time limit apply.

## Reference solution
None. Solvability evidence: a successful model trial on this frozen instance: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06), trial `myosuite-soccer-i00-privileged__DuXNvn4` (308 rows); today's verifier scores its trajectory 1 in two fresh trials (tasks/myosuite/README.md); human review in PR #65.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff the episode ends in success (the challenge's own success event). No oracle; human review in PR #65. `nop`: no trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 4096 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel |
| Instance | `myoChallengeSoccerP1-v0` after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); state hash `ccad133b7a1ad0fd`, checked on every load |
| Actions | 290 actuator commands per control step (10 ms, 10 physics substeps); success rule `event` (tasks/myosuite/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The frozen instance (`environment/instance.npz`) and its scene facts were made at generation time; see `tasks/myosuite/README.md`.
