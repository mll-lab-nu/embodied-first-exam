# Protocol (the contract every task follows)

The benchmark imposes as little as possible beyond the Harbor task format. Anything not listed here is
the task's own business: which simulator, how the scene is defined, what the agent's tool API looks like,
how the verifier decides.

## Current five-benchmark mode contract

VLABench, MetaWorld+, RoboCasa, RoboCasa365 and RoboCasa-GR1 use the paired
[limited/unlimited contract](TWO_MODES.md) and `suites/two-modes.json`.
Current tasks live under `limited_tasks/<benchmark>/` and `unlimited_tasks/<benchmark>/`,
with a dataset manifest in each mode/benchmark directory. Historical versions and results
retain their original identities. The unified host runner supplies the trusted lifecycle;
a direct Harbor invocation is insufficient for these tasks.

Both modes allow 3600 seconds of agent execution, excluding initial simulator setup and
post-agent verification. The latest user override removes every episode, submitted-trajectory,
cumulative-step and reset-count cap from unlimited while preserving frozen instances and native
success conditions. Limited retains its per-instance episode cap and prohibits reset.
For limited, the trusted sidecar seals the complete episode; an agent-authored trajectory or
success declaration is not a scoring input. See the mode contract for isolation and replay requirements.

## 1. Task = Harbor task directory
`instruction.md`, `task.toml`, `README.md`, `environment/Dockerfile`, `tests/test.sh`, `solution/solve.sh`,
plus whatever files those need. Tasks are **self-contained**: all task code (agent tooling, verifier) lives
in the task directory and is `COPY`ed by its Dockerfile. Base images under `images/` are infrastructure only
(simulator installs) and contain no benchmark code. A task's identity is its directory digest in
the applicable `dataset.toml`; changing any file is a new task version.

## 2. Deliverable
The agent writes its result under `/app/output/` (declared as `artifacts = ["/app/output/"]` so Harbor
collects it). The format is defined by the task's `instruction.md` and checked by its verifier.

`task_type` (metadata) says what kind of deliverable it is:

| `task_type` | deliverable | grading idea |
|---|---|---|
| `trajectory` | a replayable action sequence for **this** frozen scene instance | open-loop replay in a fresh process |
| `policy` | code that solves held-out instances of the family | success rate over N instances |

## 3. Verifier output
`tests/test.sh` writes `/logs/verifier/reward.txt` (`1` or `0`) and `/logs/verifier/reward.json` with
**numeric fields only** (Harbor rejects strings). Field names, so results are comparable across tasks:

| field | meaning |
|---|---|
| `success` | 1 iff the deliverable completes the task (required) |
| `deterministic` | 1 iff repeated verification agreed (trajectory tasks) |
| `n_actions`, `sim_steps` | length of the deliverable / simulation steps replayed |
| `final_reward` | the simulator's own dense reward at the end, if any |
| `missing_trajectory`, `grader_error` | 1 on those failure modes (so failures are diagnosable) |

## 4. Reproducibility rules
- The verifier must reach the same verdict in a **fresh process** on the same inputs; for physics
  simulators that means restoring the exact initial state (for MuJoCo: `qpos`, `qvel`, `time`, and
  `qacc_warmstart`, then re-anchor controllers and refresh cached observables). The example task
  replays twice and requires identical final-state hashes.
- `environment/Dockerfile` must `FROM` a registry image with a pinned tag or digest (CI checks).
- The verifier's inputs live under `tests/` (copied in after the agent finishes); `instruction.md` never
  references `/tests/`.
- `solution/solve.sh` (oracle) must score 1 and the `nop` agent must score 0.

### Isolated single-episode tasks

Versioned limited tasks may keep the simulator in a private sidecar. In that case the
trusted sidecar, rather than the agent, supplies the complete episode artifact, declared
with a service-specific Harbor artifact entry. Collection and sealing happen after the
agent stops, and verification runs in a separate environment. Agent-written trajectories
or success statements are not scoring inputs. The four public operations are `spec`,
`observe`, `step` and `status`; episode activation and sealing belong to the trusted host.

For these tasks, oracle admission uses the task's documented trusted lifecycle driver:
it sends the reference's native actions through the same public `step` interface and must
score 1. A separate empty episode must score 0. This is an explicit alternative to invoking
`harbor run -a oracle` directly; report the actual Harbor agent and the driver's oracle role
separately. Do not install the reference or private simulator in the evaluated agent's
container. Neither a source task's earlier oracle result nor static isolation checks replace
oracle/nop admission of the versioned sidecar task.

The sidecar records attempted controls and the physical steps of partial failures. Native
online success, success in fresh replay, and online/replay determinism are all required.
The agent deadline begins only once the service is ready and the agent can act; collection
and replay have separate timeouts. Modes and their budgets must remain explicit in reports.

## 5. Budget reporting
Report success **and** cost. Harbor records tokens, $, turns and wall-clock; tasks should additionally
expose simulation cost (`sim_steps`, resets) through their tooling so agents can be compared under equal
budgets (align `--ak reasoning_effort`, `max_turns`, budget caps and `[agent].timeout_sec` first).

## 6. Metadata
See `docs/TAXONOMY.md`: `simulator`, `robot`, `family`, `task_type`, `tier` (`privileged` = state-based
perception allowed; `perception` = RGB-D only), `expert_time_estimate_hours`, author fields.
