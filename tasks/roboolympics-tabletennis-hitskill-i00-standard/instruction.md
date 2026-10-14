# Table tennis: implement the robot's `hit` skill (Agent as Robotics Engineer)

You are the robotics engineer of a robot that plays table tennis (robot table tennis in a continuous world slowed by a factor S). The platform's
high level gives players a skill `hit`; here you implement it yourself, for the real robot's joint interface and
limits, from the robot's model and a disclosed toolkit. There is no match and no simulator of the world in your
container: your skill is graded after your session, offline.

- Skill API: the contract (request ranges, what is measured, the tolerances, success) is `skill_contract` in `/opt/robot/skill_spec.json`.
- Deliverable: `/app/output/skill/hit.py` (plus any files it needs in `/app/output/skill/`) with
  `hit(t, pos, normal, vel, *, state, spec) -> one low-level command ({'type': 'traj', 'k0', 'q': rows of 9 targets} | {'type': 'slew', 'q', 'speed'} | {'type': 'hold'}) or None; the contact at control step state['step'] + round(t / 0.01) (in the API test the command takes effect at state['step']; in the match when your call returns, spec timing)`; optional: `step(*, state, spec) -> a command or None (called every 20 ms between hits: the return to a ready pose, the base's position)`. It may use numpy, scipy, mujoco, the toolkit under /opt/robot (robot_only.xml, assets, lib/tt_kinematics.py, lib/tt_servo.py) and files inside /app/output/skill; module-level memory between calls of one run; state = the low level's observe state (no images, no ball coordinates), spec = game spec's kinematics, limits, toolkit, skill_contract; no network, no other files, no other processes. It must be deterministic; time limits per call: load 30 s, hit 5 s, step 1 s.
- Toolkit: `/opt/robot/toolkit.toml` lists everything you are given (joint_interface, robot_model, robot_meshes, ik_library, servo_model); not given: hit.
- Practice requests: `/opt/robot/hit_cases_public.jsonl` (public; the evaluation uses 90 other requests of the same kind, not shown to you).
- The `spec` keyword every call receives (the robot's kinematics and limits, the toolkit, `skill_contract`) is in
  `/opt/robot/skill_spec.json`; `state` is the robot's low-level state (the practice requests show its fields).
- Your robot's own model is /opt/robot/robot_only.xml (MJCF: the rail base, the arm and the paddle only, nothing of the world; meshes in /opt/robot/assets), with MuJoCo at the simulator's version. Your toolkit (/opt/robot/toolkit.toml) also holds two optional libraries: /opt/robot/lib/tt_kinematics.py (PaddleKinematics: forward kinematics and Jacobians of the 9 joints, damped least-squares IK of the blade centre and face normal with the base at a given position, the rail's go-to law) and /opt/robot/lib/tt_servo.py (RobotSim: your robot's own servo law on the robot-only model, to roll your joint targets out before you send them). There is no hit skill or stroke planner at this level: implementing hit(t, pos, normal, vel) is your engineering task (skill_contract in /opt/robot/skill_spec.json; the practice requests /opt/robot/hit_cases_public.jsonl: each the request, the robot's state and our implementation's plan). The hit contract: the blade centre at pos, its face normal along normal and its velocity vel at the contact step k_c = k_eff + round(t / 0.01) (k_eff: the step your hit's command takes effect); within 2 cm, 3 degrees, 0.15 m/s + 10 % of |vel| and 10 ms (the blade's closest pass to pos), with no refused command and no net contact

## How you are graded
After your session the platform takes your FINAL `/app/output/skill/` and runs the API test in a separate,
isolated container (no network; your skill in its own process as an unprivileged user, a fresh process per request;
time limits per call {"load": 30, "hit": 5, "step": 1} s): 90 requests of the same kind as the practice
requests, each from its recorded start state in the full simulation (the world in play, the robot as the match left
it). Each request succeeds if the contract's measurement is within its tolerances (`skill_contract`). **Success: at
least 70 % of the requests.** The reward file also reports the rate and the errors.
Keep your notes and scripts in `/app/output/` too (only `/app/output/skill/` is evaluated).

## External material
You may install packages you need (pip, apt). Please solve the task yourself: do not look up or download a solution to it, such as this benchmark's own source code, published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for your agent environment, your own container only: at most **4 GiB of memory**, **512 processes** and **20 GiB** of new files under `/app`, `/tmp` and `/root`; your container has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 2 cores for your container; the cap only slows you down.

## Time limit
You have 7200 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time you wait for the simulator service counts. When it is up you are stopped without warning and the episode is graded as it stands at that moment. The service's `time_left_s` counts the same limit from your first request to the service, so it never runs out before your time does: your real time left is `time_left_s` minus the time you spent before that request. Plan by it. Your session started when you received this task: run `date` now, and again before you decide that time is short; work out the time left from those readings, never from a guess. Installing packages is not cheating (`## External material` above).
