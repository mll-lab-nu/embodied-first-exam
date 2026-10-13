# Policy adaptation protocol: eai-policy/1.0

Status: implemented for Neural Lander; native Harbor 0.23.0 Docker oracle/nop validation passed on both instances with resource enforcement.

## Lifecycle and transport

The agent uses Harbor's native agent in `main`. The independent `sim` container serves localhost port 8000 via Harbor's network namespace wiring. No simulator directory, state volume, Docker socket, or private asset is mounted into `main`. The verifier runs separately under Harbor's `no-network` phase policy after trusted collection; see the [native validation details](benchmarks/quadrotor-landing.md#native-harbor-packaging-and-validation) for the observed boundary and limitations.

| Request | Input | Output / effect |
|---|---|---|
| `GET /health` | none | Startup readiness only; does not start the policy clock. |
| `GET /spec` | none | Protocol, task type, operation names. |
| `POST /describe` | `{}` | Public task and scoring specification, numeric policy default, remaining rounds and wall-clock deadline. |
| `POST /deploy` | `policy`, `diagnosis` | Executes a numeric candidate on the fixed adaptation cases; returns round id, policy hash, exact noisy measurements and timestamped JPEG frames. |
| `POST /seal` | `round_id`, `summary` | Irreversibly selects a completed candidate and closes adaptation. No held-out feedback is returned. |

Bodies are strict JSON, at most 8192 bytes, with no duplicate keys or nonfinite numbers. Diagnoses/summaries are bounded to 2000 characters. Policy validation allows only the documented keys, dimensions and numerical bounds. Invalid requests return generic HTTP 400, unavailable evaluator HTTP 503; private diagnostics never enter a response. Busy requests are rejected; there is only one simulator operation at a time. The HTTP server has a bounded worker pool and socket timeouts. Unknown paths do not serve files.

Every accepted deployment consumes one of three rounds before simulation. Each round uses the same three adaptation cases; final evaluation uses six disjoint cases. The agent may optimize locally as often as its resource/time budget permits. The action ABI is a fixed feedback controller with six tunable gains/timings and a 3×14 residual coefficient matrix; this release does not evaluate arbitrary controller programs.

The full-model oracle references are frozen before readiness. Harbor's agent time limit is authoritative: on agent exit or timeout, its collect hook closes submissions. As a fallback the service closes after the same duration from the first policy API call. Health checks do not start that clock. No new round, seed bank or budget is allocated on process restart. Interrupted deployments become infrastructure errors. A deployment finishing after cutoff is recorded but cannot become the selected policy.

## Submission and private evaluation

`SIGUSR1`, sent by the trusted collect hook after the agent stops, requests finalization. The service waits for any running deployment under its lock, then selects the sealed eligible round or the latest completed-before-cutoff round. Without one, it writes a zero-score no-submission verdict. The service also finalizes on its own deadline. The final file is written atomically and repeated collection is idempotent. A partial failed final evaluation is infrastructure failure, never silently replaced by a fresh task or a favorable replay.

For a selected policy, the sidecar verifies its frozen hash and the private oracle bank, then evaluates every held-out case in two fresh processes. Exact private records must match. The collector waits for the trusted final manifest; Harbor copies `/data/` from `sim` into the separate verifier. The verifier checks instance identity, manifest/grade hashes, versions, replay flags, case coverage and finite score bounds. It never reads agent-written rewards or evaluator records from `/app/output`.

| Artifact in sim `/data/` | Purpose |
|---|---|
| `final.json` | Atomic finalization status, frozen instance identity and grade digest. |
| `session/state.json`, `audit.jsonl` | Budget, selected submission, timestamps, diagnoses and accepted/rejected API calls. |
| `session/round-N/policy.json`, `agent-feedback.json` | Exact policy and feedback delivered to the agent, including image payloads. |
| `session/round-N/case-K/` | Private trajectory, sensor feedback, individual camera frames and full video. |
| `session/oracle/` | Frozen timing references, optimizer candidate history, policies and independent verification replays. |
| `session/held-out/`, `grade.json` | Private held-out trajectories/videos, two replays per case and final score details. |

These artifacts are available to the operator after the run, not mounted into the agent. Native agent transcripts retain its visible tool calls and explanations; the task records supplied diagnoses, not private model chain-of-thought. An HTTP response record shows what was supplied, not whether a vision model actually inspected every frame.

`reward.txt` is 1 iff all six cases succeed safely with verified replay, otherwise 0. `reward.json` contains numeric fields only: `success`, `deterministic`, `infra_error`, `progress`, `final_reward`, `success_rate`, `episodes`. `final_reward` is the mean per-case 0–100 score; `progress = final_reward / 100`. Invalid trusted evidence is `infra_error=1`; no submitted candidate is `infra_error=0`, score zero.

See [the benchmark specification](benchmarks/quadrotor-landing.md) for physics, observation noise, randomization, scoring and paper-calibration limitations.
