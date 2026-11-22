# EmbodiedSWE · draw and dose liquid with a syringe, two Frankas (standard)

## Task
Two Franka Panda arms with parallel grippers, each under EmbodiedSWE's operational-space (torque) controller. On the top
shelf of a medical cart: a large syringe LYING FLAT (a scanned model — translucent barrel with graduation marks and
finger flanges, a plunger with a thumb plate, travel 0.12 m = its full capacity, and a luer nozzle at the tip), a rack
of three GLASS TEST TUBES, and a wide RESERVOIR beaker of water (its blue level visibly drops as liquid is drawn). The
cart's lower shelf holds packaged syringes and a basin — scenery only. Draw a full load (>= 95% of capacity, tip seated
in the reservoir), dispense between 23% and 43% of capacity into EACH of the three tubes, then lay the syringe back down
at its spot on the shelf. The robot runs as a service you reach only through its client, as if it were real hardware:
one live episode.

## Goal
Success: you drew a full load from the reservoir (tip seated on it), dosed each of the three tubes with 23% to 43% of
the capacity (tip seated on its mouth), and the syringe now lies back at its starting spot on the shelf, roughly flat
and at rest. What counts is how things stand at the end of the episode: a success reached earlier and lost by the end
does not count, so finish in the state you want graded and stop sending commands.

Nothing to hand in: the service records and grades the episode. Keep the script that drives the robot at
`/app/output/gen.py`.

Real-robot rules:
- One episode, no reset: what you knock over stays knocked over.
- No privileged state: you get the robot's camera images (with their calibration) and its own sensor readings; no object
  poses, no scene layout, no success signal.
- Write your own controller; do not use the benchmark's demonstrations, trained policies or any published solution.

### This run: no success signal
This run changes how the episode ends.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or counter,
  and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base URL
  as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with the
  task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also when
  one of the task's failure rules ends the episode after it. Resets work as described above, within the budget, and only
  the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands), and
  where the task's own rules end it as a failure (for example a fall), as described above.

## Robot Interface
### Client
`/opt/tools/rcb_client.py`: its docstring is its manual; `r.spec()` gives the numbers. The service answers one request
at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
Simulated time advances only inside your calls. One call returns at most 240 images (cameras × the frames captured: the
first, one every round(15 / `video_fps`) control steps and the last; a per-frame depth one more image; `video="none"`
captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no
cameras gets `overview`, `left_wrist`, `right_wrist` at 2 frames per second, so every call up to `max_chunk_s` /
`max_watch_s` fits.

### Actions
The action is `ee_pose` only, 18 values: left arm then right arm, each the world pose of its `panda_hand`
(`x y z qw qx qy qz`) and its two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz
control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits.
Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).

### Observations
Cameras (RGB 640×480, depth on request): `overview` (static), `left_wrist` (on the left hand), and `right_wrist` (on the
right hand).

## Others
- Liquid moves with the plunger, but ONLY while the syringe is roughly upright with the nozzle tip seated on a mouth:
  hovering within 6 mm laterally and 12 mm above the rim. Pulling the plunger while seated on the reservoir draws
  liquid; pushing it dispenses into whichever tube the tip is seated on — anywhere else the liquid is WASTED. Tubes
  never un-fill: a tube pushed past its band is ruined for the episode (the reservoir can be re-drawn from, but
  over-dispensing cannot be undone). The water is VISIBLE: a blue column inside the translucent barrel shows the drawn
  liquid, and each tube fills with a blue column as it receives its dose. The plunger has deliberate friction: push/pull
  it slowly and steadily.

## Limits
- Time: 14400 s of wall-clock time from the start of your session; everything counts (waiting for the service too). At
  the end you are stopped without warning and the episode is graded as it stands. Time left:
  `/run/rcb-limits/usage.json` (`time_left_s`, `deadline_utc`); the service's `time_left_s` (in every reply) starts at
  your first request, so the file is the one to trust. Calls into a long-running process can block for their whole wait
  time: use short waits or one-shot scripts.
- Tokens: no separate limit.
- Network: your model's API and the package registries (PyPI, Debian / Ubuntu archives) only. You may install packages
  and read anything in your container, the simulator's and the benchmark's source included. Do not search for or
  download a ready-made solution (published or reference solutions, recorded demonstrations, trained policies); trials
  are reviewed.
- Resources: 8 CPUs, 24 GiB memory, 1024 processes and threads, 10 GiB disk (new files under `/app`, `/tmp`, `/root`),
  no GPU; the simulator runs in its own container and does not count. Over a cap a process can be killed (the CPU cap
  only slows you down); usage: `/run/rcb-limits/usage.json`.
- Resets: none: one episode.
- Steps: at most 400,000 control steps (7.4 h of simulated time, reason `step_guard`); then the episode ends and is
  graded as it stands.
