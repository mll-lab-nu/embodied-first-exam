# `eai-standard-realtime/1.0`: real-time extension of standard mode

Status: **proposal** (2026-10-02), to be accepted through a protocol-change PR (`docs/PROTOCOL.md`, D1).
Reference implementation: table tennis, `tasks/tabletennis-match-wallclock-program-standard` (single player) and
`tasks/tabletennis-duel-wallclock-program-standard` (two players).

## Why a separate protocol

`eai-standard/2.x` serves tasks whose world advances on the agent's actions. Real-time sports need a world that runs
on its own clock while the agent thinks, with points, reviews and an opponent. The tasks keep every standard-mode
property:
- the simulator runs in a sidecar the agent cannot open;
- the agent only acts and observes (camera images plus its own robot);
- there is no reset;
- a separate verifier with no network replays the record.

They differ in the time model and the wire format below. They are named `-standard` with `mode = "standard"` and
`protocol = "eai-standard-realtime/1.0"`, so they cannot be mistaken for `eai-standard/2.x`.

## What differs from `eai-standard/2.x`

| | `eai-standard-realtime/1.0` |
| --- | --- |
| Time | The world advances at 1/S of real speed (S = `timing.slowdown` in `/spec`; S = 1 is real speed), in 10 ms control steps. It freezes only before `start` and after each point until `ready`. All agent latency (model, API, tools, its programs) counts. |
| Endpoints | Single player: `http://sim:8000`. `GET /spec`, `GET /status`, `POST /start`, `POST /observe`, `POST /act`, `POST /wait`, `POST /ready`. Two players: the same calls under `http://sim:8000/<seat>/` (`observe` is a GET). A thin `game` CLI wraps them. |
| Actions | A command takes effect at the next control step, replaces the one under way, and is refused while the world is frozen. **One action in flight per seat** (HTTP 429). |
| Who acts | Program play: the agent's own program may act without a new model response per action. The service requires a live, metered model session (`RCB_ACT_RULE=program`). |
| Model access | Only through the sidecar's metering proxy (`think_proxy.py`), which records every model call. Azure deployments may fail over between replicas (`AZURE_DEPLOYMENTS`); switches are recorded and are not failures. |
| Isolation | The agent runs in a Harbor seat whose container shares only an internal network with `sim`. Internet is attached only while the agent is installed (`setup_networks`). The sidecar keeps the internet for the model APIs. |
| Configuration | Chosen at run time, not by directory. Single player: `RCB_LEVEL`, `RCB_SLOWDOWN`, `RCB_SEED`. Duel: `RCB_SLOWDOWN`, `DUEL_SEED`, `FIRST_RECEIVER`. |
| Verifier | Reports `success`, `valid_trial` and `technical_failure` (simulator, model-API, metering or replay failure; not a loss; model-API errors as in [Validity](#validity-model-api-errors)), the configuration (`level`, `seed`, `slowdown`) and `official_config`. The replay must be deterministic. |
| Twin | None: real-time sports have no privileged counterpart. |

## Validity: model-API errors

Both protocols (`eai-standard-realtime/1.0` and `eai-standard-turn/1.0`, single player and duel) use one rule for the
errors of the model API (decided 2026-10-03; code: `scripts/olympiad/api_errors.py`, copied into every task's
`environment/sim/`). The metering proxy logs every model call of a seat (`think_calls.jsonl`, `think_calls_<seat>.jsonl`
in a duel). A model-API error is a model call that did not complete successfully (an HTTP error such as 429 or 5xx, a
stream error, a broken connection) or a 429 retried inside the proxy. Each error of a seat is

- **transient** when a later model call of the same seat completed successfully: the harness retried and got past it.
  It does not invalidate the match; it is counted and reported (`transient_api_errors`, `A_`/`B_transient_api_errors`
  in a duel);
- **unrecovered** when no model call of that seat completed successfully after it, e.g. the agent stopped or its
  session ended because of the API, including an account rate limit (429) it could not get past
  (`unrecovered_api_errors`).

The model API fails the trial (`proxy_error`, per seat in a duel; a technical failure, not a loss) only if a seat had
an unrecovered error or more than `MAX_TRANSIENT_API_ERRORS = 5` transient errors in the match. Azure deployment
switches (`azure_failovers`) are not errors. The service applies the rule when it writes `final.json`; the verifier
requires `proxy_error` to be false. Trials graded before this rule can be re-graded with
`scripts/olympiad/regrade_transient.py` (it re-runs the task's own grader on a patched copy of `final.json`).

## Requested changes to the protocol and CI

1. Add `eai-standard-realtime/1.0` to the accepted standard-mode protocols (`PROTOCOLS` in
   `ci_checks/check-protocol-v1.py`), and to `docs/PROTOCOL.md` D1 as a separate wire protocol for real-time tasks.
2. Allow a standard task without a privileged twin when its protocol is `eai-standard-realtime/*` (§2.2).
3. Images follow §2.4: the `sim` service runs the benchmark's base image `eai-olympiad` (`images/olympiad/`), with the
   task's code mounted at `/srv`; agent containers and verifiers build from the standard client image and pins
   (`scripts/eai_standard/`).
4. Two-player tasks need Harbor's multi-seat support (`[[seats]]`, `--seat`, per-seat `setup_networks`), which the
   single-player tasks also use for their offline seat. Pinned until upstream Harbor has it: `CHIGUI0/harbor` branch
   `rcb-multiseat` (v0.23.0 + commit `3fc74678`); proposed to Harbor separately.
5. Model access through the sidecar's metering proxy and the thin agent adapters (`harbor_agents/`: Harbor's own Claude
   Code and Codex, pointed at the proxy, with the credential kept in the sidecar) differ from D11 (native agents, a
   recording-only gateway); to be agreed.

## Prompt

The agent's instruction follows one structure for every real-time sport, built from
`scripts/olympiad/program_prompt.py` with the sport's own sections (table tennis: `scripts/olympiad/tt_prompt.py`).
The sections are Task, Time, Write a program, Interface, Rules, Geometry and physics.

## Turn-based sports: `eai-standard-turn/1.0`

Precision sports (darts, archery, bowling, golf putting, basketball shooting, billiards, curling) wait for the player,
so they need no real-time clock. They share everything above (sidecar, program play with a live metered model session,
one action in flight, metering proxy, offline seat, run-time configuration, verifier fields, no twin) except:

| | `eai-standard-turn/1.0` |
| --- | --- |
| Time | Nothing moves between shots. Each player has a chess clock (`clock.total_s` in `/spec`) that runs only on its own turn, reviews included; a player whose clock runs out loses. No slowdown. |
| Turns | After each of the player's shots the service waits for `ready` (the review) before the game goes on. In a duel the players alternate as the sport's rules say; the service refuses an action out of turn (HTTP 409). |
| Configuration | Single player: `RCB_LEVEL` (when the sport has opponent levels), `RCB_SEED`. Duel: `DUEL_SEED`, `FIRST_PLAYER`. |
| Prompt | `scripts/olympiad/turn_prompt.py`: the same six sections as the real-time prompt, with a Time section for the waiting world. |
