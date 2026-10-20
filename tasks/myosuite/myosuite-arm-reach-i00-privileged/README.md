# myosuite-arm-reach-i00-privileged

| | |
|---|---|
| Benchmark | MyoSuite |
| Mode | privileged |
| Twin | `myosuite-arm-reach-i00-standard` |
| Simulator / robot | `myosuite` / `myoarm` |
| Family / instance | `arm_reach` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` |

## Task
MyoSuite `myoArmReachFixed-v0` (MyoArm, a musculoskeletal model of a human shoulder, arm and hand, 34 muscles): Bring the index fingertip to the target point in space: its distance below 0.0125 m for 50 consecutive control steps (1.0 s). Failure (the episode ends, from the third control step on): the distance above 1.00 m.
The arm hangs at the side; a small sphere in front of the body marks the target for the index fingertip. The deliverable is one replayable trajectory of actuator commands (`/app/output/trajectory.npz`, `(T, 34)`, one row per 20 ms control step).

## Difficulty
First-pass rating: medium. The action is muscle-level (34 muscles, each only pulling, several crossing more than one joint, with activation delays): the agent has to build its own joint control from muscle excitations. MyoSuite's goal has to hold for 1.0 s, so passing through the goal does not count.

## Reference solution
MyoSuite's own NPG baseline policy for `myoArmReachFixed-v0` (`myosuite/agents/baslines_NPG/`, shipped in the MyoSuite wheel and removed from the image), rolled out from the frozen instance and cut at the first success: `solution/oracle.npy`, 128 rows (float32-exact, so the standard twin's client executes the same rows), success after 128 control steps. Replayed and saved by `solution/solve.sh`; re-checked in two fresh sessions (same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: two replays of `/app/output/trajectory.npz`, each in a fresh process, from the verifier's own copy of the instance (`tests/instance.npz`; the rebuilt start state is checked against its recorded hash); pass iff both episodes end in success (the goal held 50 control steps) in the same state (`deterministic`). `nop`: no trajectory, reward 0.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 8 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: memory: privileged container median 6.2 GB, sim p90 1.4 GB, verifier 1.4 GB, mem_guard (docker memory per container, an RTX 4090 workstation, 10-02..10); CPU-only; CPU author estimate
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 10 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 10 GiB memory. Limits measured: memory: the [environment] cap 8 GiB, which every past trial ran under (docker peak 8.0 GiB over 18 samples, mem_guard (docker memory incl. page cache, top-4 containers every 10 min, an RTX 4090 workstation, 10-02..10)); processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details
| | |
|---|---|
| Upstream | MyoSuite 2.12.2 (Apache-2.0) on MuJoCo 3.6.0, the models that ship in its wheel |
| Instance | `myoArmReachFixed-v0` after `seed(0)` and `reset(seed=0)` (`rcb_myosuite.py make-instance`); state hash `525e013b2c9a385b`, checked on every load |
| Actions | 34 actuator commands per control step (20 ms, 10 physics substeps); success rule `hold` (tasks/myosuite/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |

### Provenance
The frozen instance (`environment/instance.npz`), its scene facts and the reference solution (`solution/oracle.npy`) were made at generation time; see `tasks/myosuite/README.md`.

### Change Log
- 2026-10-10 (review round 3): `tests/grade.py` only. A byte that is not valid UTF-8 in the session log
  the agent's tools write (`/app/output/rcb_session_log.jsonl`, read only for the self-reported `agent_*` cost fields)
  stopped the grader before it wrote a reward, so the trial had no verdict; the log is now read tolerantly and can no
  longer decide anything. A trial whose log is valid is graded as before; the pass rule is unchanged.
- 2026-10-10 (review round 3): `tests/grade.py`, whose failure a 0 is. The width of the rows is checked
  against the instance's actuators before any replay (a file that is no trajectory for this instance is
  `bad_trajectory`, as before). After that check a replay process that gives no result (out of time, killed for
  memory, not started) is `replay_failed` with `grader_error = 1` and `infra_error = 1`; it was booked as the agent's
  `bad_trajectory`. Every `reward.json` now carries `infra_error` (1 next to every `grader_error`, so also when the
  verifier's host does not rebuild the frozen instance). The pass rule is unchanged; a trial graded `bad_trajectory`
  before this date whose rows had the right shape was an infrastructure failure.
