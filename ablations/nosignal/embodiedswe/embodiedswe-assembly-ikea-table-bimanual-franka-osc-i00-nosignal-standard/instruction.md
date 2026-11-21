# Screw the four legs onto a side table (two Frankas, operational-space control) — standard mode

The task of `embodiedswe-assembly-ikea-table-bimanual-franka-osc-i00-privileged`, on the same frozen scene. You drive two Franka Panda arms with parallel grippers, each under EmbodiedSWE's operational-space (torque) controller, as if it were real hardware: the simulator runs in a service you cannot open, and you get its client, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

## The task
An IKEA-style side table, partly assembled, lying on a sturdy waist-high workbench. The free-standing tabletop slab (~0.55 x 0.55 m, 5 cm thick) carries 4 upright threaded studs at its corners (xy = (+0.25, +0.25), (-0.25, +0.25), (+0.25, -0.25), (-0.25, -0.25) m, relative to the slab centre). 4 loose legs — each a threaded nut on a graspable cylindrical shaft — lie on their side in a row near the centre of the workbench, ready to be picked up and fitted.
Goal: screw every leg down onto its stud (turn it clockwise while pressing down) until it seats. A seated leg locks in place. The table is assembled once all 4 legs are seated.

Success, exactly: at the end of the run, each of the 4 legs is screwed onto a stud of the tabletop slab: in the slab's own frame (origin at the centre of the slab's top face, the face carrying the studs; up = that face's normal), the point on the leg's axis at its threaded-nut end [the leg's origin] is at most 12 mm above the slab's top face (a leg sitting on top of a stud is at 26 mm), within 20 mm, in the slab plane, of one of the stud axes at (±0.25, ±0.25) m from the slab centre, and the leg's long axis, nut end to shaft end, is within 10° of the slab's up direction. Any leg may use any stud; the slab may have moved. Not true at the start (the legs lie on the workbench). [success() = seated().all(); leg origin = its nut body origin]

## This robot
- Action: `ee_pose` only, 18 values: left arm then right arm, each the world pose of its `panda_hand` (`x y z qw qx qy qz`) and its two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).
- Cameras (RGB 640×480, depth on request): `overview` (static), `left_wrist` (on the left hand), and `right_wrist` (on the right hand). One call returns at most 240 images (`max_frames_per_call`, PROTOCOL §3 "Images per call": cameras × the frames captured, the first, one every round(15 / `video_fps`) control steps and the last, a per-frame depth one more image; `video="none"` captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no cameras gets `overview`, `left_wrist`, `right_wrist` at 2 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.
- The episode ends after the first call at whose end the success condition holds (judged on the live simulator), when your time is up, on a simulator error, or after 400,000 control steps (7.4 h of simulated time, reason `step_guard`); it is graded as it stands then. Simulated time advances only inside your calls.
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
