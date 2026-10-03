# Embodied Agent Olympiad

Real-time sports for coding agents: a simulated robot plays a match while the world keeps running, slowed by a factor
S. The agent sees only camera images and may write its own player program, fix it during play and review after every
point (program play, decided 2026-10-02). First sport: table tennis, single player against a scripted opponent and two
players against each other.

| | |
|---|---|
| tasks | `tasks/tabletennis-match-wallclock-program-standard` (single player) and `tasks/tabletennis-duel-wallclock-program-standard` (two players); one parameterized task each, the configuration chosen at run time |
| mode | standard, protocol `eai-standard-realtime/1.0` (`docs/EAI_STANDARD_REALTIME_1_0.md`); no privileged twin |
| metadata | `simulator = "mujoco"`, `robot = "franka-panda"`, `family = "tabletennis_match"` / `"tabletennis_duel"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` (`images/olympiad/`): MuJoCo 3.3.7, OSMesa, CPU only; the task's code is mounted at `/srv` |
| agent containers, verifier | the standard client image and pins (`scripts/eai_standard/`), plus OpenCV (headless) for the players |
| generator | `scripts/olympiad/generate.py` (`check` compares `tasks/` with a fresh render) |
| run | `scripts/olympiad/run_single.sh`, `scripts/olympiad/run_duel.sh` (`HARBOR=<path to harbor>` if it is not on `PATH`) |
| Harbor | v0.23.0 with multi-seat support (seats, per-seat `setup_networks`): `uv tool install git+https://github.com/CHIGUI0/harbor@3fc74678123a2eb1845938b099e9d7856f2c6f6d` (branch `rcb-multiseat`; proposed to upstream Harbor) |

## Sports

Each sport has a single-player task and a two-player duel, generated from `scripts/olympiad/<sport>/spec.py`.

| sport | protocol | single player | duel |
|---|---|---|---|
| table tennis | real time | `tabletennis-match-wallclock-program-standard` | `tabletennis-duel-wallclock-program-standard` |
| tennis | real time | `tennis-match-wallclock-program-standard` | `tennis-duel-wallclock-program-standard` |
| baseball | real time | `baseball-batting-wallclock-program-standard` | `baseball-duel-wallclock-program-standard` (pitcher against batter) |
| badminton | real time | `badminton-match-wallclock-program-standard` | `badminton-duel-wallclock-program-standard` |
| darts | turn based | `darts-501-program-standard` | `darts-duel-program-standard` |
| archery | turn based | `archery-program-standard` | `archery-duel-program-standard` |
| basketball | turn based | `basketball-shootout-program-standard` | `basketball-duel-program-standard` |
| bowling | turn based | `bowling-program-standard` | `bowling-duel-program-standard` |
| golf putting | turn based | `golf-putting-program-standard` | `golf-putting-duel-program-standard` |
| billiards (8-ball, WPA) | turn based | `billiards-eightball-program-standard` | `billiards-duel-program-standard` |
| curling | turn based | `curling-match-program-standard` | `curling-duel-program-standard` |

Real time: `eai-standard-realtime/1.0`, prompt `program_prompt.py`. Turn based: `eai-standard-turn/1.0` (a 60-minute
chess clock per player), prompt `turn_prompt.py`. Billiards' simulator runs in `eai-olympiad-billiards`
(`images/olympiad-billiards/`), every other sport in `eai-olympiad`.

## Task definition (table tennis)
- **World.** MuJoCo, Franka Panda with a table-tennis paddle; the opponent's serves are real serves recorded by
  Google DeepMind's robot table-tennis project. Ball flight with gravity, drag and spin (Magnus). Control steps of
  10 ms of game time; the world advances at 1/S of real speed and freezes only before `start` and after each point
  until `ready` (a short review: why the point ended, what to change).
- **Configuration (run time).** Single player: opponent level 1-4 (`RCB_LEVEL`), slowdown (`RCB_SLOWDOWN`) and seed
  (`RCB_SEED`). Official: three seeds per level (101/111/121, 202/212/222, 303/313/323, 404/414/424) and slowdowns
  1, 2, 5, 10, 20. Duel: slowdown 10 or 20, `DUEL_SEED`, `FIRST_RECEIVER`; play both seat orders.
- **Observations.** Two cameras (behind the robot and at the side), 4 frames 40 ms apart per observation, with
  frame times and calibration in `/spec`; the robot's own state; no ball coordinates.
- **Actions.** The paddle's state at contact (centre, face normal, velocity) T seconds after the command takes effect;
  the arm's stroke controller (IK, joint speed limits) executes it. One action in flight per seat.
- **Program play.** The agent's own program may act without a new model response per action; the model may watch,
  stop, fix and restart it at any time, also during a point. The sidecar's metering proxy requires a live model
  session and records every model call.
- **Isolation.** The agent runs in a Harbor seat (`player`, or `seat_a` / `seat_b`) that shares only an internal
  network with `sim`; internet only while its agent is installed. The sidecar keeps the internet for the model APIs.
- **Success.** Single player: win a valid match (first to 5; 40 of the agent's shots without a win is a loss). Duel:
  a valid match, winner `A_won` / `B_won`. Valid means a deterministic replay in a fresh process and no simulator,
  model-API or metering failure; technical failures are reported separately from losses. A model-API error the
  harness recovered from (a later model call of the same seat completed) is only counted (`transient_api_errors`);
  the model API fails a trial only with an unrecovered error or more than 5 transient ones per seat
  (`scripts/olympiad/api_errors.py`; docs/EAI_STANDARD_REALTIME_1_0.md, "Validity"). Older trials:
  `scripts/olympiad/regrade_transient.py`.

## Prompt
`instruction.md` follows one structure for every real-time sport (`scripts/olympiad/program_prompt.py`: Task, Time,
Write a program, Interface, Rules, Geometry and physics). A sport supplies only its own sections
(`scripts/olympiad/tt_prompt.py`). Principles: clear, simple, general.

## Checks
`python3 scripts/olympiad/generate.py check`; `python3 scripts/olympiad/test_program_play.py tasks/<task>` (the
program-play act rule and the Azure failover of the metering proxy, offline); an `oracle` and a `nop` run per task.
