# Full-simulator program task: soccer, level 2, seed 7

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `roboolympics-match-soccer-match-i00-standard-realtime` (this task's
camera-only twin), its referee and its scripted opponent. No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.fullsim.session import Session; s=Session("soccer", level=2, seed=7); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

`s.world` is the entire mutable Match object: the simulator, the scripted opponent, the referee and the planners.
`s.spec()` gives the original action interface and the rules as the twin's `game spec` states them. `act(command)`
handles an action as the live service does (parse, plan, lower, apply); `step(n)` advances `n` control steps and
stops at a review (after a point, a goal, ...) or the end of the match; `ready()` leaves the review; `reset()` rebuilds the whole match
with the same seed. Private changes and repeated resets are allowed in development; none of them reaches the formal
match. The sport's code: `sports/soccer/` (`plugin.py`, `sport.toml` and its simulator modules).

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
or sockets); they are importable by file name. The object lives for the whole match. Every 1 control steps
(and during each review) it receives a view: `state` (the twin's observation fields; `phase` is `playing`,
`unit_over` or `finished`, `service_phase` the core's own), `truth`, `scores` and an empty `observation`. It returns
one original action, a list of at most 2 actions, `{"type": "ready"}` (alone) during a review, or None.
There is no formal reset and no handle on the formal world; you may build your own private `Session` for predictions.

`truth` (the current physical state only):

`view["truth"]` (your team's frame = the world frame for seat A: you attack the goal at x = +5; metres, m/s, radians):

| field | what |
|---|---|
| `k` | the control step (20 ms of game time each) |
| `ball` | `pos` [x, y, z] (the ball's centre), `vel` [vx, vy, vz], `spin` [wx, wy, wz] |
| `robots` | `A1`, `A2` (yours: entities "1", "2") and `B1`, `B2` (the scripted team): `xy`, `yaw`, `z` (IMU height), `vel` [vx, vy, wz] (world frame), `fallen`, `bench` (penalized and removed), `penalty_s` (time left, or null), `kicking` (a kick under way) |
| `referee` | the game controller's internal state now: `state` (kickoff / play / pso_kick), `period` (1, 2, "pso"), `clock_s`, `kickoff` {`team`, `in_play`, `touched_outside`} or null, `free_kick` {`team`, `kind`, `spot`, `in_play`} or null, `shootout` {`n`, `team`, `striker`, `keeper`} or null (the kick under way) |
| `qpos`, `qvel` | the complete MuJoCo state (`Session("soccer", ...).world.w.m` is the model: joint names and addresses) |

Nothing of the future: no scripted team's plan, no random draws, no coming events. Your robots' own state (pose,
IMU, command under way, joint positions) and the referee's messages are in `view["state"]` as in the twin.

Robot soccer 2 v 2 (soccer-2v2-10, RoboCup Humanoid Soccer League rules with the deviations of `config["spec"]`): your
two Booster T1 (team A) against the scripted team B, two halves of 300 s of game time, a penalty shoot-out when level.
One control step is 20 ms of game time; at S = 5 it is 0.1 s of wall time, and the world runs on while your program
computes. Each robot takes one low-level command at a time: `{"type": "walk", "v": [vx, vy, wz], "entity": "1"}`,
`{"type": "stand", "entity": "2"}` or `{"type": "kick", "power": P, "style": "step"|"swing"|"push", ...}`
(`config["spec"]["act"]` and `config["spec"]["robot"]` have the schema, the strike zones and the kick timings). Return
`None`, one command, or a list of at most two commands (one per robot) per view; `{"type": "ready"}` alone during a
review (after every goal, half time, dropped ball and shoot-out kick). A command for a fallen or penalized robot is
refused. The world does not wait: a command takes effect at the next control step after it arrives.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.formal --sport soccer --policy /app/output/policy --level 2 --seed 7 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh match on the original realtime service at S = 5
with your program, then replays the journal twice in fresh processes. `--unsafe-local` is a self-test, not the
trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs;
your program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. The
world keeps running at S = 5 while your program computes; each review freezes it (at most
600 s, else that side loses, as in the twin). Program load 30 s, each exchange 5 s, the formal match
4800 s of wall time, 2 GiB of address space, 4800 CPU seconds. No model or API calls in the
formal evaluation. Success: a complete win by the original referee, confirmed by two fresh replays. A missing,
invalid, stuck or unfinished program does not win. The deliverable is a program, not a trajectory.
After the verdict the verifier replays the formal match's record once more and draws `/logs/verifier/replay.mp4`
as the twin's service draws its video, for spectators only (nothing reads it back; a failed render leaves no video).
