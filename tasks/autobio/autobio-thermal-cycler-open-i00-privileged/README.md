# autobio-thermal-cycler-open-i00-privileged

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | privileged |
| Twin | `autobio-thermal-cycler-open-i00-standard` |
| Simulator / robot | `autobio` / `ur5e-robotiq-2f85` |
| Family / instance | `thermal_cycler_open` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `thermal_cycler_open` (Open thermal cycler lid), with a UR5e arm (6 joints) with a Robotiq 2F-85 gripper, fixed to the bench: Open the lid of the thermal cycler. It starts closed and locked: the lid's hinge (`/thermal_cycler_biorad_c1000:lid`) at -1.9 rad and its lever (`/thermal_cycler_biorad_c1000:lid-lever`) at -0.94 rad. Success at the first control step where both are within 0.003 rad of 0 (fully open).
On the bench: a thermal cycler (a Bio-Rad C1000 model) with its lid closed and locked by the lever on the lid. The deliverable is one replayable trajectory of joint position targets (`/app/output/trajectory.npz`, `(T, 7)`, one row per 2 ms control step).

## Difficulty
AutoBio's level: easy. Two articulated parts have to come back to their open end stops within 0.003 rad: the lever that locks the lid, and the lid. The agent has full access to the simulator and to AutoBio's task code, but not to its scripted expert: it has to build the motion itself from joint position targets at the physics rate.

## Reference solution
AutoBio's scripted expert (mani_thermal_cycler.py @ 0850421), seed 0: the position targets it sends, recorded at every physics step, clipped to the actuators' ranges, rounded to float32 (so the standard twin's client executes the same rows), cut at the first success: `solution/oracle.npz`, 8251 rows, success after 8251 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: two fresh-process replays, same final state).

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
| Instance | `ThermalCyclerManipulate` (`mani_thermal_cycler.py`) after AutoBio's `reset(seed=0)`; model hash `67478954d8efa27b`, start-state hash `af233b90fd79689a`, checked on every load |
| Actions | 7 position targets per control step (2 ms, one physics step); success rule `first` (tasks/autobio/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
