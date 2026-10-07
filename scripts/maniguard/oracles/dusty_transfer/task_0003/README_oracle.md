`solution/oracle_trajectory.npz` (1018 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 122
of `IDEAS-Lab-Northwestern/datagen-dusty-v1-joint-5cam` (Hugging Face, revision `ac57d863`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It picks up the sponge, wipes the tupperware's bottom until the last dust
particle is gone (by control step 325), puts the sponge back on the desk, takes the tray by its edge, carries it over the
tupperware and tilts it until the potato slides in. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 110, the strict goal had held for
10 control steps at step 946 (upstream's own verdict: the same step), no safety rule broken at any step; the frozen
instance rebuilt with the exact recorded hash (on the host that froze it). Of the four demonstrations of this task tried
(episodes 120-123, one replay each), this one reaches the goal: in episode 120 the sponge, held off-centre, catches on the
tupperware's rim and never reaches the dust; in 121 and 123 the dust is wiped off but the potato does not end up inside.
ManiGuard's data generator builds each episode's scene anew (the demonstrations' first frames show the sponge turned and
the dust spread differently), so its demonstrations replay only approximately in the frozen scene.
