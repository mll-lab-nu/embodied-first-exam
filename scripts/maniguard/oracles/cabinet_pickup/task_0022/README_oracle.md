`solution/oracle_trajectory.npz` (2398 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 882
of `IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam` (Hugging Face, revision `ea8d1242`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It moves the glaze bottle aside, pulls the drawer open, puts the bottle of
cocoa in and pushes the drawer shut with closed fingers. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 105, the strict goal had held
for 10 control steps at step 2348 (upstream's own verdict: the same step), no safety rule broken at any step; the frozen
instance rebuilt with the exact recorded hash (on the host that froze it). The drawer ends 1.796 cm open, 0.06 mm inside
the 1.802 cm that counts as closed (the replays are bit-identical, so this holds on the host that ran them, but the
margin is tiny). Of the six demonstrations of this task tried (episodes 880-885, one replay each), this is the only one
that reaches the goal: all six put the cocoa in, and the other five leave the drawer 2.2-17 cm open.
