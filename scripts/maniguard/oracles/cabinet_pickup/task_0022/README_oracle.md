`solution/oracle_trajectory.npz` (2344 rows of 8 at 20 Hz) is built by `oracle_gen.py` (the privileged twin's
`solution/`) from ManiGuard's public demonstration of this task, episode 882 of
`IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam` (Hugging Face, revision `ea8d1242`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it): the demonstration's commanded joint
targets read at the midpoint of each 20 Hz control step, as for the other ManiGuard oracles. It moves the glaze bottle
aside, pulls the drawer open, puts the bottle of cocoa in and pushes the drawer shut with closed fingers. Replayed as it
is, its push leaves the drawer 1.796 cm open, only 0.06 mm inside the 1.802 cm that counts as closed; so the push (from
its gripper closing at control step 2277 to its release at 2344) is made 2 cm deeper, ramped in over the push, the
fingertip centre moved along the drawer's closing direction by IK per row, and the pose then held (user decision
2026-10-04: a margin of several millimetres). The drawer then shuts fully: the goal holds with every drawer at 0.0 cm
(the whole 1.8 cm margin). PENDING Of the six demonstrations of this task tried (episodes 880-885, one replay each), 882
is the only one that reaches the goal as it is; the other five put the cocoa in but leave the drawer 2.2-17 cm open.
