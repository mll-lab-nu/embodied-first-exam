# MyoSuite · dex_apple_lift — frozen instance

You control the **MyoHand**, a musculoskeletal model of a human forearm and hand (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 39
muscles and 6 non-muscle actuators: there is no joint-level controller.
**Task:** Move the apple along MyoDex's recorded lift motion: a reference of the object's pose over 57 control steps (1.14 s), from GRAB motion capture (TCDM / MyoDex). The episode lasts exactly those 57 steps. Success: the object's motion follows the reference's: its centre of mass's displacement since the start within 0.03 m of the reference's displacement since the reference's start, at at least 90% of the control steps and at the last one, with the displacement error never above 0.05 m. Failure (the episode ends early): MyoDex's termination, the object more than 0.25 m from the reference or from the wrist.

An apple lies on the table; the MyoHand (with a 6-DoF positioned wrist) is at its pre-grasp pose next to it. `s.state()` gives the task's observation dict (privileged): `qp`, `qv`, `robot_err`, `curr_hand_qpos`, `curr_hand_qvel`, `targ_hand_qpos`, `targ_hand_qvel`, `curr_obj_com`, `curr_obj_rot`, `wrist_err`, `base_error`, `targ_obj_com`, `targ_obj_rot`, `hand_qpos_err`, `hand_qvel_err`, `obj_com_err`, `act`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myodm/myodm_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    # get targets from reference object
    tgt_obj_com = obs_dict["targ_obj_com"].flatten()
    tgt_obj_rot = obs_dict["targ_obj_rot"].flatten()

    # get real values from physics object
    obj_com = obs_dict["curr_obj_com"].flatten()
    obj_rot = obs_dict["curr_obj_rot"].flatten()

    # calculate both object "matching"
    obj_com_err = np.sqrt(self.norm2(tgt_obj_com - obj_com))
    obj_rot_err = self.rotation_distance(obj_rot, tgt_obj_rot, False) / np.pi
    obj_reward = np.exp(-self.obj_err_scale * (obj_com_err + 0.1 * obj_rot_err))

    # calculate lift bonus
    lift_bonus = (tgt_obj_com[2] >= self._lift_z) and (obj_com[2] >= self._lift_z)

    # reward = obj_reward + self.lift_bonus_mag * float(lift_bonus)

    # calculate reward terms
    qpos_reward = np.exp(
        -self.qpos_err_scale * self.norm2(obs_dict["hand_qpos_err"])
    )
    qvel_reward = (
        np.array([0])
        if obs_dict["hand_qvel_err"] is None
        else np.exp(-self.qvel_err_scale * self.norm2(obs_dict["hand_qvel_err"]))
    )

    # weight and sum individual reward terms
    pose_reward = self.qpos_reward_weight * qpos_reward
    vel_reward = self.qvel_reward_weight * qvel_reward

    # print(f"Time: {obs_dict['time']} Error Pose: {self.norm2(obs_dict['hand_qpos_err'])} {obs_dict['hand_qpos_err']}    Error Obj:{obs_dict['obj_com_err']}")

    base_error = np.sqrt(self.norm2(obs_dict["base_error"]))
    base_reward = np.exp(-self.base_err_scale * base_error)

    # print(base_error, base_reward)

    rwd_dict = collections.OrderedDict(
        (
            # Optional Keys
            ("pose", float(pose_reward + vel_reward)),
            ("object", float(obj_reward + base_reward)),
            ("bonus", self.lift_bonus_mag * float(lift_bonus)),
            ("penalty", float(self.check_termination(obs_dict))),
            # Must keys
            ("sparse", 0),
            ("solved", 0),
            ("done", self.initialized_pos and self.check_termination(obs_dict)),
        )
    )
    rwd_dict["dense"] = np.sum(
        [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
    )

    # print(rwd_dict['dense'], obj_com_err,rwd_dict['done'],rwd_dict['sparse'])
    return rwd_dict
```
MyoDex's `solved` is always 0, so Robot Coding Bench judges the tracking itself: the episode lasts 57 control steps (the reference) and succeeds as stated above; `done` (MyoDex's termination) ends it early as a failure. `s.status()['info']` reports the current errors (`track_pos_err`, `track_rot_err`) and the count of on-track steps (`track_ok`).

The reference motion (the goal) is MyoDex's `s.base.ref` and, per control step, the observation's `targ_obj_com` / `targ_obj_rot`; `curr_obj_com` / `curr_obj_rot` are the object's.

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
s = Session("dex_apple_lift", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 45 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (45, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (20 ms): 45 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 45) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("center_cam")            # RGB uint8 (480, 640, 3); cameras: left_cam, right_cam, center_cam, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["center_cam"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 45 real numbers per control step, one per actuator in order: 39 muscles and 6 non-muscle actuators. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity. The non-muscle actuators: `A_ARTx` (index 0): position target of joint ARTx in [-0.75, 0.5]; `A_ARTy` (index 1): position target of joint ARTy in [-0.5, 0.5]; `A_ARTz` (index 2): position target of joint ARTz in [-0.5, 0.3]; `A_ARRx` (index 3): position target of joint ARRx in [-1.75, 1.75]; `A_ARRy` (index 4): position target of joint ARRy in [-1.75, 1.75]; `A_ARRz` (index 5): position target of joint ARRz in [-1.75, 1.75].
- Control step 20 ms (10 physics substeps). There is no step budget: your wall-clock time is the limit
  (~500 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.

## External material
Use only what is in your container and the task interface described above. Do not download or install anything: no source code, robot models, datasets, demonstrations, pretrained policies, published solutions or packages. Do not use web search, browsing, account connectors or any other tool that runs outside your container. Network access is limited to your model's API. A result obtained with external material is void.

## Resource limits
Limits for the whole trial, all its processes together (every simulator you start included): at most **10 GiB of memory**, **512 processes** and **10 GiB** of new files under `/app`, `/tmp` and `/root`; the task has no GPU. These limits may be enforced (from protocol v1.2 on): when enforcement is on, exceeding one for 60 s within any 2 minutes, or a process killed for lack of memory, ends the trial as a failure (reward 0), whatever the deliverable. A monitor outside your container measures every few seconds; the current values are in `/run/rcb-limits/usage.json`. CPU is capped at 4 cores for your container; the cap only slows you down.
