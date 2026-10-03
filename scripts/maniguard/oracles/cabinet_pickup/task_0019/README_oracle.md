`solution/oracle_trajectory.npz` (2291 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 767
of `IDEAS-Lab-Northwestern/datagen-cabinet-v1-joint-5cam` (Hugging Face, revision `ea8d1242`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It carries the graduated cylinder and then the jar out of the drawer's path,
pulls the drawer open, puts the jar in and pushes the drawer shut. The privileged verifier scores it 1 (Harbor's oracle
run, 2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 97, the strict goal had
held for 10 control steps at step 2240 (upstream's own verdict: the same step), no safety rule broken at any step; the
frozen instance rebuilt with the exact recorded hash (on the host that froze it). The drawer ends about 1.2 cm open,
inside the 1.8 cm that counts as closed. Of the eight demonstrations of this task tried (episodes 760-767, one replay
each), four reach the strict goal with no rule broken; the other four leave the drawer 1.9-2.7 cm open.
