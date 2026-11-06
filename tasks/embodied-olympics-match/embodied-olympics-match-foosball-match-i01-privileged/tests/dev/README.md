# Full-simulator program task: foosball, level 3, seed 7

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `embodied-olympics-match-foosball-match-i01-realtime` (this task's
camera-only twin), its referee and its scripted red team. No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.fullsim.session import Session; s=Session("foosball", level=3, seed=7); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

`s.world` is the entire mutable Match object: the simulator, the scripted red team and the referee.
`s.spec()` gives the original action interface and the rules as the twin's `game spec` states them. `act(command)`
handles an action as the live service does (parse, plan, lower, apply); `step(n)` advances `n` control steps and
stops at a review (after a point, a goal, ...) or the end of the match; `ready()` leaves the review; `reset()` rebuilds the whole match
with the same seed. Private changes and repeated resets are allowed in development; none of them reaches the formal
match. The sport's code: `sports/foosball/` (`plugin.py`, `sport.toml` and its simulator modules).

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
or sockets); they are importable by file name. The object lives for the whole match. It gets a view every control step (0.01 game s, 0.2 s of wall time at S = 20).
It receives a view: `state` (the twin's observation fields; `phase` is `playing`,
`unit_over` or `finished`, `service_phase` the core's own), `truth`, `scores` and an empty `observation`. It returns
one original action, a list of at most 1 actions, `{"type": "ready"}` (alone) during a review, or None.
There is no formal reset and no handle on the formal world; you may build your own private `Session` for predictions.

`truth` (the current physical state only):

`view["truth"]` is the state of the formal match at the step of the view (`state.t_play`), nothing later. World
frame: x along the table towards the opponent's goal (your local u, as you are seat A), y to your left (local v), z up,
the playfield at z = 0, the centre (0, 0); metres, radians, seconds of game time.

- `k` (control step of play, 0.01 s), `t_rally` (game seconds since this rally's restart);
- `ball_pos` [x, y, z] (m), `ball_vel` [vx, vy, vz] (m/s): the ball now;
- `rods`: `you` and `opponent` -> rod (`goalie`, `defence`, `midfield`, `attack`) -> `slide`, `angle`,
  `slide_velocity`, `angular_velocity` and the current `command` (each team in its own local frame, as
  `state.rods` gives yours);
- `figures`: `you` and `opponent` -> rod -> the world y of each figure now;
- `opponent_parameters`: the scripted team's level parameters (reaction `delay` in control steps, `predict`,
  `slide_v`, `omega`, `shoot`, `aim`, `style`);
- `restart` (`where`: the rod group and the team of the restart), `opening` (the opening sequence's state), `score`
  (goals and fouls per team);
- `qpos`, `qvel`: the whole simulator state vector (MuJoCo order: the eight rods' slide and spin joints, then the ball).

Units and timing: one control step is 0.01 game seconds; at S = 20 that is 0.2 s of wall time, and the program gets a
view every control step (it should answer in well under 0.2 s to keep up). A command (`{"type": "rods", "rods":
{rod: {"slide", "angle", "omega", "speed"}}}`; rods not named keep their command) reaches the motors 2 control steps
after the step that takes it. The rules (ITSF: one game to 5 goals, the opening sequence, possession limits per rod,
no spinning, the 240 s cap) and the action ranges: `Session.spec()` and `sports/foosball/sport.toml`. The scripted
team's policy is `sports/foosball/foos_policy.py`; it sees the ball `delay` steps late.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.formal --sport foosball --policy /app/output/policy --level 3 --seed 7 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh match on the original realtime service at S = 20
with your program, then replays the journal in a fresh process. `--unsafe-local` is a self-test, not the
trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs;
your program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. The
world keeps running at S = 20 while your program computes; each review freezes it (at most
300 s, else that side loses, as in the twin). Program load 30 s, each exchange 5 s, the formal match
6000 s of wall time, 2 GiB of address space, 6000 CPU seconds. No model or API calls in the
formal evaluation. Success: a complete win by the original referee, confirmed by a fresh replay. A missing,
invalid, stuck or unfinished program does not win. The deliverable is a program, not a trajectory.
After the verdict the verifier replays the formal match's record once more and draws `/logs/verifier/replay.mp4`
as the twin's service draws its video, for spectators only (nothing reads it back; a failed render leaves no video).
