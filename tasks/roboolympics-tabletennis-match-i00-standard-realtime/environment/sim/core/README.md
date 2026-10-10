# core/

The match core (docs/framework_zh.md §5): it hosts every match under one set of rules and never names a sport or a
harness. Version: `VERSION` in `__init__.py` (bump on every change; every sport's golden replay must still pass).

| File | Contract / job |
|---|---|
| `sport.py` | ② the sport interface: `MatchConfig` (seats, sides, format, modes, renderer), `Phase`, `Refused`, `MatchBase` (the optional hooks and their defaults), `ActionLayer` / `LowLayer` / `SchemaLayer`, `check_command`; request validation (core 0.2.11): `check_body` (every request), `check_action` + `parse_action` (every act: any exception while reading an action is the player's 400, never a technical failure) |
| `http.py`, `client.py`, `game.py` | ① the player protocol: the HTTP envelope (`/<seat>/<endpoint>`, limits), the client loop of built-in players, the generic `game` CLI |
| `realtime.py`, `turn.py`, `service.py` | flow: `eai-standard-realtime/1.0` (slowdown, freeze and review, act pipeline, delayed effects, entities) and `eai-standard-turn/1.0` (turns, chess clocks, reviews); what both share (seats and sides, observations, team channel, retirement, final.json) |
| `episode.py` | ③ the match record: `episode.jsonl` and the fresh-process replay (`python -m core.episode PLUGIN DIR`) |
| `outcome.py`, `grading.py` | judgement: the no-draw chain, N-side ranking, solo scoring; the verifier (validity, reward fields, no-code audit hookup) |
| `observe.py`, `channel.py`, `rng.py`, `spec.py` | the observation whitelist and camera tiles (through `renderers/`), the reply images of an action (`Match.reply_views`, core 0.2.8: snapshotted under the lock, drawn off it by the same camera worker, attached to the reply as `observation`), the team channel, random streams by name, sport.toml |
| `seats.py`, `metering/` | per-seat counters, locks and chess clocks; the metering hookup (`think_clock.py`, `api_errors.py`: byte-identical copies); player modes (`PLAYER_MODE_<seat>`): `model` (metered by the seat's proxy, required for validity), `oracle` (exempt), `unmetered` (core 0.2.13: the runner meters the model itself, e.g. a plain Harbor with native agents; no proxy, no meter required) |
| `spectator.py` | the broadcast log (`broadcast.jsonl`, the legacy writer copied as `spectator/broadcast_log.py`) and the replay video (`replay.mp4`, a fresh-process replay drawn by the spectator renderer); never read back |
| final.json compatibility | `service.py` `COMPAT`: the sport's fields are lifted to the top level (unless a core field has the name) and `score` is set, so the Season-1 readers work; the sport fields also stay under `sport_fields` |
| `workers.py`, `serve.py`, `launch.py` | worker processes (plan, render, camera), the service entry point, the launcher (one metering proxy per seat, none for an unmetered seat) |
| `local.py`, `testkit.py`, `tests/` | in-process matches of built-in players, the generic test suite of every sport, the core's own tests |
