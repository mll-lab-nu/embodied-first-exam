# myosuite-dex-apple-lift-i00-privileged

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | privileged |
| Twin | `myosuite-dex-apple-lift-i00-standard` |
| Simulator / robot | `myosuite` / `myohand` |
| Family / instance | `dex_apple_lift` / seed 0 |
| Oracle | `none` — a successful model trial on this frozen instance: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06), trial `myosuite-dex-apple-lift-i00-priv__j5qaRCZ` (57 rows); today's verifier scores its trajectory 1 in two fresh trials (tasks/myosuite/README.md); human review in PR #65 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `MyoHandAppleLift-v0` (MyoHand, a musculoskeletal model of a human forearm and hand, 39 muscles and 6 other actuators): Move the apple along MyoDex's recorded lift motion: a reference of the object's pose over 57 control steps (1.14 s), from GRAB motion capture (TCDM / MyoDex). The episode lasts exactly those 57 steps. Success: the object's motion follows the reference's: its centre of mass's displacement since the start within 0.03 m of the reference's displacement since the reference's start, at at least 90% of the control steps and at the last one, with the displacement error never above 0.05 m. Failure (the episode ends early): MyoDex's termination, the object more than 0.25 m from the reference or from the wrist.
An apple lies on the table; the MyoHand (with a 6-DoF positioned wrist) is at its pre-grasp pose next to it. The deliverable is one replayable trajectory of actuator commands (`/app/output/trajectory.npz`, `(T, 45)`, one row per 20 ms control step).

## Difficulty
First-pass rating: hard. The action is muscle-level (39 muscles, each only pulling, several crossing more than one joint, with activation delays): the agent has to build its own joint control from muscle excitations. The whole recorded motion has to be followed with the object in hand, within a few centimetres, for 57 control steps.

## Reference solution
None. Solvability evidence: a successful model trial on this frozen instance: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06), trial `myosuite-dex-apple-lift-i00-priv__j5qaRCZ` (57 rows); today's verifier scores its trajectory 1 in two fresh trials (tasks/myosuite/README.md); human review in PR #65.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff the episode ends in success (on track over the 57-step reference). No oracle; human review in PR #65. `nop`: no trajectory, reward 0.

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
| Instance | `MyoHandAppleLift-v0` after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); state hash `bd23842e5afc7253`, checked on every load |
| Actions | 45 actuator commands per control step (20 ms, 10 physics substeps); success rule `track` (tasks/myosuite/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The frozen instance (`environment/instance.npz`) and its scene facts were made at generation time; see `tasks/myosuite/README.md`.
