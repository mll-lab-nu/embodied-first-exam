`solution/oracle_trajectory.npz` (1623 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 320
of `IDEAS-Lab-Northwestern/datagen-stack-v1-joint-5cam` (Hugging Face, revision `e30b3585`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It takes the three cans off the toast one at a time from the top (gripper closed
at control steps 154, 596 and 970) and stands each one on the desk, then takes the toast (step 1415), lifts it a few
millimetres and brings it into the sphere. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 154, the strict goal (the toast
held, touching the sphere, no can touching it) had held for 10 control steps at step 1577 (upstream's own verdict: the same
step), no safety rule broken at any step; the frozen instance rebuilt with the exact recorded hash (on the host that froze
it). It is the first of this task's demonstrations tried (episode 320, one replay).
