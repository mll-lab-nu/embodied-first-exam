# MyoSuite · osl_run — frozen instance

You control the **MyoLeg + OSL**, a free-standing musculoskeletal model of a human whose right leg is an Open-Source Leg knee-ankle prosthesis (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 54
muscles and 2 non-muscle actuators: there is no joint-level controller.
**Task:** Run the track: move forward 29 m along it to the finish (MyoChallenge 2024 OSL Run, its own win condition), staying within 1 m of the track's centre line and on your feet; the right leg is the prosthesis (`osl_knee_angle_r`, `osl_ankle_angle_r`), driven by its own controller, so you command only the 54 muscles. Failure (the episode ends): falling, leaving the track sideways, or moving 2 m backwards. There is no time limit.

A musculoskeletal body whose right leg is an Open-Source Leg prosthesis (knee and ankle motors driven by its own controller) stands at the start of a straight, flat running track. `s.state()` gives the task's observation dict (privileged): `terrain`, `internal_qpos`, `internal_qvel`, `grf`, `socket_force`, `torso_angle`, `muscle_length`, `muscle_velocity`, `muscle_force`, `act`, `model_root_pos`, `model_root_vel`, `hfield`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myochallenge/run_track_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    """
    Rewards are computed from here, using the <self.weighted_reward_keys>.
    These weights can either be set in this file in the
    DEFAULT_RWD_KEYS_AND_WEIGHTS dict, or when registering the environment
    with gym.register in myochallenge/__init__.py
    """
    # act_mag = np.linalg.norm(self.obs_dict['act'], axis=-1)/self.mj_model.na if self.mj_model.na !=0 else 0
    act_mag = (
        np.mean(np.square(self.obs_dict["act"])) if self.mj_model.na != 0 else 0
    )
    pain = self.get_pain()

    # The task is entirely defined by these 3 lines
    score = self.get_score()
    win_cdt = self._win_condition()
    lose_cdt = self._lose_condition()

    self.obs_dict["time"] = self.maxTime if lose_cdt else self.obs_dict["time"]

    rwd_dict = collections.OrderedDict(
        (
            # Perform reward tuning here --
            # Update Optional Keys section below
            # Update reward keys (DEFAULT_RWD_KEYS_AND_WEIGHTS) accordingly to update final rewards
            # Example: simple distance function
            # Optional Keys
            ("act_reg", act_mag.squeeze()),
            ("pain", pain),
            # Must keys
            ("sparse", score),
            ("solved", win_cdt),
            ("done", self._get_done()),
        )
    )
    rwd_dict["dense"] = np.sum(
        [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
    )
    return rwd_dict
```
`solved` is the challenge's own success event: the episode ends in success at the first control step where it holds; `done` without it (its failure conditions, its own time limit) ends it as a failure. The gym step budget (`max_episode_steps`) is lifted; the challenge's own time limit is not.

This is a *fixed scene instance*: the start pose, the objects and the goal never change between resets. You may reset and
retry as many times as you want. Your deliverable is **one replayable trajectory**, not a general policy.

## Deliverable
Write the final trajectory to `/app/output/trajectory.npz` with `Session.save_trajectory(...)` (below). It is replayed
open-loop from the same initial state in two fresh processes and scored 1 if both episodes end in success in the same
state, else 0. Also leave the script that produced it at `/app/output/gen.py`.

Save a trajectory as soon as you have one that works, improve it while time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_myosuite import Session
s = Session("osl_run", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 56 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (56, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (5 ms): 56 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 56) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("side_view")            # RGB uint8 (480, 640, 3); cameras: topview, side_view, agent_view
s.render_video(actions, "/app/output/check.mp4", cameras=["side_view"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 56 real numbers per control step, one per actuator in order: 54 muscles and 2 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `osl_knee_torque_actuator` (index 54): ignored: the prosthesis's own impedance controller (MyoSuite's OSL state machine) sets it; `osl_ankle_torque_actuator` (index 55): ignored: the prosthesis's own impedance controller (MyoSuite's OSL state machine) sets it.
- Control step 5 ms (5 physics substeps). There is no step budget: your wall-clock time is the limit
  (~600 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
