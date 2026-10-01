> **Historical design note.** Superseded by [PROTOCOL.md](PROTOCOL.md) (v1.0) and [LIMITED_MODE_PROTOCOL.md](LIMITED_MODE_PROTOCOL.md) (`eai-standard/2.1`); kept for the record. Limited mode is now called standard mode.

# Two evaluation modes: unlimited vs limited ("robot as a service")

Wire protocol: `LIMITED_MODE_PROTOCOL.md` (rcb-limited/2.1: `submit` action chunks + `observe`, binary RCB1 responses, 82-column proprioception, crash resume; 1.0's `/step` is retired). Status 2026-09-22: design + verified Harbor plumbing (PoC under `docs/limited_mode/gym-sidecar-poc/`, oracle scores 1
in both `public` and `no-network` agent policies). 47 RoboTwin tasks, 21 DexToolBench and 4 MuJoCo Playground tasks have limited twins (`tasks/*-limited`).

## Mode 1 — unlimited (what every current task is)
Agent and simulator live in the same container. The agent may reset without limit, read privileged state
(object poses, `check_success`), call planning primitives, and self-verify by replay. Deliverable: a trajectory.
Cheap and simple; measures "can the agent program the robot given full sim access".

## Mode 2 — limited (real-robot-like)
The agent never touches the simulator. A **sim service** runs in its own container; the agent only gets a
**client** with a gym-like API: `reset()` (budgeted), `step(action) -> observation`, observations = RGB(-D) +
proprioception only. The service enforces the budget, logs every call, and holds the success predicate. Grading
happens from the service's own log, in a verifier sandbox the agent never ran in.

### Harbor already provides every piece (verified 2026-09-22, Harbor 0.23)
| need | Harbor feature | where |
|---|---|---|
| a container the agent cannot open | compose **sidecar service** in `environment/docker-compose.yaml` (`main` = agent, any other service = sidecar; separate filesystem/process namespace, reachable only over the network) | docs: core-concepts/tasks/multi-container |
| the agent cannot fetch solutions or talk to anything else | `[agent] network_mode = "no-network"` or `"allowlist"` (model API only). Under egress control Harbor puts main + sidecars in one network namespace: the sidecar is `localhost:<port>`; with `public` it is `http://<service>:<port>` | docs: network-policies |
| tamper-proof evidence | `artifacts = [{ source = "/data/episode.jsonl", service = "sim" }]` collected **after main is stopped**; `[[verifier.collect]]` hook runs a snapshot command inside the sidecar first | docs: artifacts, jobs/artifact-collection |
| verifier the agent cannot have modified | `[verifier] environment_mode = "separate"` + `tests/Dockerfile` (dedicated verifier image, artifacts uploaded to their original paths) | docs: separate-verifier |

PoC findings (`gym-sidecar-poc`, oracle probes recorded in `artifacts/app/output/probe.txt` of the jobs):
- from `main`, `/data` and `/srv` of the sidecar do not exist, `ps` shows only main's own process;
- an undocumented endpoint returns 501/404; in the PoC the third `reset()` is refused with HTTP 429 (the real tasks have no reset at all: 404);
- the separate verifier receives `/data/episode.jsonl` + `/data/final.json` (written by the collect hook) and scores
  from them; the agent's container is already gone;
- gotcha: do **not** put `expose:`/`ports:` on the sidecar — it conflicts with the shared network namespace that
  egress control uses (`conflicting options: port exposing and the container type network mode`). Just listen on
  0.0.0.0 and let the client try the service name, then `localhost`;
- gotcha: with plain `environment_mode = "separate"`, this Harbor version wants `tests/Dockerfile` (a verifier image
  that already contains `/tests/test.sh`).

### Proposed limited-mode task shape for RoboTwin
```
tasks/robotwin_2_0_<task>-limited/
  environment/Dockerfile          # agent image: python + client.py only (NO simulator, NO RoboTwin code)
  environment/docker-compose.yaml # sim: FROM rcb-robotwin image + server.py; GPU reservation on *sim*, not main
  environment/client.py           # reset()/step()/observe(): JSON over HTTP, images as PNG bytes (base64) or msgpack
  tests/Dockerfile + test.sh      # separate verifier: reads /data/episode.jsonl, success = service's own check_success
  task.toml                       # [agent] network_mode="allowlist" (model API); artifacts from service "sim";
                                  # [[verifier.collect]] dumps final state; [verifier] environment_mode="separate"
```
Server contract (draft): `POST /reset` (budget N, returns obs), `POST /step {action}` (14-d joint targets or
end-effector pose + gripper; server runs K physics steps; returns obs), `GET /spec` (action space, camera list,
budget left). Observation = {head/front/wrist RGB (+depth), joint positions, gripper state, step index}. Never:
object poses, `check_success`, scene files. Success is decided **inside the service** at every step and written to
the log; the "deliverable" is the episode itself, so there is nothing for the agent to hand in (no replay needed).
The reset budget and step budget become the interaction cost that PROTOCOL §5 asks to report.

Open design choices: (1) action space granularity (joint targets vs EE pose with a server-side IK/planner);
(2) whether to allow *offline* planning helpers on the agent side (e.g. a URDF for IK) — they do not leak scene
state; (3) sim step latency over HTTP (fine for a coding agent, ~ms per call); (4) per-instance seeds stay hidden
inside the service.
