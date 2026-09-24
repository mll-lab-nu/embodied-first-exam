# Protocol (the contract every task follows)

The benchmark imposes as little as possible beyond the Harbor task format. Anything not listed here is
the task's own business: which simulator, how the scene is defined, what the agent's tool API looks like,
how the verifier decides.

## 1. Task = Harbor task directory
`instruction.md`, `task.toml`, `README.md`, `environment/Dockerfile`, `tests/test.sh`, `solution/solve.sh`,
plus whatever files those need. Tasks are **self-contained**: all task code (agent tooling, verifier) lives
in the task directory and is `COPY`ed by its Dockerfile. Base images under `images/` are infrastructure only
(simulator installs) and contain no benchmark code. A task's identity is its directory digest in
`tasks/dataset.toml`; changing any file is a new task version.

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
| `video_rendered` | 1 if the verifier also wrote a human-viewable `/logs/verifier/replay.mp4` (recommended; never affects the verdict) |

## 4. Reproducibility rules
- The verifier must reach the same verdict in a **fresh process** on the same inputs; for physics
  simulators that means restoring the exact initial state (for MuJoCo: `qpos`, `qvel`, `time`, and
  `qacc_warmstart`, then re-anchor controllers and refresh cached observables). The example task
  replays twice and requires identical final-state hashes.
- `environment/Dockerfile` must `FROM` a registry image with a pinned tag or digest (CI checks).
- **The verifier runs in its own sandbox, never in the container the agent controlled.** `task.toml` sets
  `[verifier] environment_mode = "separate"` and `tests/Dockerfile` builds the verifier image (same simulator base
  image, the verifier's own copies of the tooling and the frozen instance baked into `/tests/`; `tests/docker-compose.yaml`
  for a GPU reservation if replay needs one). Harbor uploads only the declared artifacts (`/app/output/`) into it.
  Reason, measured 2026-09-23: in Harbor's default *shared* mode the tests run inside the agent's container after
  `/tests/` is copied in, so an agent that is root there can patch the task's `check_success` (or the interpreter) —
  a do-nothing trajectory then scores 1. The same cheat scores 0 under the separate sandbox. `ci_checks/check-verifier-isolation.sh`
  enforces this. `instruction.md` never references `/tests/`.
- **Agent egress is a per-run choice, default open.** Harbor's default is `public`; the reference solutions we scrub
  from the agent image are public upstream (RoboTwin's `play_once` on GitHub, this repo's `solution/`), so a run that
  must rule out "the agent fetched the answer" flips every task to model-APIs-only with
  `scripts/set_agent_egress.py allowlist` (and back with `public`). Measured 2026-09-24: under that allowlist Codex
  (ChatGPT login) still reaches its model while GitHub and PyPI return nothing, and the limited-mode sidecar stays
  reachable; an empty allowlist breaks the agent. CI only checks that an allowlist, when set, lists hosts.
- `solution/solve.sh` (oracle) must score 1 and the `nop` agent must score 0.
- **Reference solutions live only under `solution/`** (Harbor mounts it at `/solution/` for the oracle agent only).
  Nothing the agent can reach — the task image, base images, tooling, docs inside the container — may contain
  a solution or point to one. Lesson from the first agent run: it found cap-x's built-in `oracle_code` through
  the tooling's `run-oracle` command and replayed it; base images now scrub those strings.

## 5. Budget reporting
Report success **and** cost. Harbor records tokens, $, turns and wall-clock; tasks should additionally
expose simulation cost (`sim_steps`, resets) through their tooling so agents can be compared under equal
budgets (align `--ak reasoning_effort`, `max_turns`, budget caps and `[agent].timeout_sec` first).

## 6. Metadata
See `docs/TAXONOMY.md`: `simulator`, `robot`, `family`, `task_type`, `tier` (`privileged` = state-based
perception allowed; `perception` = RGB-D only), `expert_time_estimate_hours`, author fields.
