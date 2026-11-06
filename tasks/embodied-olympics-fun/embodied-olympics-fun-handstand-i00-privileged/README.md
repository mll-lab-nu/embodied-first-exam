# embodied-olympics-fun-handstand-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-handstand-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `handstand` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection of the way up (the tuck placed by a state write at 0.2 s) and of the way down (the robot put standing); the unfold, the 2 s hold and the fold are the robot's own lowcmd control: an LQR (finite-difference linearisation of the 10 ms step, 29 joint-target inputs) about 7 IK equilibria on the fists, scheduled tuck to straight, holds the straight handstand at least 2 s and folds back (it survives 1.5 rad/s pushes in the tuck); negatives: nop, a tuck balance, a 1.5 s hold, a fall after the hold, a headstand, outside the area. A searched tuck jump from the crouch reached a 2 s LQR-held tuck once in 448 trials but did not reproduce; snap-down exits landed in a pike or crouch, but the rise to standing was a knife edge; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Do a handstand: from your stance get up onto your hands, hold the handstand still for 2 s with only your hands on the floor, then come back down onto your feet and stand. (Embodied Olympics `handstand`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
Your whole 33 kg rests on two small fists and arms whose shoulders give 25 N m: the body has to be balanced over a support a few centimetres long, actively, as an inverted pendulum, and no built-in action does that. Getting from standing onto the hands, and from the hands back onto the feet, are as hard as the hold.

## Reference solution
None. No reference controller exists for this family yet: positive by injection of the way up (the tuck placed by a state write at 0.2 s) and of the way down (the robot put standing); the unfold, the 2 s hold and the fold are the robot's own lowcmd control: an LQR (finite-difference linearisation of the 10 ms step, 29 joint-target inputs) about 7 IK equilibria on the fists, scheduled tuck to straight, holds the straight handstand at least 2 s and folds back (it survives 1.5 rad/s pushes in the tuck); negatives: nop, a tuck balance, a 1.5 s hold, a fall after the hold, a headstand, outside the area. A searched tuck jump from the crouch reached a 2 s LQR-held tuck once in 448 trials but did not reproduce; snap-down exits landed in a pike or crouch, but the rise to standing was a knife edge.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: A handstand is: only your hands on the floor (nothing else of you touches it), your pelvis above your hands and your ankles above your pelvis, and both lines of your body, from the middle of where your hands touch the floor to your pelvis and from your pelvis to the middle of your ankles, within 45.0 degrees of vertical (the Code of Points does not recognise a handstand that deviates more), and your body extended: your knees bent at most 20.0 degrees (the knee joints' angle, 0 is straight) and your hips bent at most 25.0 degrees (the angle, towards your front, between the line from the middle of your shoulder joints to the middle of your hip joints and the line from each hip joint to its knee joint); a tucked or piked balance is not a handstand. Any part of your hand counts as the hand (you have fists, not fingers). The handstand is held while you stay in it with your pelvis slower than 0.15 m/s (a complete stop); it counts once it has been held without a break for 2.0 s. After that you come back down so that only your feet touch the floor (your hands off it), and then you stand for 1.0 s without a break: only your feet on the floor, your torso within 20.0 degrees of vertical, your pelvis slower than 0.35 m/s. You fail if any part of you other than your hands and feet touches the floor, or your pelvis is lower than 0.25 m (a fall); if any part of you touches the floor outside the 12.0 m x 12.0 m floor area (its lines are inside); or after 30 s. Your feet may leave the floor in a jump; nothing limits how you get onto your hands or back to your feet. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | FIG Men's Artistic Gymnastics Code of Points 2025-2028: floor exercise, element I.19 'Handstand (2 s.)' (EG I, non-acrobatic elements); Art. 9.2.15 (a hold element is held at least 2 s, measured from the moment a complete stop has been reached; no stop is not recognised); Art. 9.2.13 (a handstand deviating more than 45 degrees from the vertical is not recognised); Art. 10.1 (the floor area, 12 m x 12 m); Art. 10.2.1.2a (the exercise inside the floor area, the lines included); deviations: FIG Apparatus Norms, floor: the floor is rigid and level (friction 1.0), not the norm's sprung floor with its elastic surface, because the simulator's ground is rigid and no sourced stiffness of the sprung floor is used here (a sprung floor would give energy back at the jump into the handstand: this is not easier) · Art. 10.1 / I.19 (a handstand on the hands): the G1 has no fingers and no palm that opens; each hand is a rigid rubber fist (a 4.4 x 8 x 10 cm pad on the wrist). Any part of the hand (the pad, the wrist's housing) may bear the weight: a knuckle (fist) handstand counts as a handstand · Art. 9.2.13 (deviation from the perfect handstand): judged pass or fail with the Code's non-recognition limit of 45.0 degrees, on two lines of the body: from the middle of the hands' support to the pelvis and from the pelvis to the middle of the ankles; the 15 and 30 degree execution deductions are not applied, as there is no E-Jury · Art. 9.2.13 / I.19 (the handstand's shape: a straight body, legs together and extended): the Code treats bent legs and a bent body as execution faults and sets no number for when a balance stops being a handstand; here, judged pass or fail, the knees (the knee joints' angle, 0 = straight) may bend at most 20.0 degrees and the hips at most 25.0 degrees (the angle, measured towards the front, between the line from the middle of the shoulder joints to the middle of the hip joints and each line from a hip joint to its knee joint), during the whole hold; both limits lie in the medium band (15-30 degrees) of the Code's angle-fault scale, so a slightly bent handstand counts (its deductions are not applied) and a tucked or piked balance does not · Art. 9.2.15 (a complete stop): without judges a stop is the pelvis slower than 0.15 m/s · Art. 10.2.1.1 (the exercise begins from a still stand, legs together): the robot starts in its own stance, feet 0.24 m apart, because that is how it stands; the task is one element and the way back to the feet, not a 70 s exercise |
| Stages | handstand → held 2 s → on the feet → stand |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c8d29ee33f2939a5acf56585b50eebf9089c168dcbdc17696329544828a15475` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
