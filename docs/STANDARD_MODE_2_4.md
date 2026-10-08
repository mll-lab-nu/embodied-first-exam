# eai-standard/2.4 — the operations capability

Status: accepted 2026-10-08 (owner), protocol-change issue #89. It was first served by RoboTangle's standard tasks; the
benchmark's own release called it "2.3", but that number had already gone to the realtime capability (#86). Reference
implementation: [`scripts/eai_standard/v2_4/`](../scripts/eai_standard/v2_4/), with `rcb_limited.py` and
`rcb_client.py`. `rcb1.py`, `run.sh`, the client image and the client pins are the 2.2 ones in `scripts/eai_standard/`.

## 1. Version

`eai-standard/2.4` = 2.3 + the **operations capability** below.
- Every earlier addition stays a MAY capability. That covers 2.2's depth, `frame_time_s`, extrinsics, `POST /kinematics`
  and the per-call wall bound, and 2.3's realtime capability ([`LIMITED_MODE_PROTOCOL.md`](LIMITED_MODE_PROTOCOL.md),
  "Standard-realtime mode"). So a 2.2 service that adds the operations capability is a 2.4 service.
- Standard-mode tasks may declare `protocol = "eai-standard/2.4"` (PROTOCOL §2.3). Standard-realtime tasks stay on 2.3
  (PROTOCOL §4b).
- Everything in PROTOCOL §4 holds unchanged: four endpoints (plus `/kinematics` and the one below), RCB1, no reset,
  crash recovery that resumes the same episode, and grading by a fresh replay.
- `/spec.protocol` is `eai-standard/2.4`.

Why: a native simulator call can run for minutes (IPC and PBD deformables). Under 2.2, a client whose HTTP read timed
out cannot tell whether the call ran, and a retry can execute the same actions twice. The capability makes every call
identifiable, bounded, and queryable after the fact.

## 2. Operation ids and request deadlines

| Item | Level |
|---|---|
| `/submit` and `/observe` accept `meta.operation_id` (string, `[A-Za-z0-9_-]{1,80}`) and `meta.request_deadline_unix_s` (finite number, Unix seconds); a malformed value is 400 | MUST |
| A request whose deadline has passed before execution starts gets **408**; no physics runs | MUST |
| An `operation_id` that the service has already admitted gets **409**, with `operation_id`, the operation record and a pointer to `/operations/<id>`; it is never executed again | MUST |
| The response `meta` echoes `operation_id` | MUST |
| A request without these fields is served as in 2.2 | MUST |
| The client sends a fresh id and a deadline (now + `max_call_wall_s`) on every call to a 2.4 service. It keeps the last id (`Robot.last_operation_id`), and its read timeout is at least the service budget + 120 s | SHOULD (reference client: always) |
| After a timeout the client queries the operation instead of re-sending the actions. A new id for the same actions is a new operation | SHOULD |

## 3. `GET /operations/<id>`

Returns the operation record as JSON: 200, or 404 for an unknown id, or 400 for a malformed id. Fields:
- `operation_id`;
- `status`: `admitted` | `completed` | `error` | `interrupted`;
- `rows_before`: control rows executed before the call;
- `committed_rows`: rows executed when the call ended;
- `stopped`: the call's stop reason, as in 2.2's `meta.stopped`.

After a crash recovery, an operation that was `admitted` becomes `interrupted`, with `execution_uncertain: true` and
`restored_committed_rows` (the rows the resumed episode replayed). `completed` means the call ended. Rows it executed are
in `committed_rows`. The service keeps no copy of the response video. The endpoint is read-only, never steps physics, and
is the only GET this capability adds.

## 4. Call watchdog

| Item | Level |
|---|---|
| A call's budget is `min(max_call_wall_s, request_deadline_unix_s − now)`. The service checks it, and a client disconnect, at control-step boundaries | MUST |
| A native step cannot be pre-empted safely, so the service also owns a hard watchdog. A call that has not finished 60 s past its budget ends the process. The restart then ends the episode as an infra error, `call_watchdog` (`infra_error = 1`), and does not replay into the call that hung | MUST |

## 5. Physics-tick ledger and durability

| Item | Level |
|---|---|
| The journal can record, for each executed row, the physics ticks it actually took (`journal.ticks.i64`, int64, one per row). A step that ends early inside its control period records fewer ticks, and `sim_time_s` and `frame_time_s` follow the actual physics clock | MAY (MUST for a service whose steps can end mid-period) |
| A resume replays each row with its recorded tick count. A missing or incomplete ledger ends the episode as an infra error, `resume_failed` | MUST if the ledger is kept |
| Journal rows, the tick ledger, checkpoints and operation records are fsynced, including their directory, before the call that counts them is reported complete | MUST |
| `dt` must be an integer multiple of the control period within float tolerance; otherwise 400 (2.1 rule, restated) | MUST |

## 6. Evidence

As in 2.2 (`/data/episode.jsonl`, `trajectory.npz`, `final.json`, `calls/`), plus:
- `/data/operations/<id>.json`;
- `journal.ticks.i64`, when kept;
- `call-watchdog.json`, while a call is running.

The verifier still grades `final.json` only (PROTOCOL §4.8).

## 7. Compatibility

- 2.x clients connect to a 2.4 service unchanged. They send no operation ids and get 2.2 behaviour.
- The 2.4 client sends ids only when `/spec.protocol` is 2.4, so it also works against 2.1–2.3 services.
- A benchmark adopts 2.4 by copying `scripts/eai_standard/v2_4/` unchanged; `ci_checks/check-tooling-identity.sh`
  checks the copies.
