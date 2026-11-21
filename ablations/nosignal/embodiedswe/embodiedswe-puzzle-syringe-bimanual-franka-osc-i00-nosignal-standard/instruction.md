# Draw and dose liquid with a syringe (two Frankas, operational-space control) — standard mode

The task of `embodiedswe-puzzle-syringe-bimanual-franka-osc-i00-privileged`, on the same frozen scene. You drive two Franka Panda arms with parallel grippers, each under EmbodiedSWE's operational-space (torque) controller, as if it were real hardware: the simulator runs in a service you cannot open, and you get its client, one episode and no reset. The client's docstring is its manual (`/opt/tools/rcb_client.py`); `r.spec()` gives the numbers.

## The task
On the top shelf of a medical cart: a large syringe LYING FLAT (a scanned model — translucent barrel with graduation marks and finger flanges, a plunger with a thumb plate, travel 0.12 m = its full capacity, and a luer nozzle at the tip), a rack of three GLASS TEST TUBES, and a wide RESERVOIR beaker of water (its blue level visibly drops as liquid is drawn). The cart's lower shelf holds packaged syringes and a basin — scenery only.
Liquid moves with the plunger, but ONLY while the syringe is roughly upright with the nozzle tip seated on a mouth: hovering within 6 mm laterally and 12 mm above the rim. Pulling the plunger while seated on the reservoir draws liquid; pushing it dispenses into whichever tube the tip is seated on — anywhere else the liquid is WASTED. Tubes never un-fill: a tube pushed past its band is ruined for the episode (the reservoir can be re-drawn from, but over-dispensing cannot be undone). The water is VISIBLE: a blue column inside the translucent barrel shows the drawn liquid, and each tube fills with a blue column as it receives its dose. The plunger has deliberate friction: push/pull it slowly and steadily.
Goal: draw a full load (>= 95% of capacity, tip seated in the reservoir), dispense between 23% and 43% of capacity into EACH of the three tubes, then lay the syringe back down at its spot on the shelf.

Success, exactly: (1) at some moment the barrel held at least 95% of capacity (liquid gained only from plunger draw while the tip was seated on the reservoir) while the tip was seated on the reservoir beaker; (2) each of the three test tubes has received between 23% and 43% of capacity (0.12 m stroke), counting only plunger pushes made while the tip was seated on that tube's mouth; (3) now the syringe lies at its starting spot on the shelf: barrel centre within 60 mm horizontally of its start position, barrel axis within about 20.5 deg of horizontal (|vertical component| < 0.35), barrel centre within 80 mm of the shelf top height, moving slower than 0.05 m/s. 'Seated' = nozzle tip within 6 mm horizontally of the mouth centre, from 12 mm below to 12 mm above its rim, plunger end up with the barrel within ~31.8 deg of vertical, counted for 10 substeps after it last held. Not true at the start.

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
