# {{title}}: a match against a scripted opponent, in real time

{{intro}}

**Your goal: win the match.** The task succeeds if the match finishes and you won it. Keep your scripts, logs and notes
in `/app/output/`; there is nothing else to hand in: the simulator records the match.

## Time does not stop
- The world runs at 1/{{slowdown}} of real speed (`spec()["timing"]["slowdown"]` = {{slowdown}}): one 10 ms control
  step of game time every {{wall_s_per_step}} s of wall time. It never waits for you: while you think, the opponent
  plays on and your robot keeps executing its last command.
- The match starts paused. Its clock starts at your first `submit` or `get_obs(seconds > 0)`, and from then on it runs
  until the match is over. Look at the cameras and read `spec()` first (`get_obs(seconds=0)` does not start the clock).
- **Breaks.** After every {{unit}} the match stands still for {{break_s}} s of game time ({{break_wall_s}} s of wall time):
  the clock keeps running, nothing moves and nothing scores, and play resumes by itself at the end of the break. Use it
  to look at what happened and fix your program. Send a `ready` row to resume earlier (put your review, why you won or
  lost the {{unit}} and what you change, in `submit`'s `note`). Commands planned for steps inside a break are dropped.
- You have {{agent_timeout_sec}} s in all. **If your session ends before the match is over, you lose** (success 0); so
  start the match well before your time runs out and stay until it is over (`meta["done"]`).
- No reset: one match is the whole episode.

## Write a program
A model response takes seconds, a {{unit}} only a few seconds of game time, so play with a program of your own: it
observes, measures in the images, computes its next command and submits it, in a loop, without a new model response
for each action. Run it in the background, watch its log, and stop, fix and restart it whenever needed (also during the
match). Use only the camera images, the service's replies and this document: no simulator internals or hidden state.

## Interface
The client is installed: `from rcb_client import Robot, EpisodeOver` (`/opt/tools/rcb_client.py`, on `PYTHONPATH`;
its docstring is the reference). Your container has Python 3.12 with numpy, SciPy, Pillow, requests and
opencv-python-headless; no internet except your model's API.

```python
r = Robot()                                   # connects to the simulator, waits until it is ready
spec = r.spec()                               # the facts: action_types, cameras, proprio_layout, rules, break, timing
res = r.get_obs(seconds=0)                    # now, at once: res.last[cam] (H x W x 3 uint8), res.proprio (rows)
res = r.get_obs(seconds=0.12, video_fps=25, video="frames")   # watch 0.12 s of game time: res.frames[cam] (N x H x W x 3)
r.submit("{{first_action}}", [row])                   # a command: answers at once; it takes effect at the next control step
r.submit("ready", [[0]], note="WHY ... PLAN ...")       # during a break: resume now
```

- `get_obs(cameras=None, seconds=0, video_fps=10, video="frames")`: `seconds=0` returns the current images and one
  proprio row; `seconds > 0` (at most `spec()["max_watch_s"]`) waits while that much game time runs and returns the
  frames the cameras saw (one every 1/`video_fps` s) and one proprio row per frame. `cameras=[]`: proprio only.
- `submit(type, rows, at=None, note="")`: one command per row; the rows become the plan from control step `at` (the
  next step by default; `meta["control_steps"]` is the next step's number), replacing whatever was planned from there.
  A row takes effect at its step: the command is checked and planned there, from the state of that step. Rows for
  steps that are already gone when the request arrives are dropped (`meta["late_steps"]`); out-of-range values are
  clipped (`meta["clipped"]`); a command the rules refuse at its step (e.g. {{refused_example}}) changes nothing and
  counts in the proprio column `commands_refused`.
- `res.meta`: `control_steps`, `sim_time_s`, `time_left_s`, `done`, `reason`, `running`, `lag_s`, and `proprio`
  (`layout`, `now`). `EpisodeOver` is raised once the match is over.

Your commands (`spec()["action_types"]`):

{{actions}}

Proprioception and the referee's information (`spec()["proprio_layout"]`, one float row per frame; NaN = not
applicable now; times in game seconds, positions in metres in your frame): {{proprio}}

Cameras: {{cameras}}

{{tip}}

## Rules
{{rules}}

Your robot: {{robot_text}}. Everything else you need (the frame, the geometry and the rule constants) is in
`spec()["rules"]`; the physics engine is MuJoCo.
