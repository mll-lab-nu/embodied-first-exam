# Full-simulator program task: soccer_ssl, level 2, seed 7

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `roboolympics-soccerssl-match-i00-standard-realtime` (this task's
camera-only twin), its referee and its scripted opponent. No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.fullsim.session import Session; s=Session("soccer_ssl", level=2, seed=7); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

`s.world` is the entire mutable Match object: the simulator, the scripted opponent, the referee and the planners.
`s.spec()` gives the original action interface and the rules as the twin's `game spec` states them. `act(command)`
handles an action as the live service does (parse, plan, lower, apply); `step(n)` advances `n` control steps and
stops at a review (after a point, a goal, ...) or the end of the match; `ready()` leaves the review; `reset()` rebuilds the whole match
with the same seed. Private changes and repeated resets are allowed in development; none of them reaches the formal
match. The sport's code: `sports/soccer_ssl/` (`plugin.py`, `sport.toml` and its simulator modules).

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
or sockets); they are importable by file name. The object lives for the whole match. Every 5 control steps
(and during each review) it receives a view: `state` (the twin's observation fields; `phase` is `playing`,
`unit_over` or `finished`, `service_phase` the core's own), `truth`, `scores` and an empty `observation`. It returns
one original action, a list of at most 1 actions, `{"type": "ready"}` (alone) during a review, or None.
There is no formal reset and no handle on the formal world; you may build your own private `Session` for predictions.

`truth` (the current physical state only):

`view["truth"]` is the state of the formal match at the step of the view (`state.step`), nothing later:

- `t`, `step`: game time (s) and control step (0.01 s).
- `team`: `blue` (yours). Like every command and the observation, it is in **your team's frame** (you attack +x;
  `referee.attack_sign` maps it to the world frame, which flips at half time).
- `ball`: `pos` [x, y, z] (m), `vel` [vx, vy, vz] (m/s); `ball_spin` [wx, wy, wz] (rad/s, world frame).
- `us`, `them`: robot number -> `on_field`, `pose` [x, y, theta], `vel` [vx, vy, omega] (the yellow team's robots
  are `them`; true poses, no vision delay).
- `referee`: the game controller's information (as `state.referee`).
- `world`: `ball_pos`, `ball_vel` in the world frame; `attack_sign`.
- `qpos`, `qvel`: the complete MuJoCo state vectors (`Session.world.w.model` names the joints).
- `opponent_level` and `opponent_parameters` (the scripted team's level table: reaction delay, speed, scheme, ...).

No future information: no seed, no random stream, no plan of the scripted team. `state.robots` keeps your robots'
own sensors (kicker charge, break beam, dribbler, the skill's target and eta).

- One formal view every 5 control steps (and during every review). Return one act (a single command or a `batch` of
  up to five, one per robot), `{"type": "ready"}` during a review (after every goal, at half time, before the
  shoot-out and after every shoot-out kick: the world is frozen; at most 600 s), or `None`.
- The S = 10 clock: one control step every 0.1 s of wall time, whether your program has answered or not; the sport's
  declared reaction delay applies (an act takes effect 2 steps after the state it answers, or later if you answer
  later). A whole match is two halves of 300 s of playing time plus the stoppages: about 800-1070 s of game time,
  2.3-3 hours of wall clock in the verifier.
- `Session("soccer_ssl", level, seed)` in development: `s.act` applies a command at once (no reaction delay); use
  `s.step(2)` before `s.act` to reproduce the formal timing.
- The scripted team (`sports/soccer_ssl/opponents/`) is built on the sport's reference team
  (`sports/soccer_ssl/builtin_players.py`); both are readable in the development copy.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.formal --sport soccer_ssl --policy /app/output/policy --level 2 --seed 7 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh match on the original realtime service at S = 10
with your program, then replays the journal twice in fresh processes. `--unsafe-local` is a self-test, not the
trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs;
your program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. The
world keeps running at S = 10 while your program computes; each review freezes it (at most
600 s, else that side loses, as in the twin). Program load 30 s, each exchange 5 s, the formal match
13500 s of wall time, 2 GiB of address space, 13500 CPU seconds. No model or API calls in the
formal evaluation. Success: a complete win by the original referee, confirmed by two fresh replays. A missing,
invalid, stuck or unfinished program does not win. The deliverable is a program, not a trajectory.
After the verdict the verifier replays the formal match's record once more and draws `/logs/verifier/replay.mp4`
as the twin's service draws its video, for spectators only (nothing reads it back; a failed render leaves no video).
