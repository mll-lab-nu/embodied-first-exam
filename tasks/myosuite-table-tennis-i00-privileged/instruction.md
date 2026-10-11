# MyoSuite · table_tennis — frozen instance

You control the **MyoArm with torso**, a musculoskeletal model of a human torso, right arm and hand on a pelvis that slides on the floor (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 273
muscles and 2 non-muscle actuators: there is no joint-level controller.
**Task:** Return the served ball: hit it with the paddle so that it lands on the opponent's half of the table (MyoChallenge 2025 TableTennis P1's own success test on the ball's contact history: after the serve's bounce on your half, the paddle touches it once, then it touches the opponent's half, with no second paddle touch and no further bounce on your half). Failure (the episode ends): any other outcome of the rally, the ball falling below 0.3 m, or 3 s of simulated time.

You stand at a table-tennis table holding a paddle in the right hand; a ball is served toward you from the far side. `s.state()` gives the task's observation dict (privileged): `pelvis_pos`, `body_qpos`, `body_qvel`, `ball_pos`, `ball_vel`, `paddle_pos`, `paddle_vel`, `paddle_ori`, `padde_ori_err`, `reach_err`, `palm_pos`, `palm_err`, `touching_info`, `act`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myochallenge/tabletennis_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    reach_dist = np.abs(np.linalg.norm(self.obs_dict["reach_err"], axis=-1))
    palm_dist = np.abs(np.linalg.norm(self.obs_dict["palm_err"], axis=-1))
    act_mag = (
        np.linalg.norm(self.obs_dict["act"], axis=-1) / self.mj_model.na
        if self.mj_model.na != 0
        else 0
    )
    ball_pos = (
        obs_dict["ball_pos"][0][0]
        if obs_dict["ball_pos"].ndim == 3
        else obs_dict["ball_pos"]
    )
    solved = evaluate_pingpong_trajectory(self.contact_trajectory) == None
    paddle_quat_err = np.linalg.norm(obs_dict["padde_ori_err"], axis=-1)
    torso_err = abs(
        self.mj_data.qpos[
            self.mj_model.jnt_qposadr[self.mj_model.joint("flex_extension").id]
        ]
    )
    paddle_touch = (
        obs_dict["touching_info"][0][0]
        if obs_dict["touching_info"].ndim == 3
        else obs_dict["touching_info"]
    )
    # =========== for the baseline, we provide an h5 file in which you could perform simple imitation learning ===========
    # ======== uncomment to load the files and rewards =======================
    # qpos_ref, qvel_ref, qpos_err, qvel_err = self.ref_traj()()
    # ref_qpos_err = np.linalg.norm(qpos_err)
    # ref_qvel_err = np.linalg.norm(qvel_err)

    rwd_dict = collections.OrderedDict(
        (
            # Perform reward tuning here --
            # Update Optional Keys section below
            # Update reward keys (DEFAULT_RWD_KEYS_AND_WEIGHTS) accordingly to update final rewards
            # Examples: Env comes pre-packaged with two keys pos_dist and rot_dist
            # Optional Keys
            ("reach_dist", np.exp(-1.0 * reach_dist)),
            ("palm_dist", np.exp(-5.0 * palm_dist)),
            ("paddle_quat", np.exp(-5 * paddle_quat_err)),
            ("torso_up", np.exp(-5 * torso_err)),
            # ('ref_qpos_err', -1 * ref_qpos_err), use these for your imitation learning script
            # ('ref_qvel_err', -1 * ref_qvel_err),
            # Must keys
            ("act_reg", -1.0 * act_mag),
            ("sparse", paddle_touch[0] == 1),  # paddle_touching
            ("solved", np.array([[solved]])),
            ("done", np.array([[self._get_done(ball_pos[-1], solved)]])),
        )
    )

    rwd_dict["dense"] = sum(
        float(wt) * float(np.array(rwd_dict[key]).squeeze())
        for key, wt in self.rwd_keys_wt.items()
    )

    if rwd_dict["solved"]:
        self.cur_rally += 1
    if rwd_dict["solved"] and self.cur_rally < self.rally_count:
        rwd_dict["done"] = False
        rwd_dict["solved"] = False
        self.obs_dict["time"] = 0
        self.mj_data.time = 0
        self.contact_trajectory = []
        self.relaunch_ball()
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
s = Session("table_tennis", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 275 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (275, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (10 ms): 275 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 275) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("default")            # RGB uint8 (480, 640, 3); cameras: topview, default, close_up, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["default"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 275 real numbers per control step, one per actuator in order: 273 muscles and 2 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `pelvis_x` (index 273): normalized: a in [-1, 1] maps linearly onto [-1, 0.05] (position of joint pelvis_x); `pelvis_y` (index 274): normalized: a in [-1, 1] maps linearly onto [-1, 1] (position of joint pelvis_y).
- Control step 10 ms (5 physics substeps). There is no step budget: your wall-clock time is the limit
  (~300 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
