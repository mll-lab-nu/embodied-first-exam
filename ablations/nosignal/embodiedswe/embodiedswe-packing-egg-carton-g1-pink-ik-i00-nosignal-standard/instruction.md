# Put three eggs in the carton and close the lid (Unitree G1, fixed pelvis, Pink IK) — standard mode

The task of `embodiedswe-packing-egg-carton-g1-pink-ik-i00-privileged`, on the same frozen scene. You drive a Unitree G1 humanoid with three-finger hands, its pelvis fixed, its arms and waist under EmbodiedSWE's Pink IK, as if it were real hardware: the simulator runs in a service you cannot open, and you get its client, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

## The task
Four loose eggs lie on their sides on the left half of the table. On the right is a small four-cell egg carton fixed to the table, with its hinged lid standing fully open. The carton has four distinct pockets in a 2 by 2 layout.
Goal (three stages): pick eggs from the table one at a time, turn each upright, and place three eggs securely in three DISTINCT carton pockets; then push the hinged lid closed over them. Every seated egg must remain upright and settled, and the lid must rest closed at the end. The fourth egg is a distractor and can stay on the table.

Success, exactly: at the end of the run three different pockets of the 2 x 2 carton each hold a seated egg (at least three eggs seated, at least three distinct pockets occupied). Pocket centres are 30 mm from the carton's centre along each of its two base axes. An egg counts as seated when, in the carton's base frame (origin at the carton's bottom centre, z along the carton's up), its centre is within 21 mm horizontally of a pocket centre and 15-42 mm above the carton base, its long axis is within 50° of the carton's vertical (either end up), and it moves slower than 0.05 m/s. The hinged lid is within 7° of fully shut; it starts 110° open. All four eggs, the spare included, move slower than 0.05 m/s, and the lid swings slower than 0.10 rad/s. Not true at the start.

## This robot
- Action: `ee_pose` only, 28 values: the world poses of the left and right `wrist_yaw_link` (`x y z qw qx qy qz` each), then 14 hand joint targets (rad). Rows are streamed at the 60 Hz control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).
- Cameras (RGB 640×480, depth on request): `overview` (static) and `head` (on the torso, where the real G1 carries its depth camera). One call returns at most 240 images (`max_frames_per_call`, PROTOCOL §3 "Images per call": cameras × the frames captured, the first, one every round(60 / `video_fps`) control steps and the last, a per-frame depth one more image; `video="none"` captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no cameras gets `overview`, `head` at 3 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.
- The episode ends after the first call at whose end the success condition holds (judged on the live simulator), when your time is up, on a simulator error, or after 400,000 control steps (1.9 h of simulated time, reason `step_guard`); it is graded as it stands then. Simulated time advances only inside your calls.
- The service answers one request at a time: while a long call runs, every other request waits, so a client-side timeout means "busy", not "crashed".
- Leave your scripts in `/app/output/` for the record.

## This run: no success signal

This run changes how the episode ends. This section overrides anything above, and anything in `/spec`, that says a
success ends the episode, that `meta["reason"]` can be `"success"`, or that a success refuses later calls or resets.

- The robot never tells you whether you have succeeded: reaching the goal changes no response, status, error or
  counter, and the episode does not end there.
- You decide when you are done: send `POST /finish` with an empty JSON body (`{}`) to the service, on the same base
  URL as your other calls (`http://sim:8000` or `http://localhost:8000`; in Python, for example
  `requests.post(base + "/finish", json={})`). The state at that moment is graded with the task's success rule (with
  the task's settle or hold time described above, run from that state). After `/finish` every call is refused (409).
- If you do not call it, the state when your session ends (you stop, or your time runs out) is graded.
- A success reached earlier and then undone does not count: only the state at the end is graded. An event the task
  records once it happens (for example a scored goal or a completed stage sequence) stays part of that state, also
  when one of the task's failure rules ends the episode after it. Resets work as described above, within the budget,
  and only the episode that ends with `/finish` or at the end of your session is graded.
- The episode still ends on its own on a simulator error, at the task's technical step limit (graded as it stands),
  and where the task's own rules end it as a failure (for example a fall), as described above.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resources
Your container: **8 CPUs**, **24 GiB of memory**, **1024 processes and threads** and **10 GiB** of disk (new files under `/app`, `/tmp` and `/root`). Your container has no GPU. The simulator runs in its own container and does not count against these. CPU only slows you down; a process that goes over any other cap can be killed. Usage and caps: `/run/rcb-limits/usage.json`.

## Time limit
You have 14400 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
