# myosuite-dex-cup-pour-i00-privileged

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | privileged |
| Twin | `myosuite-dex-cup-pour-i00-standard` |
| Simulator / robot | `myosuite` / `myohand` |
| Family / instance | `dex_cup_pour` / seed 0 |
| Oracle | `none` — no positive example yet (two model attempts failed: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06) and Codex + GPT-6 Luna, effort high, run `codex-gpt6_luna-high`); the task is marked unvalidated (PROTOCOL §2 `validated`); human review in PR #65 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `MyoHandCupPour-v0` (MyoHand, a musculoskeletal model of a human forearm and hand, 39 muscles and 6 other actuators): Move the cup along MyoDex's recorded pour motion, lifting it and tilting it as if pouring. The reference is the cup's pose over 81 control steps, from GRAB motion capture (TCDM / MyoDex), and the episode lasts exactly those 81 steps. At the last control step and at nine in ten or more of all control steps, the cup's centre of mass must have moved since the start to within about 3 cm of how the reference has moved since its start, and the cup must have turned since the start to within about 25 degrees of how the reference has turned. That position error must never go above about 5 cm. The episode ends early in failure, by MyoDex's own termination rule, if the cup gets more than about 25 cm from the reference or from the wrist.
A cup stands on the table; the MyoHand is at its pre-grasp pose. The deliverable is one replayable trajectory of actuator commands (`/app/output/trajectory.npz`, `(T, 45)`, one row per 20 ms control step).

## Difficulty
First-pass rating: hard. The action is muscle-level (39 muscles, each only pulling, several crossing more than one joint, with activation delays): the agent has to build its own joint control from muscle excitations. The whole recorded motion has to be followed with the object in hand, within a few centimetres, for 81 control steps.

## Reference solution
None. Solvability evidence: no positive example yet (two model attempts failed: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06) and Codex + GPT-6 Luna, effort high, run `codex-gpt6_luna-high`); the task is marked unvalidated (PROTOCOL §2 `validated`); human review in PR #65.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff the episode ends in success (on track over the 81-step reference). No oracle; human review in PR #65. `nop`: no trajectory, reward 0.

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
| Instance | `MyoHandCupPour-v0` after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); state hash `b337ee643ada80d1`, checked on every load |
| Actions | 45 actuator commands per control step (20 ms, 10 physics substeps); success rule `track` (tasks/myosuite/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The frozen instance (`environment/instance.npz`) and its scene facts were made at generation time; see `tasks/myosuite/README.md`.
