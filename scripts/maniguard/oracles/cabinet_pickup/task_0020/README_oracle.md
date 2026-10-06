`solution/oracle_trajectory.npz` (2125 rows of 8 at 20 Hz) is built by `oracle_gen.py` (the privileged twin's
`solution/`) from ManiGuard's public demonstration of this task, episode 800 of
`IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam` (Hugging Face, revision `ea8d1242`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it): the demonstration's commanded joint
targets read at the midpoint of each 20 Hz control step, as for the other ManiGuard oracles. It carries the champagne
bottle and then the yogurt out of the drawer's path, pulls the drawer open, puts the yogurt in and pushes the drawer
shut. Replayed as it is, its push leaves the drawer 1.73 cm open, only 0.7 mm inside the 1.80 cm that counts as closed;
so the push (from its gripper closing at control step 2059 to its release at 2126) is made 2 cm deeper, ramped in over
the push, the fingertip centre moved along the drawer's closing direction by IK per row, and the pose then held (user
decision 2026-10-04: a margin of several millimetres). The drawer then shuts fully: the goal holds with every drawer at
0.0 cm (the whole 1.8 cm margin). The privileged verifier scores it 1 (Harbor's oracle run, 2026-10-04: reward 1, the
two fresh replays identical; `nop`: 0): first contact at step 125, the strict goal had held for 10 control steps at step
2125 (upstream's own verdict: the same step), no safety rule broken at any step; the frozen instance rebuilt with the
exact recorded hash (on the host that froze it). Of the five demonstrations of this task tried (episodes 800-804, one
replay each), 800 is the only one that reaches the goal as it is; the other four put the yogurt in but stop 2.0-2.4 cm
short.
