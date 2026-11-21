# Pack three tools into their drawers (Franka, operational-space control) — standard mode

The task of `embodiedswe-packing-tool-packing-franka-osc-i00-privileged`, on the same frozen scene. You drive a Franka Panda arm with its parallel gripper, under EmbodiedSWE's operational-space (torque) controller, as if it were real hardware: the simulator runs in a service you cannot open, and you get its client, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

## The task
A black high-gloss chest of drawers (~37 cm wide, 36 cm tall) stands on the table: four sliding drawers stacked top to bottom, each with a real pull handle on its front. All drawers start shut. In front of the chest lie three tools: a green stapler, a pair of scissors, and a utility knife.
Goal: pull drawers open as needed and pack the tools — the STAPLER goes in the TOP (1st) drawer, the SCISSORS in the SECOND drawer, the KNIFE in the THIRD drawer (the 4th/bottom drawer stays shut and gets nothing) — then push every drawer shut. An item counts only inside its own drawer's tray; the job is done when all three tools are stowed and every drawer is shut.

Success, exactly: a fixed point of the green stapler's body, not necessarily its centre [its rigid-body origin], lies inside the top drawer's tray interior, the scissors' inside the second drawer's, and the utility knife's inside the third drawer's — each tray interior being a box measured in that drawer's own frame (so it moves with the drawer), 355 mm side-to-side x 139 mm front-to-back x 54 mm tall [tray_center (0, 0.0006, 0.0388) m +/- tray_half (0.1775, 0.0694, 0.0268) m in the drawer link frame]; all four drawers (including the empty bottom one) are pulled out less than 15 mm from fully shut; every tool moves slower than 0.05 m/s and every drawer slides slower than 0.05 m/s. Not true at the start (drawers shut, tools on the table).

## This robot
- Action: `ee_pose` only, 9 values: the world pose of `panda_hand` (`x y z qw qx qy qz`) and the two finger position targets (m, 0 closed, 0.04 open). Rows are streamed at the 15 Hz control rate with your `dt`; `spec["action_types"]["ee_pose"]` has the layout, the controller and the joint limits. Coordinates are the simulator's world frame (metres, z up; `spec["world"]`).
- Cameras (RGB 640×480, depth on request): `overview` (static) and `wrist` (on the hand). One call returns at most 240 images (`max_frames_per_call`, PROTOCOL §3 "Images per call": cameras × the frames captured, the first, one every round(15 / `video_fps`) control steps and the last, a per-frame depth one more image; `video="none"` captures only the first and the last); a larger request is refused (400) before anything runs. A call that names no cameras gets `overview`, `wrist` at 4 frames per second, so every call up to `max_chunk_s` / `max_watch_s` fits.
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
