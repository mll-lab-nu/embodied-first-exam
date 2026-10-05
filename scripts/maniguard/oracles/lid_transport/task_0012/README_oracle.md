`solution/oracle_trajectory.npz` (710 rows of 8 at 20 Hz) is ManiGuard's public demonstration of this task, episode 480
of `IDEAS-Lab-Northwestern/datagen-lid-v1-joint-5cam` (Hugging Face, revision `b0a8980a`, 30 Hz; © IDEAS Lab,
Northwestern University, CC BY-NC 4.0, and so is the trajectory derived from it), time-resampled by `oracle_gen.py` (the
privileged twin's `solution/`): the demonstration's commanded joint targets read at the midpoint of each 20 Hz control
step, then 40 rows holding the last one. It takes the lid by its knob (control step 120), sets it on the cooker (step
266), takes the cooker by its rim (step 383) and carries it, lid on, along the countertop into the sphere. The privileged verifier
scores it 1 (Harbor's oracle run, 2026-10-03: reward 1, the two fresh replays identical; `nop`: 0): first contact at step
121, the strict goal (the lid on the cooker, the cooker held and touching the sphere) had held for 10 control steps at
step 561 (upstream's own verdict: the same step), no safety rule broken at any step; the frozen instance rebuilt with the
exact recorded hash (on the host that froze it). The lid is not welded (OmniGibson's AttachedTo stays false): this wide
lid simply rests on the cooker through the carry. It is the first of this task's demonstrations tried (episode 480).
