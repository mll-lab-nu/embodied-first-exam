`solution/oracle_trajectory.npz` (2180 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 800
of `IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam` (Hugging Face, revision `ea8d1242`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It carries the champagne bottle and then the yogurt out of the drawer's path,
pulls the drawer open, puts the yogurt in and pushes the drawer shut. The privileged verifier scores it 1 (Harbor's oracle run, 2026-10-03: reward
1, the two fresh replays identical; `nop`: 0): first contact at step 125, the strict goal had held for 10 control steps at
step 2130 (upstream's own verdict: the same step), no safety rule broken at any step; the frozen instance rebuilt with the
exact recorded hash (on the host that froze it). The drawer ends 1.73 cm open, 0.7 mm inside
the 1.80 cm that counts as closed (the replays are bit-identical, so the margin holds on the host that ran them). Of the
five demonstrations of this task tried (episodes 800-804, one replay each), this is the one that reaches the goal: the
other four put the yogurt in but leave the drawer 2.0-2.4 cm open.
