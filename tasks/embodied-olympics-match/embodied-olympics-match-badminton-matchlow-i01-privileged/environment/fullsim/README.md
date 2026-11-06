# Full-simulator program task: badminton at the low level, level 2, seed 8

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `embodied-olympics-match-badminton-matchlow-i01-realtime` (this task's
camera-only twin), its referee and its scripted opponent. No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.fullsim.session import Session; s=Session("badminton", level=2, seed=8); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

`s.world` is the entire mutable Match object: the simulator, the scripted opponent and the referee.
`s.spec()` gives the original action interface and the rules as the twin's `game spec` states them. `act(command)`
handles an action as the live service does (parse, plan, lower, apply); `step(n)` advances `n` control steps and
stops at a review (after a point, a goal, ...) or the end of the match; `ready()` leaves the review; `reset()` rebuilds the whole match
with the same seed. Private changes and repeated resets are allowed in development; none of them reaches the formal
match. The sport's code: `sports/badminton/` (`plugin.py`, `sport.toml` and its simulator modules).

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
or sockets); they are importable by file name. The object lives for the whole match. It gets a view every 2 control steps (0.02 game s, 0.4 s of wall time at S = 20), the twin's in-loop cadence.
It receives a view: `state` (the twin's observation fields; `phase` is `playing`,
`unit_over` or `finished`, `service_phase` the core's own), `truth`, `scores` and an empty `observation`. It returns
one original action, a list of at most 1 actions, `{"type": "ready"}` (alone) during a review, or None.
There is no formal reset and no handle on the formal world; you may build your own private `Session` for predictions.

`truth` (the current physical state only):

- `shuttle_pos`, `shuttle_vel`: the shuttle's position (m) and velocity (m/s) now, `shuttle_live` (in flight);
- `opponent_xy`: where the opponent's base is now, `opponent_parameters`: its level's parameters;
- `leg`: the current leg (kind, point, state, server, launch step, serve window), `score`, `k` (control step);
- `qpos`, `qvel`: your robot's joints (base x, y and the arm) in the simulator's order; `target`: the joint targets.

The low level (the twin's skill in the loop, without its plumbing): your program returns the robot's LOW-LEVEL
commands itself, `{"type": "traj", "q": rows of 9 joint targets}` (one row per control step from the next step on;
then the robot returns to its ready pose and the base holds), `{"type": "move", "base"}`, `{"type": "toss", ...}`
and `{"type": "none"}` (the schema: `Session.spec()["actions"]`), every view (every 2 control steps, the twin's
in-loop cadence). There is no `act` skill and no skill server: what the twin's skill computes (the stroke within the
real limits) your program computes, and its computation counts as the twin's skill's does (the world runs on while
it computes; a command takes effect at the first control step after the answer). The low-level toolkit of the twin
(the robot's own model, the kinematics and servo libraries) is in your copy of the simulator under
`sports/badminton/seat/` (the twin's /opt/robot). Coordinates: metres, +y toward the opponent, the net at y = 0.
One control step is 0.01 game seconds; at S = 20 that is 0.2 s of wall time.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.formal --sport badminton --policy /app/output/policy --level 2 --seed 8 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh match on the original realtime service at S = 20
with your program, then replays the journal in a fresh process. `--unsafe-local` is a self-test, not the
trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs;
your program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. The
world keeps running at S = 20 while your program computes; each review freezes it (at most
300 s, else that side loses, as in the twin). Program load 30 s, each exchange 5 s, the formal match
7200 s of wall time, 2 GiB of address space, 7200 CPU seconds. No model or API calls in the
formal evaluation. Success: a complete win by the original referee, confirmed by a fresh replay. A missing,
invalid, stuck or unfinished program does not win. The deliverable is a program, not a trajectory.
After the verdict the verifier replays the formal match's record once more and draws `/logs/verifier/replay.mp4`
as the twin's service draws its video, for spectators only (nothing reads it back; a failed render leaves no video).
