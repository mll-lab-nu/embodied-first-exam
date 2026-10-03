# Embodied Agent Olympiad: adding a sport

How to bring a real-time sport (tennis, baseball batting, badminton, ...) into the Olympiad in the same form as table
tennis. Read first: `docs/benchmarks/olympiad.md`, `docs/EAI_STANDARD_REALTIME_1_0.md`, `docs/PROTOCOL.md`, and the
table tennis implementation listed in section 2. Table tennis is the reference: when this page and the table tennis
code disagree, the code wins and the page should be fixed.

## 1. What a sport delivers

Two **parameterized** tasks, generated (never hand-edited):

| task | players | run-time parameters |
|---|---|---|
| `tasks/<sport>-<family>-wallclock-program-standard` | the agent against the sport's scripted opponent | `RCB_LEVEL`, `RCB_SLOWDOWN`, `RCB_SEED` |
| `tasks/<sport>-duel-wallclock-program-standard` | two agents against each other in one world | `RCB_SLOWDOWN`, `DUEL_SEED`, `FIRST_RECEIVER` (or the sport's equivalent of who starts) |

`<family>` is `match` for tennis and badminton and `batting` for baseball. There is one directory per task: level,
slowdown and seed are chosen at run time, never one directory per configuration.

### Rules of the mode: program play (team decision of 2026-10-02; do not change)

- **Time.** The world runs in real time slowed by S (S = 1 is real speed). All real time counts, including model
  thinking, API latency and tool calls. The world freezes only before `game start` and during the review after each
  point (`game ready "WHY" "PLAN"`). A single-player review has no time limit. A duel review has a limit (`REVIEW_S`);
  after that the player forfeits.
- **Program.** The agent may write its own player program. The program observes and calls `game act` on its own, with
  no new model response per act. The model stays in the loop: it may watch, stop, fix and restart the program at any
  time, also during a point.
- **Allowed inputs.** Only the public camera images and the documented geometry and physics. Simulator internals,
  hidden coordinates and the reference solution are off limits.
- **One act in flight per seat.** A second act while one is pending gets HTTP 429 `busy`; these are counted as
  `refused_busy` in final.json.
- **Model calls.** Every model call goes through the sidecar's metering proxy (`think_proxy.py`). The act rule
  `RCB_ACT_RULE=program` (`think_clock.py`) allows an act only while a live, metered model session exists.
- **Network.** Internet is available only while the agent is installed. During play the agent's container reaches
  only `sim`.

### Official configurations

- **Single player.** Slowdowns `OFFICIAL_SLOWDOWNS = [1, 2, 5, 10, 20]` (`scripts/olympiad/common.py`). The old 3
  and 30 are dropped. Seeds: three per level, taken from the existing tasks. Read `MATCH_SEED` in each old task's
  compose, e.g. tennis L1 101/111/121, baseball L1 301/311/321, badminton L1 101, L2 202/212/222. When the old tasks
  have fewer than three seeds for a level, add seeds in the same pattern and check each one with the oracle.
- **Duel.** Slowdowns `DUEL_SLOWDOWNS = [10, 20]`.
- **Grader.** The grader writes `official_config` = 1 iff the run's parameters are an official combination. It also
  writes `level`, `seed`, `slowdown`, `success`, `valid_trial` and `technical_failure`. Duel graders write
  `A_points`/`B_points` (or the sport's score), `A_won`/`B_won` and `ready_forfeit`.

## 2. Where things are

| what | where |
|---|---|
| generator (finds every sport) | `scripts/olympiad/generate.py`: loads `scripts/olympiad/*/spec.py`, each defining `TASKS = {name: spec}`; `check` compares `tasks/` with a fresh render |
| settings every sport shares | `scripts/olympiad/common.py`: `IMAGE`, `PINS`, `OFFICIAL_SLOWDOWNS`, `DUEL_SLOWDOWNS`, `START_S`, `REVIEW_S` |
| table tennis spec | `scripts/olympiad/tabletennis/spec.py`. A spec has `source` (task sources under scripts/olympiad/), `shared` (simulator code copied into `environment/sim/`), `pins_to` (where client-requirements.txt goes), optional `extra_scene`, `prompt` (a function returning instruction.md) and `readme` (arguments of `realtime_standard.readme`) |
| table tennis task sources | `scripts/olympiad/tabletennis/match/`, `scripts/olympiad/tabletennis/duel/` (task.toml, environment/, tests/, solution/); the shared sim code is in `scripts/olympiad/shared/tabletennis/sim/` |
| prompt | `scripts/olympiad/program_prompt.py`: the general structure (Task, Time, Write a program, Interface, Rules, Geometry and physics). Every sport uses it unchanged, wording included. The sport writes only its own sections, in `scripts/olympiad/<sport>/<sport>_prompt.py` (table tennis: `tabletennis/tt_prompt.py`). |
| README | `scripts/olympiad/realtime_standard.py` `readme(...)` (the PROTOCOL v1.0 layout); `normalize()` from `scripts/task_conventions.py` runs last |
| simulator image | `images/olympiad/` (`eai-olympiad`): MuJoCo 3.3.7, numpy 2.2.6, imageio, PyOpenGL, pillow, OSMesa. Tennis, baseball and badminton have the same simulator dependencies, so they use this image unchanged; the task code is mounted with `./sim:/srv:ro` |
| agent and verifier images | the standard client image and pins (`scripts/eai_standard/client-requirements.txt`) plus `opencv-python-headless==5.0.0.93`; copy the table tennis `environment/Dockerfile`, `environment/seat/Dockerfile` and `tests/Dockerfile` |
| run | `scripts/olympiad/run_single.sh --task <name> --agent oracle\|nop\|opus\|... --level L --slowdown S --seed N`; `scripts/olympiad/run_duel.sh --task <name> --a oracle --b oracle --slowdown S --seed N --first A\|B`. Set `HARBOR=<path to the multi-seat Harbor>` if it is not on `PATH` |
| offline check | `python3 scripts/olympiad/test_program_play.py tasks/<task>`: the act rule and the Azure failover; must print `ALL OK` |
| starting points (the earlier per-response sports pilot, outside this repository) | `tasks/tennis-match-l{1..4}-wallclock-x10-interactive`, `tasks/baseball-batting-l{1..4}-wallclock-x10-interactive`, `tasks/badminton-match[-l2]-wallclock-x10-interactive`. Read them; do not modify them. |
| table tennis program-play changes as functions (dev/chi) | `scripts/interactive/mk_tt_program_mode.py`: `patch_clock`, `patch_server`, `patch_proxy`, `patch_compose`, `patch_toml`. Also `mk_tt_program_param.py` (parameterization, `GRADE_OFFICIAL`) and `mk_tt_program_duel.py` (duel) |
| table tennis duel before program play (dev/chi) | `scripts/interactive/duel2/`: two-robot scene (`mk_scene2.py`), `server_duel.py`, `duel.py`, `duel_ref.py` |

## 3. Steps for one sport

1. **Sources.** Copy the old x10 task into `scripts/olympiad/<sport>/<family>/`. Put the simulator files that both of
   the sport's tasks use into `scripts/olympiad/shared/<sport>/sim/`.
   - Copy `think_clock.py` and `think_proxy.py` from table tennis's shared sim. They are byte-identical across sports
     and already contain the program act rule and the Azure failover. `api_errors.py` (the model-API validity rule) is
     copied into every task's sim by the generator; the server sets `proxy_error` from `seat_api_errors(usage_file,
     usage)["api_failure"]` and records `transient_api_errors` / `unrecovered_api_errors` (per seat in a duel).
   - Delete the per-task Dockerfile. The image is `eai-olympiad`.
2. **Server** (`server.py`, per sport). Port table tennis's `patch_server()` by hand:
   - Wrap the act handler with the one-act-in-flight check: 429 `busy`, count `refused_busy`, clear the flag in
     `finally`.
   - Select the spec's `decision_rule` text from `RCB_ACT_RULE`.
   - Set the spec's `protocol` to `eai-standard-realtime/1.0`.
   - Write `trajectory.npz` next to the match record and list it in the artifacts.
   - Read level, slowdown and seed from the environment.
3. **Compose** (copy the table tennis `match/environment/docker-compose.yaml` and change only what the sport needs):
   - `sim` uses `image: <IMAGE>` with `./sim:/srv:ro`.
   - `player` is the only Harbor seat. It has the internal network `play` to `sim`, and `egress` only during setup
     (`setup_networks`).
   - `main` and `player` share `agent_output:/app/output`. The seat must not be `main`: Harbor recurses.
   - Set `RCB_ACT_RULE: program`, `AZURE_DEPLOYMENTS`, and `RCB_LEVEL`/`RCB_SLOWDOWN`/`RCB_SEED` with defaults.
   - Do not use `[agent] network_mode = "allowlist"`. It puts `sim` into the restricted network.
4. **task.toml.**
   - `name = "robot-coding-bench/<dir>"`, `mode = "standard"`, `protocol = "eai-standard-realtime/1.0"`, no `tier`.
   - `oracle` and `oracle_evidence`.
   - `[verifier] environment_mode = "separate"`.
   - Agent timeout 7200 s.
   - `/app/output/` in the artifacts.
   - `tests/test.sh` first clears `/logs/verifier/*`.
5. **Grader.** Add `official_config` (copy `GRADE_OFFICIAL`; the official sets come from the sport's spec.py).
6. **Prompt.** Write `<sport>_prompt.py` with only the sport's sections, as in `tt_prompt.py`: task, observation,
   action, rules, geometry and physics, commands. Principles: clear, simple, general.
   - Write only what a player needs. Leave out history, implementation details and tactics advice.
   - Put no configuration number in the prompt. Level and slowdown come from `game spec`, and times are written in
     terms of S.
   - Do not edit `program_prompt.py`. If the sport needs something the structure cannot express, report it instead
     of changing the shared text.
7. **spec.py.** Register both tasks, then run `python3 scripts/olympiad/generate.py`. Running it twice must leave
   `git status` unchanged.
8. **Duel.** Build it from the sport's single-player world, following table tennis's duel:
   - two robots, one per side, in one scene;
   - `server_duel.py` with seats A and B, each with its own metering (`think_calls_A/B`) and route
     (`THINK_OPENAI_ROUTE_A/B`, see `launch.py`);
   - a neutral server or launcher, the start window `START_S`, and the review limit `REVIEW_S` with forfeit;
   - Harbor seats `seat_a` and `seat_b`;
   - a scripted reference player (`solution/`) usable on either side;
   - a replay-based grader.

   The prompt uses `program_prompt.duel(...)`.
   - **Tennis and badminton:** a mirrored court, like table tennis.
   - **Baseball:** the duel is pitcher against batter. Each plate appearance, one seat pitches and the other bats; the
     roles swap every half inning (or every N pitches), so each seat bats equally often.
     - The pitcher chooses the pitch: type, speed, location, and release within physical limits stated in the prompt.
     - The batter uses the existing batting actions.
     - Score: runs, or another per-plate-appearance score from the existing batting grader.
     - Choose the exact format and document it in the README.

## 4. Checks (all must pass before anything else)

1. `python3 -m py_compile` on every changed Python file.
2. `python3 scripts/olympiad/generate.py check` (Python >= 3.11), then
   `bash ci_checks/run_all.sh tasks/<task>` for each task. The only
   allowed failure is the repository-wide `dataset.toml` manifest check: the new tasks are added to the manifest
   later, when the branches are merged.
3. `python3 scripts/olympiad/test_program_play.py tasks/<task>`, which must print `ALL OK`. For the duel, run it with
   whatever sim layout the test supports; if it cannot handle the duel, say so in the report.
4. Harbor runs with `oracle` and `nop`. Every run must have `valid_trial=1` and a deterministic replay, and the
   reported `level`/`seed`/`slowdown` must equal what was passed in. An oracle loss is fine; the match only has to be
   valid. Cover at least:
   - single: the default configuration, a non-default level and slowdown, a non-default seed, and x1;
   - duel: oracle against oracle at x10 and x20, with both values of `FIRST_RECEIVER`.

## 5. Do not

- Run models (Opus, Fable, Astra, luna) or use any subscription or key. Only `oracle` and `nop` runs.
- Edit another sport's directories, `program_prompt.py`, `common.py`, `generate.py`, the table tennis files,
  `tasks/dataset.toml`, or anything on `dev/chi` (including the old task directories).
  - If a shared file must change, describe the change in the report instead.
- Push. Commit only on your own branch.
- Print or write keys or tokens.

## 6. Known traps

- `open(p, "w").write(f(open(p).read()))` empties the file before reading it. Read first, then write.
- Python code embedded in a generator gets escaping wrong easily. Run `py_compile` on the output.
- The world must not stall: a server step that takes longer than one control step at x1 shows up as a lag. Check
  the sim's timing log at x1.
- `pgrep -f` / `pkill -f` patterns can match your own shell. Kill processes by PID.
- `scripts/task_conventions.py` needs Python 3.11+ (`tomllib`). Use the Harbor venv's Python.
