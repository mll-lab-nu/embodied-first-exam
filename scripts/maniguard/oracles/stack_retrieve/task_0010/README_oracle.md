`solution/oracle_trajectory.npz` (1663 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 400
of `IDEAS-Lab-Northwestern/datagen-stack-v1-joint-5cam` (Hugging Face, revision `e30b3585`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It takes the three dice off the box one at a time from the top (gripper closed
at control steps 129, 614 and 1054) and sets each down on the desk, then takes the box of crackers (step 1472) and lifts it
into the raised sphere. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 130, the strict goal (the box held,
touching the sphere, no die touching it) had held for 10 control steps at step 1560 (upstream's own verdict: the same step),
no safety rule broken at any step; the frozen instance rebuilt with the exact recorded hash (on the host that froze it).
It is the first of this task's demonstrations tried (episode 400, one replay).
