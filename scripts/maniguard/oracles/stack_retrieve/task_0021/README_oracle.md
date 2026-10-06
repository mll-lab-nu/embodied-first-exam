`solution/oracle_trajectory.npz` (1517 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 840
of `IDEAS-Lab-Northwestern/datagen-stack-v1-joint-5cam` (Hugging Face, revision `e30b3585`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It takes the three upper bottles off the tower one at a time (gripper closed at
control steps 168, 598 and 976) and stands each one on the table, then takes the bottom bottle (step 1305), lifts it over
and sets it down in the sphere, still held. The privileged verifier scores it 1 (Harbor's oracle run, 2026-10-03: reward
1, the two fresh replays identical; `nop`: 0): first contact at step 168, the strict goal (the bottle held, touching the
sphere, no other bottle touching it) had held for 10 control steps at step 1474 (upstream's own verdict: the same step),
no safety rule broken at any step; the frozen instance rebuilt with the exact recorded hash (on the host that froze it).
Of the four demonstrations of this task tried (episodes 840-843, one replay each), 840, 841 and 842 reach the strict goal
with no rule broken (steps 1474, 1462 and 1482); 843 reaches it too (step 1506) but tips a bottle past 30° before (step
1417), so it fails.
