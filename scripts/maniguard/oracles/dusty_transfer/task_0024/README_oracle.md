`solution/oracle_trajectory.npz` (1028 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 962
of `IDEAS-Lab-Northwestern/datagen-dusty-v1-joint-5cam` (Hugging Face, revision `ac57d863`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It picks up the sponge, wipes the bowl until the last dust particle is gone (by
control step 300), puts the sponge back, takes the platter by its end, carries it over the bowl and tilts it until the
half blackberry drops in. The privileged verifier scores it 1 (Harbor's oracle run, 2026-10-03: reward 1, the two fresh
replays identical; `nop`: 0): first contact at step 110, the strict goal had held for 10 control steps at step 972
(upstream's own verdict: the same step), no safety rule broken at any step; the frozen instance rebuilt with the exact
recorded hash (on the host that froze it). Of the three demonstrations of this task tried (episodes 960-962, one replay
each), this is the one that reaches the goal: in 960 one dust particle is left and the berry rolls off onto the desk; in
961 the bowl is wiped clean but the berry stays on the tilted platter. ManiGuard's data generator builds each episode's
scene anew, so its demonstrations replay only approximately in the frozen scene.
