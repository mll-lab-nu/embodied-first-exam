# Full-simulator program task: table tennis duel, seed 8, seat B the built-in RL opponent

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `embodied-olympics-match-tabletennis-duelrl-i01-realtime` (this task's
camera-only twin), its referee and its built-in RL opponent (seat B). No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.fullsim.duel import DuelSession; s=DuelSession("tabletennis", seed=8); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

`s.world` is the entire mutable Match object: the simulator, the built-in RL opponent (seat B) and the referee.
`s.spec()` gives the original action interface and the rules as the twin's `game spec` states them. `act(command)`
handles an action as the live service does (parse, plan, lower, apply); `step(n)` advances `n` control steps and
stops at a review (after a point, a goal, ...) or the end of the match; `ready()` leaves the review; `reset()` rebuilds the whole match
with the same seed. Private changes and repeated resets are allowed in development; none of them reaches the formal
match. The sport's code: `sports/tabletennis/` (`plugin.py`, `sport.toml` and its simulator modules).

## Submit a persistent program

Create `/app/output/policy/program.py`:

```python
def make_policy(config):
    # config["spec"]: the original action interface, the rules, cfg (seed, level, slowdown), frozen_commit
    return Policy()


class Policy:
    def act(self, view):
        if view["state"]["phase"] == "unit_over":
            return {"type": "ready"}
        return None  # replace with your controller
```

Helpers and data must be regular files under `policy/` (at most 512 files, 32 MiB in all; no links, devices, FIFOs
or sockets); they are importable by file name. The object lives for the whole match. It gets a view every 5 control steps (0.05 game s, 0.5 s of wall time at S = 10).
It receives a view: `state` (the twin's observation fields; `phase` is `playing`,
`unit_over` or `finished`, `service_phase` the core's own), `truth`, `scores` and an empty `observation`. It returns
one original action, a list of at most 1 actions, `{"type": "ready"}` (alone) during a review, or None.
There is no formal reset and no handle on the formal world; you may build your own private `Session` for predictions.

`truth` (the current physical state only):

`view["truth"]` is the state of the formal match at the step of the view (`state.step`), nothing later. Your frame is
the world frame (you are seat A; seat B's own frame is the world turned by 180 degrees about z).

- `ball_pos` [x, y, z] (m), `ball_vel` [vx, vy, vz] (m/s), `ball_spin` [wx, wy, wz] (rad/s): the ball now;
- `opponent_x`: the world x of the opponent's paddle centre now, `opponent_paddle_pos`, `opponent_q`, `opponent_qd`
  (its rail base and arm joints, in its own joint order);
- `leg`: the rally state (point, server, receiver, expect, launch step, hits, ...), `score` {A, B};
- `qpos`, `qvel`: the whole MuJoCo state; `servo`: your arm's servo state (targets, limits in force).

Seat B is the twin's built-in player (`sports/tabletennis/builtin_players.py`, class `RLOpponentV2`: learned shot
choices and its own joint-level swing, `rl/`), played inside the service process exactly as in the twin; it sees the
ball's true position (`Match.builtin_truth`). For development use `DuelSession` (below): a `Session` in which seat B
plays with that player every `b_every` control steps (default 1; in the formal match it acts about every 0.05 s of wall
time). One control step is 0.01 game seconds; at S = 10 that is 0.1 s of wall time. The rules (ITTF, one game to 5,
lead by 2, cap 7) and the action schema: `Session.spec()` and `sports/tabletennis/sport.toml`.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.duel --sport tabletennis --policy /app/output/policy --level 0 --seed 8 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh match on the original realtime service at S = 10
with your program, then replays the journal in a fresh process. `--unsafe-local` is a self-test, not the
trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs;
your program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. The
world keeps running at S = 10 while your program computes; each review freezes it (at most
300 s, else that side loses, as in the twin). Program load 30 s, each exchange 5 s, the formal match
7200 s of wall time, 2 GiB of address space, 7200 CPU seconds. No model or API calls in the
formal evaluation. Success: a complete win by the original referee, confirmed by a fresh replay. A missing,
invalid, stuck or unfinished program does not win. The deliverable is a program, not a trajectory.
After the verdict the verifier replays the formal match's record once more and draws `/logs/verifier/replay.mp4`
as the twin's service draws its video, for spectators only (nothing reads it back; a failed render leaves no video).
