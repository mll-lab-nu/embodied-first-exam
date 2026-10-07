`solution/oracle_trajectory.npz` (675 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 520
of `IDEAS-Lab-Northwestern/datagen-jar-v1-joint-5cam` (Hugging Face, revision `080dddb4`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. With the gripper open it pushes the lid over and shut (closed by control step
250), then closes the gripper on the jar at step 488 and lifts it into the sphere. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 88, the strict goal (the jar held,
touching the sphere, its lid closed) had held for 10 control steps at step 552 (upstream's own verdict, which does not ask
for the lid, at step 537), no safety rule broken at any step; the frozen instance rebuilt with the exact recorded hash (on
the host that froze it). It is the first of this task's demonstrations tried (episode 520, one replay).
