# MyoSuite · obj_reorient — frozen instance

You control the **MyoHand**, a musculoskeletal model of a human forearm and hand (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 39
muscles: there is no joint-level controller.
**Task:** Reorient the object held in the hand to the target orientation: the cosine between the object's orientation vector and the target's above 0.95, with the object within 0.075 m of the target position, for 100 consecutive control steps (1.0 s). Failure (the episode ends): the object more than 0.075 m from the target position (dropped).

An object (one of eight shapes; this instance fixes one) rests on the fingers of the upturned hand; a translucent copy shows the target orientation. `s.state()` gives the task's observation dict (privileged): `hand_jnt`, `obj_pos`, `obj_des_pos`, `obj_vel`, `obj_rot`, `obj_des_rot`, `obj_err_pos`, `obj_err_rot`, `act`, `mlen`, `mvel`, `mforce`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myobase/reorient_sar_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    pos_err = obs_dict["obj_err_pos"]
    pos_align = np.linalg.norm(pos_err, axis=-1)
    rot_align = calculate_cosine(obs_dict["obj_rot"], obs_dict["obj_des_rot"])
    dropped = pos_align > 0.075
    act_mag = (
        np.linalg.norm(self.obs_dict["act"], axis=-1) / self.mj_model.na
        if self.mj_model.na != 0
        else 0
    )
    rwd_dict = collections.OrderedDict(
        (
            # Optional Keys
            ("pos_align", -1.0 * pos_align),
            ("rot_align", rot_align),
            ("act_reg", -1.0 * act_mag),
            ("drop", -1.0 * dropped),
            (
                "bonus",
                1.0 * (rot_align > 0.9) * (pos_align < 0.075)
                + 5.0 * (rot_align > 0.95) * (pos_align < 0.075),
            ),
            # Must keys
            ("sparse", -1.0 * pos_align + rot_align),
            ("solved", (rot_align > 0.95) * (~dropped)),
            ("done", dropped),
        )
    )
    rwd_dict["dense"] = np.sum(
        [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
    )
    if list(self.mj_model.site_rgba[self.success_indicator_sid, :2]) != [0.0, 2.0]:
        self.mj_model.site_rgba[self.success_indicator_sid, :2] = (
            np.array([0, 2]) if rwd_dict["solved"] else np.array([2, 0])
        )
    return rwd_dict
```
Robot Coding Bench counts the goal only when `solved` holds for 100 consecutive control steps (1.0 s); `done` ends the episode as a failure. MyoSuite's step budget is lifted.

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
s = Session("obj_reorient", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 39 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (39, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (10 ms): 39 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 39) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("hand_top")            # RGB uint8 (480, 640, 3); cameras: side_view, front_view, front, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["hand_top"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 39 real numbers per control step, one per actuator in order: 39 muscles. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
- Control step 10 ms (5 physics substeps). There is no step budget: your wall-clock time is the limit
  (~2000 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## External material
You may install packages you need (pip, apt), and you may read anything installed in your container, the simulator's and this benchmark's own source code included. Please solve the task yourself: do not search the web for, or download, a ready-made solution to it, such as published or reference solutions, recorded demonstrations, or policies trained for it. This is an honour rule; trials are reviewed. The network reaches your model's API and the package registries (PyPI, Debian / Ubuntu archives) only.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.

## Time limit
You have 3600 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.

This is wall-clock time from the start of your session; the time a simulator takes to start counts. When it is up you are stopped without warning and only what is in `/app/output/` at that moment is graded, so save a deliverable as soon as you have one and overwrite it whenever you have a better one. Your session started when you received this task. `/run/rcb-limits/usage.json`, rewritten every few seconds, gives the time left on this limit (`time_left_s`) and its end (`deadline_utc`), counted from a little before your session started, so it never gives you more time than you have: read it (or run `date`) before you decide that time is short, never guess. Waiting counts too: a tool call that sends input to a process that keeps running (an interactive interpreter, a simulator loop, a server) can wait for the whole wait or yield time you give it (for example Codex's `yield_time_ms`) even when the answer is printed at once, so give such calls a short wait and poll again if the output is not complete, or run one-shot scripts that exit when they are done. Installing packages is not cheating (`## External material` above).
