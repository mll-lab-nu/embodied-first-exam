# dextoolbench_screwdriver_long_screwdriver_spin_horizontal-limited

Limited-mode twin of `dextoolbench_screwdriver_long_screwdriver_spin_horizontal` (see its README): the same scene, instance and scoring, served as a robot service (`images/mujoco/limited/server_mj.py`, protocol rcb-limited/2.1, tooling `rcb_dtb`). The agent sees camera RGB-D and proprioception only.

| | |
|---|---|
| oracle | `solution/`: the unlimited oracle's recorded targets submitted through the client (one row per control step) |
| grading | the sidecar replays the recorded episode in a fresh simulator; `deterministic` = same final state as the live episode |
