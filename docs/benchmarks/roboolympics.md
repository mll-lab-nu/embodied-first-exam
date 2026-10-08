# RoboOlympics (standard-realtime)

Three single-player real-time sports from [RoboOlympics](https://github.com/CHIGUI0/roboolympics): the world runs on its
own clock at 1/S of real speed (S = 10) while the agent thinks, against a scripted opponent. Standard-realtime only (no
privileged twin), served by RoboOlympics' own realtime protocol `eai-standard-realtime/1.0` (the #41 time model; a
proposed per-benchmark exception, PROTOCOL §4b, §7 Open 6). `tasks/roboolympics-<sport>-<format>-i00-standard-realtime`,
generated in the RoboOlympics repository by `tools/generate.py --upstream <this checkout>/tasks` (table:
`tools/upstream.toml`; `tools/generate.py check --upstream <this checkout>/tasks` compares).

## Tasks
| task | sport, rules | robot | instance | oracle |
|---|---|---|---|---|
| `roboolympics-tabletennis-match-i00-standard-realtime` | table tennis, ITTF Laws (deviations in the README): one game to 5 points; the opponent serves recorded real serves, you receive | Franka Panda with a paddle (high-level act: the blade's state at contact; the service plans the swing) | seed 101, opponent level 1 of 4, S = 10 | full |
| `roboolympics-badminton-match-i00-standard-realtime` | singles badminton, BWF Laws: first to 5 points, rally scoring, the players serve | Franka Panda with a racket on an x-y sliding base | seed 101, opponent level 1 of 2, S = 10 | full |
| `roboolympics-airhockey-match-i00-standard-realtime` | air hockey, USAA rules: one game to 7 goals, 0.35 m goal mouth | KUKA iiwa 14 with a mallet (mallet target in your half; Cartesian path and torque control in the sim) | seed 101, opponent level 1 of 4, S = 10 | full |

Rendering: MuJoCo with OSMesa (software, CPU only). The players' camera images draw the robots with their Menagerie
visual meshes decimated to about 25k triangles per robot (RoboOlympics renderer rule 6, `players = "25k"`; same
kinematics as the physics model, checked).

The agent sees only camera images (and its own robot's state and the referee's calls) through the `game` CLI / HTTP at
`$SIM_URL` (`http://localhost:8000`), may write a player program that plays in a loop and fix it during the match, and
must stay until the match ends (an early exit or no `start` is a valid loss). The world freezes after every unit (a
point, a goal) until the agent sends its review (`game ready WHY PLAN`).

## Run
```bash
MODES=standard-realtime scripts/run_agent_batch.sh <batch> roboolympics-tabletennis-match-i00 \
  roboolympics-badminton-match-i00 roboolympics-airhockey-match-i00
```
Requirements: Docker, CPU only. Per trial the sim takes up to 6 CPUs and 8 GB, the agent container 2 CPUs and 4 GB.
The image `ghcr.io/mll-lab-nu/eai-olympiad:0.1.0` is public (about 0.6 GB; or `images/olympiad/`). Keep the tasks'
egress allowlist: the agent reaches the sim through Harbor's egress-control namespace (with public egress `main` could
not reach it). Run real-time tasks where the host is not overloaded: the simulator's lag behind its clock is reported
in the reward fields.

Agent time budget 7200 s. Wall time of the oracle's match at S = 10 (2026-10-08): table tennis about 4 min, badminton
about 20 min, air hockey 20 min (the time cap); the start window before `game start` is 30 min.

## Verification
The sim service records the match (`episode.jsonl`), a fresh process replays it (state hash, scores, commands), and
`tests/grade.py` (separate sandbox, no network) writes `success` = a valid match the agent won, `valid_trial`,
`deterministic`, the score and the sport's fields. A simulator error voids the trial (`technical_failure = 1`,
`valid_trial = 0`), never the agent's loss. `nop`: no-show, a valid loss, reward 0. No model metering in the sim (player
mode `unmetered`): usage comes from Harbor and the optional usage gateway.

## Differences from the standard-realtime protocol (PROTOCOL §4b)
Proposed as a per-benchmark exception; the owner decides which stay (PROTOCOL §7 Open 6).

| | PROTOCOL §4b | RoboOlympics | why |
|---|---|---|---|
| slowdown S | 1 by default | 10 (frozen in the task) | a model call takes seconds; at S = 1 a rally is over before one response, so play is reflexes, not reasoning; 10 is an official RoboOlympics slowdown of all three sports |
| reset budget | 50 by default | 0 (no reset) | a match is the episode; a reset would replay points already lost |
| privileged twin | `<base>-privileged` | none | the sports measure play from camera images against an opponent; no trajectory deliverable |
| interface | `/spec`, `/status`, `/observe`, `/submit` (RCB1), `rcb_client.py` | the `game` CLI / HTTP: `/spec`, `/status`, `/start`, `/observe`, `/act`, `/wait`, `/ready` | RoboOlympics' shared core serves 20 sports, turn-based and real-time, with one interface |
| images | RCB1 frames | PNG camera tiles in JSON (`observation.tiles`) | the same core and graders as the RoboOlympics matches |
| clock | never stops once started | freezes after every unit (a point, a goal) for the agent's review | the review between units is RoboOlympics' core feature: the agent states why it won or lost the point and its plan |
| crash | journal resume, `infra_error = 1` past the resumes | no resume; the trial is void (`technical_failure = 1`) | matches are short at S = 10 (4-20 min); a void trial is re-run |
| evidence | `ticks.f64`, `calls.jsonl`, `submitted.f64`, `trajectory.npz`, ... | `final.json`, `episode.jsonl`, `replay_check.json`, `replay.mp4`, `video.json`, `broadcast.jsonl` | the RoboOlympics core's own record and fresh-process replay |

## Egress: `cap_drop: [NET_RAW]`
Both services drop NET_RAW. Under Harbor's egress control, a process with CAP_NET_RAW (Docker grants it by default; on
Linux >= 5.17 it is enough to set `SO_MARK`) can mark its socket with the egress proxy's own mark and leave the
allowlist. Measured in a running trial with `cap_drop`: setting `SO_MARK` -> `EPERM`; the allowed model API -> reached;
GitHub and PyPI -> refused by the proxy; the sim at `localhost:8000` -> reached.

## Differences from the RoboOlympics tasks
Same simulator, rules, prompts and grader as the RoboOlympics tasks `tabletennis-match-wallclock-program-standard`,
`badminton-match-wallclock-program-standard` and `airhockey-match-wallclock-program-standard`, with: a frozen instance
(seed 101, level 1, S = 10; set at run time there); Harbor's native agents instead of RoboOlympics' seats and metering
proxy; the agent in `main` instead of a `player` seat container; egress = the model APIs.
