# MyoSuite · bimanual — frozen instance

You control the **MyoArm + MPL**, a musculoskeletal right arm and hand next to a motorized prosthetic left arm (the Modular Prosthetic Limb) (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 63
muscles and 17 non-muscle actuators: there is no joint-level controller.
**Task:** Hand the object over: pick it up with the MyoHand, pass it to the prosthetic hand, and place it on the goal pillar. Success: the object within 0.17 m of the pillar top after touching only the pillar for 10 control steps, and MyoChallenge 2024's contact check on its whole history passes (held by the MyoHand for at least 100 control steps, by the prosthesis for at least 100, only the pillar at the end, never the table or the floor). Failure (the episode ends): the object below 0.3 m (dropped), or 10 s of simulated time.

The MyoArm (right, muscles) and a prosthetic MPL arm (left, motors) stand at a table; an object lies in front of the MyoHand and a pillar marks the goal on the far side. `s.state()` gives the task's observation dict (privileged): `qp`, `qv`, `myohand_qpos`, `myohand_qvel`, `pros_hand_qpos`, `pros_hand_qvel`, `object_qpos`, `object_qvel`, `start_pos`, `goal_pos`, `elbow_fle`, `max_force`, `touching_body`, `palm_pos`, `fin0`, `fin1`, `fin2`, `fin3`, `fin4`, `Rpalm_pos`, `MPL_ori`, `MPL_ori_err`, `obj_pos`, `reach_err`, `pass_err`, `act`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myochallenge/bimanual_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):

    reach_dist = np.abs(np.linalg.norm(obs_dict["reach_err"], axis=-1))
    pass_dist = np.abs(np.linalg.norm(obs_dict["pass_err"], axis=-1))

    obj_pos = (
        obs_dict["obj_pos"][0][0]
        if obs_dict["obj_pos"].ndim == 3
        else obs_dict["obj_pos"]
    )
    palm_pos = (
        obs_dict["palm_pos"][0][0]
        if obs_dict["palm_pos"].ndim == 3
        else obs_dict["palm_pos"]
    )
    goal_pos = (
        obs_dict["goal_pos"][0][0]
        if obs_dict["goal_pos"].ndim == 3
        else obs_dict["goal_pos"]
    )
    goal_pos = np.concatenate((goal_pos[:2], np.array([self.PILLAR_HEIGHT])))

    lift_height = np.linalg.norm(
        np.array([[[obj_pos[-1], palm_pos[-1]]]])
        - np.array([[[self.init_obj_z, self.init_palm_z]]]),
        axis=-1,
    )
    lift_height = 5 * np.exp(-10 * (lift_height - self.target_z) ** 2) - 5

    act = (
        np.linalg.norm(obs_dict["act"], axis=-1) / self.mj_model.na
        if self.mj_model.na != 0
        else 0
    )
    fin_keys = ["fin0", "fin1", "fin2", "fin3", "fin4"]
    fin_open = sum(
        np.linalg.norm(obs_dict[fin] - obs_dict["palm_pos"], axis=-1)
        for fin in fin_keys
    )
    fin_dis = sum(
        np.linalg.norm(obs_dict[fin] - obs_dict["obj_pos"], axis=-1)
        for fin in fin_keys
    )

    elbow_err = 5 * np.exp(-10 * (obs_dict["elbow_fle"][0] - 1.0) ** 2) - 5
    goal_dis = np.array([[np.abs(np.linalg.norm(obj_pos - goal_pos, axis=-1))]])

    touching_vec = (
        obs_dict["touching_body"][0][0]
        if obs_dict["touching_body"].ndim == 3
        else obs_dict["touching_body"]
    )

    if touching_vec[3] == 1:
        self.goal_touch += 1
    rwd_dict = collections.OrderedDict(
        (
            # Optional Keys
            ("reach_dist", reach_dist + np.log(reach_dist + 1e-6)),
            ("act", act),
            (
                "fin_open",
                np.exp(-5 * fin_open),
            ),  # fin_open + np.log(fin_open +1e-8)
            ("fin_dis", fin_dis + np.log(fin_dis + 1e-6)),
            ("lift_bonus", elbow_err),
            ("lift_height", lift_height),
            ("pass_err", pass_dist + np.log(pass_dist + 1e-3)),
            # Must keys
            ("sparse", 0),
            ("goal_dist", goal_dis),
            (
                "solved",
                goal_dis < self.proximity_th
                and self.goal_touch >= self.TARGET_GOAL_TOUCH,
            ),
            ("done", self._get_done(obj_pos[-1])),
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

Your time budget is 5400 s of wall clock. Save a trajectory as soon as you have one that works, improve it while
time remains, and do not stop early.

## Tooling (already installed; run `python` from any directory)
```python
from rcb_myosuite import Session
s = Session("bimanual", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 80 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (80, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (10 ms): 80 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 80) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("front_view")            # RGB uint8 (480, 640, 3); cameras: side_view, front_view, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["front_view"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 80 real numbers per control step, one per actuator in order: 63 muscles and 17 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `prosthesis/Lshoulder_fe` (index 63): normalized: a in [-1, 1] maps linearly onto [-0.611, 2.792] (position of joint prosthesis/Lshoulder_fe); `prosthesis/Lshoulder_abad` (index 64): normalized: a in [-1, 1] maps linearly onto [-2.792, 0] (position of joint prosthesis/Lshoulder_abad); `prosthesis/Lhumeral_rot` (index 65): normalized: a in [-1, 1] maps linearly onto [-0.524, 1.483] (position of joint prosthesis/Lhumeral_rot); `prosthesis/Lelbow` (index 66): normalized: a in [-1, 1] maps linearly onto [0.05, 2.356] (position of joint prosthesis/Lelbow); `prosthesis/A_wrist_PRO` (index 67): normalized: a in [-1, 1] maps linearly onto [-1.57, 1.57] (position of joint prosthesis/wrist_PRO); `prosthesis/A_wrist_UDEV` (index 68): normalized: a in [-1, 1] maps linearly onto [-0.26, 0.79] (position of joint prosthesis/wrist_UDEV); `prosthesis/A_wrist_FLEX` (index 69): normalized: a in [-1, 1] maps linearly onto [-1, 1] (position of joint prosthesis/wrist_FLEX); `prosthesis/A_thumb_ABD` (index 70): normalized: a in [-1, 1] maps linearly onto [0, 2.1] (position of joint prosthesis/thumb_ABD); `prosthesis/A_thumb_MCP` (index 71): normalized: a in [-1, 1] maps linearly onto [0, 1] (position of joint prosthesis/thumb_MCP); `prosthesis/A_thumb_PIP` (index 72): normalized: a in [-1, 1] maps linearly onto [0, 1] (position of joint prosthesis/thumb_PIP); `prosthesis/A_thumb_DIP` (index 73): normalized: a in [-1, 1] maps linearly onto [-0.82, 1.3] (position of joint prosthesis/thumb_DIP); `prosthesis/A_index_ABD` (index 74): normalized: a in [-1, 1] maps linearly onto [0, 0.34] (position of joint prosthesis/index_ABD); `prosthesis/A_index_MCP` (index 75): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/index_MCP); `prosthesis/A_middle_MCP` (index 76): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/middle_MCP); `prosthesis/A_ring_MCP` (index 77): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/ring_MCP); `prosthesis/A_pinky_ABD` (index 78): normalized: a in [-1, 1] maps linearly onto [0, 0.34] (position of joint prosthesis/pinky_ABD); `prosthesis/A_pinky_MCP` (index 79): normalized: a in [-1, 1] maps linearly onto [0, 1.6] (position of joint prosthesis/pinky_MCP).
- Control step 10 ms (5 physics substeps). There is no step budget: your wall-clock time is the limit
  (~600 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
