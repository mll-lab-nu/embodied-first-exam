# Reference solution for one_leg: the scripted demonstration policy, recorded through the Session.
# Run by `rcb_tactilelab.py run-oracle`, which provides `s` (a Session on the frozen instance); leaves its rows in `actions`.
import numpy as np
import tactilelab_tasks

spec = tactilelab_tasks.TASKS["one_leg"]
# the Session has just reset the scene: record the first episode of the process (it is what a fresh replay reproduces)
policy = spec.policy_cls(s.cfg, s.task)
obs, info = s.obs, s.task.info()
policy.reset(obs, info)
s.record_start()
for t in range(25000):
    act, phase, done = policy.act(obs, info, t)
    if done:
        break
    gap = np.full(2, np.nan) if act.gripper_gap is None else np.asarray(act.gripper_gap, dtype=np.float64)
    s.step(
        np.concatenate([np.asarray(act.ee_target, dtype=np.float64), np.asarray(act.gripper, dtype=np.float64), gap])
    )
    obs, info = s.obs, s.task.info()
actions = s.record_stop()
