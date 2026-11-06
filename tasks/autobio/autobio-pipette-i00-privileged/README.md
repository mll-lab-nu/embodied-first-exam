# autobio-pipette-i00-privileged

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | privileged |
| Twin | `autobio-pipette-i00-standard` |
| Simulator / robot | `autobio` / `ur5e-dexhand-2f85-bimanual` |
| Family / instance | `pipette` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `pipette` (Aspirate with pipette), with two UR5e arms fixed to the bench: `arm1` carries a dexterous hand that holds a pipette (its thumb presses the plunger); `arm2` has a Robotiq 2F-85 gripper: Aspirate from the 50 mL centrifuge tube with the pipette. AutoBio's test is a sequence: (1) with the plunger pressed (the thumb's target, action entry `arm1_dh_rh_thj3`, above 0.70 rad), the pipette tip is within 6.5 mm (horizontally) of the tube's axis and more than 5 mm below the liquid surface; (2) the plunger is released (the thumb's target below 0.45 rad) while the tip is still below the surface; (3) success at the first control step after (1) and (2) where the tip is more than 5 cm above the liquid surface. The tube holds 31.5 mL; the test is on positions and commands, and no liquid actually moves (AutoBio models the liquid's surface in the tube, not its transfer).
On the bench, between the arms: a rack with an open, part-filled 50 mL tube standing in it. AutoBio's prompt for this task: "one arm lifts centrifuge tube, the other aligns pipette tip and aspirates liquid"; the test itself does not ask for the tube to be lifted. The deliverable is one replayable trajectory of joint position targets (`/app/output/trajectory.npz`, `(T, 14)`, one row per 2 ms control step).

## Difficulty
AutoBio's level: medium. Two arms. The pipette tip has to enter a 50 mL tube within 6.5 mm of its axis and reach below the liquid surface, with the plunger pressed before and released there. The agent has full access to the simulator and to AutoBio's task code, but not to its scripted expert: it has to build the motion itself from joint position targets at the physics rate.

## Reference solution
AutoBio's scripted expert (mani_pipette.py @ 0850421), seed 0: the position targets it sends, recorded at every physics step, clipped to the actuators' ranges, rounded to float32 (so the standard twin's client executes the same rows), cut at the first success: `solution/oracle.npz`, 6973 rows, success after 6973 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: two fresh-process replays, same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the compiled model and the rebuilt start state are checked against its recorded hashes); pass iff the episode succeeds (the first control step at which AutoBio's check holds ends the episode in success). `nop`: no trajectory, reward 0.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 12 GiB | 8192 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Upstream | AutoBio (github.com/autobio-bench/AutoBio @ 0850421, no licence stated: the image is built locally, images/autobio/BUILD_ONLY) on MuJoCo 3.3.0 |
| Instance | `Pipette` (`mani_pipette.py`) after AutoBio's `reset(seed=0)`; model hash `40806bc5f581ca3e`, start-state hash `228ededc6af93404`, checked on every load |
| Actions | 14 position targets per control step (2 ms, one physics step); success rule `first` (tasks/autobio/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
