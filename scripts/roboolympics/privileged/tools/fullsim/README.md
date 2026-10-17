# The privileged setting for single-player sports (generic)

The First Exam **privileged** twin of an exported `-standard-realtime` match (PROTOCOL §3, H.7): in development the
agent has the sport's full simulator (`Session`: any state read or changed, the whole match reset); it submits a
Python program that plays a fresh, unmodified match in a network-less verifier on the original realtime service and
the twin's clock (S), seeing the full state (`truth`) instead of the cameras; two fresh replays confirm the verdict.
Table tennis has its own copy in `tools/tt_fullsim` (PR #154); every other sport uses this one.

## A sport = one adapter

`tools/fullsim/sports/<sport>.py` (never under `sports/<sport>/`: that directory is copied byte for byte into the twin's
simulator). Required and optional attributes: `tools/fullsim/adapter.py`; examples: `sports/badminton.py`,
`sports/tabletennis.py`. The oracle (a full-state reference program) goes to `tools/fullsim/oracles/<sport>.py`.

| attribute | meaning |
|---|---|
| `SPORT`, `FORMAT`, `SEATS`, `ACTION_LEVEL`, `LEVELS` | the match (`sports/<SPORT>/plugin.py`) |
| `SOURCE_TASK` | our generated task whose `environment/sim` is the frozen tree (native export) |
| `FAMILY`, `INSTANCES` | upstream names `roboolympics-{FAMILY}-{id}-privileged` / `-standard-realtime`; `{id: {level, seed}}` = the twin's `RO_LEVEL` / `RO_SEED` |
| `SLOWDOWN`, `CUTOFF_S`, `READY_TIMEOUT_S`, `REPLAY_TIMEOUT_S` | the twin's S, `[agent] timeout_sec`, `READY_TIMEOUT_S`, `RO_REPLAY_TIMEOUT_S` |
| `MATCH_WALL_S`, `VERIFIER_TIMEOUT_S` | the formal match's wall-clock cutoff (also the program's CPU limit); the verifier's timeout |
| `EVERY`, `MAX_COMMANDS` | control steps between two views; commands per view (a list; each one `service.act`) |
| `IMAGE` | the twin's sim image, pinned by digest |
| `truth(match)` | the current physical state only, JSON-able (no seed, plan or future event) |
| `TRUTH_DOC`, `NOTES_DOC`, `DESCRIPTION`, `RESOURCES` | text for README / instruction; resource minimums |
| `ORACLE`, `ORACLE_FILES` | the reference program; files copied next to it into `solution/` |
| `PUBLIC_DROP_FILES` | files of `sports/<sport>/` left out of the agent's copies (default: `builtin_players.py`) |

## Commands

```bash
python -m unittest tools.fullsim.tests.test_fullsim                       # every adapter builds, steps, resets
python -m tools.fullsim.calibrate --sport S --program tools/fullsim/oracles/S.py --levels 1-4 --seeds 1-40 \
    --jobs 8 [--delay D] --out /tmp/S.json                                # step timing, paired seeds
python -m tools.fullsim.formal --sport S --policy DIR --level L --seed N --out NEWDIR --unsafe-local   # the S-clock match
python -m tools.fullsim.export --sport S --out /tmp/tasks                  # native tasks
python -m tools.fullsim.export --sport S --hub /path/to/robot_coding_bench # install the generator upstream + render
cd /path/to/robot_coding_bench && python3 scripts/roboolympics/privileged/generate.py --check
bash tools/fullsim/harbor/accept.sh TASKS_DIR NEWDIR TASK...               # Docker: build, boundary, Harbor nop + oracle
```

Upstream the generator renders from each twin's own `environment/sim` and `--check` verifies the trusted copy byte for
byte (H.7). Every adapter is exported upstream unless it sets `EXPORT = False`.
