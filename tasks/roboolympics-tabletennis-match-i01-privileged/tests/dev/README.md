# Full-simulator program task: table tennis L2, seed 22

The development source at `/opt/fullsim` is complete and CPU-only. Python 3.12,
MuJoCo 3.3.7 and its exact dependencies are installed by the task Dockerfile.
No Git checkout, GPU, renderer, host environment or external simulator service is
needed. Run these commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.tt_fullsim.session import Session; s=Session(level=2,seed=22); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

This prints the initial 0:0 score and reset step 0. `s.world` is the entire mutable
Match object: `R.s.m/d`, the opponent, referee and planner. `s.spec()` gives the
original high action interface and serving rules. `act(command)` uses the original
parse/lower/apply; `step(n)` advances explicit 0.01 game-second steps and stops at
a point review or game end; `ready()` leaves review; `reset()` creates the entire
same-seed match at 0:0. Private simulator edits and repeated resets are permitted
in development; they never get transferred to the final official world.

## Submit a persistent program

Create `/app/output/policy/program.py`:

```python
def make_policy(config):
    # config["spec"] includes cfg, frozen_commit, actions, serve, robot/frame rules.
    return Policy()


class Policy:
    def act(self, view):
        if view["state"]["phase"] == "unit_over":
            return {"type": "ready"}
        return None  # replace this idle behavior with your controller
```

Helpers/data must be regular files under `policy/` (512 files and 32 MiB total).
No symlinks, devices, FIFOs or sockets. Helpers are importable by filename. The
object persists throughout one whole match, receives fresh `state`, `truth`,
`scores` and `observation`, and returns a single original high action, `ready`, or
None. `state.phase` is `playing`, `unit_over` or `finished`; `service_phase` retains
the underlying core's lifecycle when useful. There is no formal reset command.
A private prediction world can be created with `Session`, but there is no writable
reference to the official world and no arbitrary/checkpoint restore API.

`truth` includes named ball_pos/ball_vel/ball_spin, q/qd/q_target and full qpos,
qvel, servo, opponent parameters and current leg. Use named fields rather than
assuming free-joint array offsets. Coordinates and units are in `spec.frame`:
metres, +y toward opponent, z=0 on table. Copying only qpos/qvel does not restore
servo, referee, planner or opponent history. `points`/`shots` are recent windows,
not whole-match totals. Sandbox `act()` returns planner diagnostics; no extra
formal response callback is part of this version's policy API.

## Serving and time units

`state.serve.phase` is `waiting` → `open` → `tossed` → `done`. This is separate
from match phase. On your serve, wait for `open` before a legal `toss`, then strike
the ball while it falls. It rests on the device for ten control steps (0.1 game
seconds) before projection. `serve.detail` distinguishes `toss resting` from
`toss rising/falling`; use `serve.toss.projected_at_step`. `spec.serve` includes
opens_after_point_s=0.8, toss_within_s=5.0 and legality details. `act.t` and `_s`
fields are game seconds; at S=10 multiply by ten for wall time. Sources are
`sports/tabletennis/plugin.py` and `sports/tabletennis/sim/serve.py`.

## Developer self-test of your saved program

```bash
python -m tools.tt_fullsim.formal --policy /app/output/policy --level 2 --seed 22 \
  --out /tmp/my-tt-self-test --unsafe-local
```

Use a new output directory each time. This starts a fresh world and the original
`core.realtime.RealtimeService` clock, runs your persistent program, and replays
its trusted journal twice in fresh processes. `--unsafe-local` is a developer
self-test, NOT the trusted final grading boundary; your development simulator may
have been modified. No `.git`/git binary or reference policy is required.

Formal evaluation happens later in Harbor's separate no-network verifier image:
root owns the private frozen simulator and logs; your code runs as nobody, has a
separate read-only public simulator copy and a writable scratch directory. Only
legal commands can influence the official world. The world continues at S=10
while your program computes; original point reviews freeze it. There is no extra
step mode in this release evaluator. Program load limit is 30s, each input/response
exchange 5s, review 300s; formal match execution cutoff is 1800s. The program has
2 GiB address space and 1800 CPU seconds (the match cutoff); development gets the task's overall
agent resource budget. No model/API calls are available in formal evaluation.

`reward.json` distinguishes valid deterministic losses from wins; success requires
a complete original-referee win and two fresh matching journal replays. Missing,
invalid, stuck or unfinished programs do not win. Files under `evaluation/match/`
record original final.json/episode/replay; diagnostics and decisions explain errors.
The submitted artifact is a program, not a trajectory. After the verdict the verifier replays the formal match's record
in a fresh process and draws `/logs/verifier/replay.mp4` with the sport's spectator camera (`core.spectator`), for
spectators only: nothing reads it back, and a failed render only leaves no video (`/logs/verifier/video.json` says
why). The verifier's timeout includes 1800 s for it.

Level 2 / seed 22 is the frozen instance of `roboolympics-tabletennis-match-i01-standard-realtime`, this task's
camera-only twin. Full simulator/truth access changes the
setting relative to camera-only standard; fixed-instance solving is not a claim
of generalization. Image build and Harbor oracle/nop validation must be recorded
on a Docker-enabled host; local functional checks cannot certify that boundary.
