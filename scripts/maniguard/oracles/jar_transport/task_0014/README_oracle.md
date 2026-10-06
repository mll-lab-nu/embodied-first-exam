`solution/oracle_trajectory.npz` (747 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 560
of `IDEAS-Lab-Northwestern/datagen-jar-v1-joint-5cam` (Hugging Face, revision `080dddb4`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. With the gripper open it pushes the lid shut, then closes the gripper on the
jar at control step 499 and carries the jar up into the sphere. The privileged verifier scores it 1 (Harbor's oracle
run, 2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 90, the strict goal had
held for 10 control steps at step 599 (upstream's own verdict: the same step), no safety rule broken at any step, also
before the first contact; the frozen instance rebuilt with the exact recorded hash (on the host that froze it). Two
other resamplings (each step's start; the reached joints) also reach the strict goal with no rule broken (steps 599 and
598, one replay each).
