# MyoSuite · key_turn — frozen instance

You control the **MyoHand**, a musculoskeletal model of a human forearm and hand (MyoSuite 2.12.2 on MuJoCo), via Python, through its actuators — 39
muscles: there is no joint-level controller.
**Task:** Turn the key held between the thumb and the index finger by more than 3.14 rad (half a turn). Success: the key's hinge angle above 3.14 rad for 50 consecutive control steps (1.0 s). Failure (the episode ends): the index or thumb tip more than 0.10 m from the key head.

The key sits in a lock in front of the palm; its head is between the thumb and the index finger. `s.state()` gives the task's observation dict (privileged): `hand_qpos`, `hand_qvel`, `key_qpos`, `key_qvel`, `IFtip_approach`, `THtip_approach`, `act`.
MyoSuite's reward code (from `/usr/local/lib/python3.11/site-packages/myosuite/envs/myo/myobase/key_turn_v0.py`; `solved` is the goal test,
`done` the failure test):
```python
def get_reward_dict(self, obs_dict):
    IF_approach_dist = np.abs(
        np.linalg.norm(self.obs_dict["IFtip_approach"], axis=-1) - 0.030
    )
    TH_approach_dist = np.abs(
        np.linalg.norm(self.obs_dict["THtip_approach"], axis=-1) - 0.030
    )
    key_pos = (
        obs_dict["key_qpos"][:, :, 0]
        if obs_dict["key_qpos"].ndim == 3
        else obs_dict["key_qpos"][0]
    )
    act_mag = (
        np.linalg.norm(self.obs_dict["act"], axis=-1) / self.mj_model.na
        if self.mj_model.na != 0
        else 0
    )
    far_th = 0.1
    rwd_dict = collections.OrderedDict(
        (
            # Optional Keys
            ("key_turn", key_pos),
            ("IFtip_approach", -1.0 * IF_approach_dist),
            ("THtip_approach", -1.0 * TH_approach_dist),
            ("act_reg", -1.0 * act_mag),
            ("bonus", 1.0 * (key_pos > np.pi / 2) + 1.0 * (key_pos > np.pi)),
            (
                "penalty",
                -1.0 * (IF_approach_dist > far_th / 2)
                - 1.0 * (TH_approach_dist > far_th / 2),
            ),
            # Must keys
            ("sparse", key_pos),
            ("solved", obs_dict["key_qpos"] > self.goal_th),
            ("done", (IF_approach_dist > far_th) or (TH_approach_dist > far_th)),
        )
    )
    rwd_dict["dense"] = np.sum(
        [wt * rwd_dict[key] for key, wt in self.rwd_keys_wt.items()], axis=0
    )
    return rwd_dict
```
Robot Coding Bench counts the goal only when `solved` holds for 50 consecutive control steps (1.0 s); `done` ends the episode as a failure. MyoSuite's step budget is lifted.

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
s = Session("key_turn", instance="/app/instance.npz")   # a few seconds
s.reset()                          # back to the frozen initial state (unlimited; an exact snapshot restore)
s.state()                          # the task's observation dict (privileged; see above)
s.actuators(); s.muscles(); s.joints()   # 39 actuators (kind, command); muscles; hinge/slide joints (qpos/dof address, range)
s.moment_arms()                    # (39, nv) actuator moment arms at the current pose
s.model, s.data                    # MuJoCo model / data: read them freely; only the actions you record are replayed
s.excitation(a); s.command_for(u)  # muscle command a -> excitation u = 1/(1+exp(-5(a-0.5))) and its inverse
s.step(a)                          # one control step (20 ms): 39 commands; False once the episode is over
s.rest_action()                    # every command at -1 (muscles relaxed)
s.status()                         # {'success', 'done', 'reason', 'steps', 'resets', 'solved_run', 'rule', 'state_sha', 'info', ...}
s.record_start(); ...; actions = s.record_stop()   # (T, 39) commands, one row per control step
s.replay(actions)                  # resets, replays open-loop until the episode ends, returns status -> self-check
s.save_trajectory(actions, "/app/output/trajectory.npz")
s.render_frame("hand_top")            # RGB uint8 (480, 640, 3); cameras: side_view, front_view, hand_top, hand_bottom, hand_side_inter, hand_side_exter, plam_lookat
s.render_video(actions, "/app/output/check.mp4", cameras=["hand_top"])
```
There are no motion primitives: every skill is yours to build from actuator commands.

CLI equivalent of the grader:
`python /opt/tools/rcb_myosuite.py replay --instance /app/instance.npz --traj /app/output/trajectory.npz --repeat 2`

## Conventions
- Action: 39 real numbers per control step, one per actuator in order: 39 muscles. A muscle's command a maps to its excitation u = 1 / (1 + exp(-5 (a - 0.5))) and is not clipped (a = -1: u ~ 0.0006, a = 0.5: 0.5, a = 1: 0.92, a = 2: 0.9994); activation follows excitation with a first-order delay (~10 ms up, ~40 ms down); muscles only pull; one muscle can cross several joints; its force also depends on its length and velocity.
- Control step 20 ms (10 physics substeps). There is no step budget: your wall-clock time is the limit
  (~1700 control steps/s here). An episode ends at success or failure; `s.step` then refuses further
  actions until `s.reset()`.
