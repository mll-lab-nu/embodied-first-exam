# autobio-thermal-mixer-i00-privileged

| | |
|---|---|
| Benchmark | AutoBio |
| Mode | privileged |
| Twin | `autobio-thermal-mixer-i00-standard` |
| Simulator / robot | `autobio` / `ur5e-robotiq-2f85` |
| Family / instance | `thermal_mixer` / seed 0 |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe-private:autobio-0.1.0` |

## Task
AutoBio's `thermal_mixer` (Operate thermal mixer panel), with a UR5e arm (6 joints) with a Robotiq 2F-85 gripper, fixed to the bench: Set the thermal mixer by pressing the buttons of its panel: time 30 s, temperature 33 °C, mixing speed 600 rpm. It starts at 60 s, 25 °C and 900 rpm. The episode is judged in the state in which your trajectory ends: success iff the panel is then set to exactly these three values. AutoBio's score for the task (reported as `progress`) is 0.5 x temperature + 0.3 x time + 0.2 x speed, each term the fraction of the way from the initial to the target value.
On the bench: a thermal mixer (an Eppendorf ThermoMixer C model) with a thermoblock on top and a front panel: a display and buttons for time, temperature and speed (up and down each), menu navigation, five program keys, `short` and `start/stop`. The deliverable is one replayable trajectory of joint position targets (`/app/output/trajectory.npz`, `(T, 7)`, one row per 2 ms control step).

## Difficulty
AutoBio's level: hard. Three settings are changed by pressing small panel buttons with the gripper, the right number of times each; the final panel state is what counts, so an overshoot has to be corrected. The agent has full access to the simulator and to AutoBio's task code, but not to its scripted expert: it has to build the motion itself from joint position targets at the physics rate.

## Reference solution
AutoBio's scripted expert (mani_thermal_mixer.py @ 0850421), seed 0: the position targets it sends, recorded at every physics step, clipped to the actuators' ranges, rounded to float32 (so the standard twin's client executes the same rows): `solution/oracle.npz`, 8094 rows, success after 8094 control steps. Replayed and saved by `solution/solve.sh`; re-checked by the privileged verifier (`harbor run -a oracle`: two fresh-process replays, same final state).

## Verification
`tests/grade.py` in a separate sandbox without network: one replay of `/app/output/trajectory.npz`, in a fresh process, from the verifier's own copy of the instance (`tests/instance.json`; the compiled model and the rebuilt start state are checked against its recorded hashes); pass iff the episode succeeds (the episode is judged in the state in which it ends, success iff AutoBio's score is 1). `nop`: no trajectory, reward 0.

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
| Instance | `ThermalMixerManipulate` (`mani_thermal_mixer.py`) after AutoBio's `reset(seed=0)`; model hash `9ad959e8120cbbea`, start-state hash `40d5857ebf38fb99`, checked on every load |
| Actions | 7 position targets per control step (2 ms, one physics step); success rule `final` (tasks/autobio/README.md) |
| Resources | 4 CPUs, no GPU (CPU physics, OSMesa rendering) |
