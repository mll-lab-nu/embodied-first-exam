# myosuite-sarc-key-turn-i00-privileged

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | privileged |
| Twin | `myosuite-sarc-key-turn-i00-standard` |
| Simulator / robot | `myosuite` / `myohand` |
| Family / instance | `sarc_key_turn` / seed 0 |
| Oracle | `none` — a successful model trial on this frozen instance: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06), trial `myosuite-sarc-key-turn-i00-privi__iVBaqTS` (230 rows); today's verifier scores its trajectory 1 in two fresh trials (tasks/myosuite/README.md); human review in PR #65 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `myoSarcHandKeyTurnFixed-v0` (MyoHand, a musculoskeletal model of a human forearm and hand, 39 muscles): Turn the key held between the thumb and the index finger by more than 3.14 rad (half a turn). Success: the key's hinge angle above 3.14 rad for 50 consecutive control steps (1.0 s). Failure (the episode ends): the index or thumb tip more than 0.10 m from the key head. The muscles are sarcopenic: MyoSuite's sarcopenia condition halves every muscle's maximum isometric force.
As key_turn: the key sits in a lock in front of the palm, its head between the thumb and the index finger. The deliverable is one replayable trajectory of actuator commands (`/app/output/trajectory.npz`, `(T, 39)`, one row per 20 ms control step).

## Difficulty
First-pass rating: hard. The action is muscle-level (39 muscles, each only pulling, several crossing more than one joint, with activation delays): the agent has to build its own joint control from muscle excitations. MyoSuite's goal has to hold for 1.0 s, so passing through the goal does not count.

## Reference solution
None. Solvability evidence: a successful model trial on this frozen instance: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06), trial `myosuite-sarc-key-turn-i00-privi__iVBaqTS` (230 rows); today's verifier scores its trajectory 1 in two fresh trials (tasks/myosuite/README.md); human review in PR #65.

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff the episode ends in success (the goal held 50 control steps). No oracle; human review in PR #65. `nop`: no trajectory, reward 0.

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
| Instance | `myoSarcHandKeyTurnFixed-v0` after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); state hash `0f5e087eca267632`, checked on every load |
| Actions | 39 actuator commands per control step (20 ms, 10 physics substeps); success rule `hold` (tasks/myosuite/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The frozen instance (`environment/instance.npz`) and its scene facts were made at generation time; see `tasks/myosuite/README.md`.
