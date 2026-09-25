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
In limited mode (`mode = "limited"`, `docs/LIMITED_MODE_1_1.md`) the deliverable is the episode itself: the
simulator sidecar records it as the trajectory, and `/app/output/` only keeps the agent's script.

`task_type` (metadata) says what kind of deliverable it is:

| `task_type` | deliverable | grading idea |
|---|---|---|
| `trajectory` | a replayable action sequence for **this** frozen scene instance | open-loop replay in a fresh process |
| `policy` | code that solves held-out instances of the family | success rate over N instances |

**`instruction.md` must tell the agent to save the deliverable as soon as it has any version, to overwrite
it as it improves, and must state the wall-clock budget and tell it not to stop early.** The timeout
arrives without warning, so an agent that saves only at the end scores 0 and measures nothing; and one that
cannot see its score tends to stop long before the budget (5 of 10 full-mode runs of GPT-6 Luna stopped,
unsolved, after 23–46 of 60 min).

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
- The verifier's inputs live under `tests/` (copied in after the agent finishes); `instruction.md` never
  references `/tests/`.
- `solution/solve.sh` (oracle) must score 1 and the `nop` agent must score 0.
- **Reference solutions live only under `solution/`** (Harbor mounts it at `/solution/` for the oracle agent only).
  Nothing the agent can reach — the task image, base images, tooling, docs inside the container — may contain
  a solution or point to one. Lesson from the first agent run: it found cap-x's built-in `oracle_code` through
  the tooling's `run-oracle` command and replayed it; base images now scrub those strings.
- **A grader that ships with the simulator is an answer key too** (a dense reward, a success predicate):
  with it the task is to invert an expression rather than to control a robot. Delete it from the base
  image, ship it only under `tests/`, and patch it back inside the verifier, so the score still comes from
  upstream's own code. `instruction.md` must then describe the scoring in prose — what is measured, how the
  terms combine, order-of-magnitude targets, what ends the episode — with no tolerance parameters, exact
  weights, per-step scale, or what any particular policy scores.
- **Deleting an answer key only counts if the agent cannot fetch another copy**: the network, an earlier
  Docker layer, `.git`, stale `__pycache__`, a sibling task's `tests/`. Tasks set `[agent] network_mode =
  "allowlist"` with `allowed_hosts = []` (the model endpoint is opted in per run with
  `--allow-agent-host <host>`) and `[verifier] network_mode = "no-network"`.
  Method and checklist: [docs/LEAKAGE.md](LEAKAGE.md).

## 5. Budget reporting
Report success **and** cost. Harbor records tokens, $, turns and wall-clock; tasks should additionally
expose simulation cost (`sim_steps`, resets) through their tooling so agents can be compared under equal
budgets (align `--ak reasoning_effort`, `max_turns`, budget caps and `[agent].timeout_sec` first).

## 6. Metadata
See `docs/TAXONOMY.md`: `simulator`, `robot`, `family`, `task_type`, `tier` (`privileged` = state-based
perception allowed; `perception` = RGB-D only), `expert_time_estimate_hours`, author fields.

`tier` describes *observation* only, so it cannot express the two other things an agent may or may not
see: the simulator's white-box model, and the scoring function. Until there are fields for them
(`model_visibility` / `reward_visibility`, proposed in `local_docs/plan/04-framework-suggestions.md`),
a task states both in its `README.md`. The HumanoidBench tasks are `model_visibility = white_box`,
`reward_visibility = black_box`.
