# myosuite-dex-bunny-inspect-i00-standard

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `myosuite-dex-bunny-inspect-i00-privileged` |
| Simulator / robot | `myosuite` / `myohand` |
| Family / instance | `dex_bunny_inspect` / seed 0 |
| Oracle | `none` — no positive example yet (two model attempts failed: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06) and Codex + GPT-6 Luna, effort high, run `codex-gpt6_luna-high`); the task is marked unvalidated (PROTOCOL §2 `validated`); human review in PR #65 |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `MyoHandStanfordbunnyInspect-v0` (MyoHand, 39 muscles) on the same frozen instance as `myosuite-dex-bunny-inspect-i00-privileged`: Move the Stanford bunny along MyoDex's recorded inspect (lift it and turn it to look at it) motion: a reference of the object's pose over 99 control steps (1.98 s), from GRAB motion capture (TCDM / MyoDex). The episode lasts exactly those 99 steps. Success: the object's motion follows the reference's: its centre of mass's displacement since the start within 0.03 m of the reference's displacement since the reference's start, and its rotation since the start within 0.5 rad of the reference's, at at least 90% of the control steps and at the last one, with the displacement error never above 0.05 m. Failure (the episode ends early): MyoDex's termination, the object more than 0.25 m from the reference or from the wrist.
The Stanford bunny lies on the table; the MyoHand is at its pre-grasp pose. Standard mode (eai-standard/2.2): the agent drives the body through a client, with only its own proprioception and the scene's cameras, and 10 resets (only the last episode is graded).

## Difficulty
Same instance and success rule as `myosuite-dex-bunny-inspect-i00-privileged` (first-pass rating: hard). In standard mode the agent loses free resets, the simulator and the object state: it sees camera images and the limb's proprioception, acts in actuator-command chunks, and gets 10 resets, so it has to close the loop on what it sees and learn the body from a few real attempts.

## Reference solution
None. Solvability evidence: no positive example yet (two model attempts failed: Claude Code + Claude Opus 5.5 (run `claude_code-claude_opus_5_5-default`, 2026-10-06) and Codex + GPT-6 Luna, effort high, run `codex-gpt6_luna-high`); the task is marked unvalidated (PROTOCOL §2 `validated`); human review in PR #65.

## Verification
The sim service judges the episode live (the task's rule on the steps it ran: on track over the 99-step reference) and records every executed control step; it checks at the episode's start that the scene is the frozen instance (its recorded state hash; else `instance_mismatch`, an infrastructure failure). The collect hook (`environment/sim/finalize.sh`) ends the service and writes that live verdict to `final.json` (`graded_by` = `live`; nothing is replayed to grade it), then renders `replay.mp4` in one pass over the recorded trajectory, which decides nothing; `tests/grade.py` (separate sandbox, no network) passes iff the live episode succeeded. A missing or unreadable `final.json`, one without a verdict, or a give-up after crashes not all inside the agent's calls is an infrastructure failure (`infra_error = 1`), not the agent's 0. No oracle; human review in PR #65. `nop`: the episode times out, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 7 GiB | 2048 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 4 | 7 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel |
| Service | `environment/sim/server.py` (the adapter) on the shared 2.2 layer `rcb_limited.py` (`embodied_first_exam/standard/`); cameras `left_cam`, `right_cam`, `center_cam`, `hand_top`, `hand_bottom`, `hand_side_inter`, `hand_side_exter`, `plam_lookat` (640 x 480); forward kinematics of the body's links |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering); after the agent's phase the collect hook only renders the video (one pass over the graded episode), it replays nothing to grade |
| Reset budget | 10 (`RCB_RESET_BUDGET`, compose default; PROTOCOL §2): `POST /reset` starts a new episode from the frozen instance; only the last episode is graded, a success ends the trial; results under another budget are reported separately |

### Provenance
The frozen instance (`environment/sim/instance.npz`) and its scene facts were made at generation time; see `tasks/myosuite/README.md`.
