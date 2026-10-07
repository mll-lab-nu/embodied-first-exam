`solution/oracle_trajectory.npz` (687 rows of 8 at 20 Hz) is built by `oracle_gen.py` (the privileged twin's `solution/`)
from ManiGuard's public demonstration of this task, episode 640 of `IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam`
(Hugging Face, revision `b0a8980a`, 30 Hz; © IDEAS Lab, Northwestern University, CC BY-NC 4.0, and so is the trajectory
derived from it). Replayed as they are (resampled to 20 Hz like the other ManiGuard oracles), none of the four
demonstrations tried (episodes 640-643) keeps the cap on: each sets it down a little high and tilted, OmniGibson never
welds it to the jug (AttachedTo needs the cap's attachment point within 5 cm and 15° of the jug's when they touch), and
the cap falls off when the jug is lifted; ManiGuard's own evaluator counts all four as successes (the jug held in the
sphere from steps 481-522), the strict goal counts none. The oracle keeps the demonstration's rows up to the cap held over
the jug (control step 200), lowers the cap with its attachment point over the jug's (both poses read from the simulator)
until OmniGibson welds it, opens the gripper, lifts the hand 10 cm, returns over the demonstration's approach of the jug
(its row 320) from above and plays the demonstration's remaining rows: the jug taken by its handle and carried into the
sphere with the cap on. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical, the weld included; `nop`: 0): first contact at step 111, the
strict goal (the cap on the jug, the jug held and touching the sphere) had held for 10 control steps at step 687
(upstream's own verdict: the same step), no safety rule broken at any step; the frozen instance rebuilt with the exact
recorded hash (on the host that froze it).
