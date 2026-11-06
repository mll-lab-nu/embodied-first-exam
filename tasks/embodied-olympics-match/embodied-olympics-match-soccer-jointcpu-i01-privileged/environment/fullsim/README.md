# Full-simulator program task: humanoid soccer at the joint level (CPU tier), level 5, seed 101

The development source at `/opt/fullsim` is complete and CPU-only: the frozen simulator of `embodied-olympics-match-soccer-jointcpu-i01-realtime` (this task's
camera-only twin), its referee and its learned joint-level opponent team. No GPU, renderer or simulator service is needed. Run the
commands inside the task's agent container from `/app`.

## First command: inspect, step and reset the actual simulator

```bash
python -c 'from tools.fullsim.session import Session; s=Session("soccer", level=5, seed=101); print(s.state()["scores"]); s.step(10); print(s.reset()["state"]["step"])'
```

`s.world` is the entire mutable Match object: the simulator, the learned joint-level opponent team and the referee.
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
or sockets); they are importable by file name. The object lives for the whole match. It gets a view every control step (20 ms of game time, 0.2 s of wall time at S = 10).
It receives a view: `state` (the twin's observation fields; `phase` is `playing`,
`unit_over` or `finished`, `service_phase` the core's own), `truth`, `scores` and an empty `observation`. It returns
one original action, a list of at most 2 actions, `{"type": "ready"}` (alone) during a review, or None.
There is no formal reset and no handle on the formal world; you may build your own private `Session` for predictions.

`truth` (the current physical state only):

`view["truth"]` is the state of the formal match at the step of the view, nothing later, in your team's frame (you
attack +x): `ball` [x, y, z] and `ball_v`, `robots` (`us1`, `us2`, `them1`, `them2`: x, y, yaw, fallen, bench) - the
same fields as the twin's observation `truth` - plus `k` (control step) and `qpos`, `qvel` (the whole MuJoCo state:
all four robots' joints and the ball). `view["state"]` is the twin's observation: per robot of yours its joint state
(joint_pos, joint_vel, trunk_quat, gyro, ...), the referee, the stoppages.

The joint level: per robot (entity "1", "2") `{"type": "joints", "q": [12 leg joint targets, rad]}` for the next 20 ms
control step, or `{"type": "traj", "k0": K, "q": [[12], ...]}`; each row is limited to the joint speed and ranges,
then PD every 2 ms, then the motors (`Session.spec()`: joint_level). A view comes every control step (20 ms of game
time, 0.2 s of wall time at S = 10); answer with up to 2 commands (one per robot). The opponent, level 5, is the
twin's learned joint-level team (sports/soccer/rl_joint.py, rl/joint/v2; numpy). Your program runs in the verifier on
the CPU with 2 GiB of address space: deploy what you learn as numpy (or plain Python) inference.

Resource tier: CPU only (6 cores, no GPU, no ML framework installed: numpy, SciPy and MuJoCo); the twin's seat toolkit
is at `/opt/robot`. The twin `embodied-olympics-match-soccer-jointgpu-i01-privileged` is the same task with one NVIDIA
GPU and a GPU training stack added; the formal match is the same in both tiers.

## Developer self-test of your saved program

```bash
python -m tools.fullsim.formal --sport soccer --policy /app/output/policy --level 5 --seed 101 \
  --out /tmp/my-self-test-1 --unsafe-local
```

Use a new output directory each time. This plays a fresh match on the original realtime service at S = 10
with your program, then replays the journal in a fresh process. `--unsafe-local` is a self-test, not the
trusted grading boundary.

The formal evaluation runs in a separate verifier without network: root owns the trusted simulator and the logs;
your program runs as nobody, with a read-only public copy of the simulator and a writable scratch directory. The
world keeps running at S = 10 while your program computes; each review freezes it (at most
300 s, else that side loses, as in the twin). Program load 30 s, each exchange 5 s, the formal match
10800 s of wall time, 2 GiB of address space, 10800 CPU seconds. No model or API calls in the
formal evaluation. Success: a complete win by the original referee, confirmed by a fresh replay. A missing,
invalid, stuck or unfinished program does not win. The deliverable is a program, not a trajectory.
After the verdict the verifier replays the formal match's record once more and draws `/logs/verifier/replay.mp4`
as the twin's service draws its video, for spectators only (nothing reads it back; a failed render leaves no video).
