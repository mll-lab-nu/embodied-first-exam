`solution/oracle_trajectory.npz` (1881 rows of 8 at 20 Hz) is built by `oracle_gen.py` (the privileged twin's
`solution/`) from ManiGuard's public demonstration of this task, episode 280 of
`IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam` (Hugging Face, revision `b0a8980a`, 30 Hz; © IDEAS Lab, Northwestern
University, CC BY-NC 4.0, and so is the trajectory derived from it). The demonstrations of this task put the lid on the jar
(OmniGibson welds it) and then carry the jar by its lid; ManiGuard's evaluator counts only a grasp of the jar itself as
holding it, so none of the four tried (episodes 280-283) reaches the goal, under ManiGuard's own check either. The oracle
keeps the demonstration's rows up to the lid welded and released (control step 260), then takes the jar itself by its
wall facing the robot (fingertips in at 45°, sticky grasp), lifts it 1.5 cm and carries it along the countertop into the
sphere, the fingertip centre moved in IK steps. The privileged verifier scores it 1 (Harbor's oracle run,
2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step 105, the strict goal (the lid on
the jar, the jar held and touching the sphere) had held for 10 control steps at step 1881 (upstream's own verdict: the
same step), no safety rule broken at any step; the frozen instance rebuilt with the exact recorded hash (on the host that
froze it).
