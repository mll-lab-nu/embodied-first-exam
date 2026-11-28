# AutoBio · thermal_mixer (standard)

| | |
|---|---|
| Task ID | `autobio-thermal-mixer-i00-standard` |
| Benchmark | [AutoBio](https://github.com/autobio-bench/AutoBio) (Lan et al., 2025), upstream `autobio-bench/AutoBio@0850421` |
| Robot | Universal Robots UR5e arm with a Robotiq 2F-85 gripper |
| Mode | standard |
| Instance | `thermal_mixer`, seed 0 |
| Time limit | 1 h |
| Reference solution | Included |

## Task
Set the thermal mixer to time 30 s, temperature 33 °C, mixing speed 600 rpm, with the buttons on its front panel.

## Success criteria
At the last control step, the thermal mixer's panel settings (set time, set temperature, mixing speed) all equal the
target settings named in the Task section. The panel starts at 60 s, 25 °C and 900 rpm. AutoBio's check is a score in
[0, 1] (0.5 × temperature + 0.3 × time + 0.2 × speed, each the fraction of the way from the start setting to the
target); success needs a score of 1.

The graded episode is the one live episode, as it ran; nothing is replayed to grade it. There is no reset. AutoBio's
`check()` is evaluated after every control step of 2 ms, and the condition above is judged on the state at the last
executed control step. The episode ends when the agent sends `/finish` (the action type `done` is the same), when the
agent's session ends (at the latest after 1 h), or after 600,000 control steps (1200 s of simulated time).
Meeting the condition earlier does not end the episode, and the service never reports success while it runs.

A MuJoCo physics warning (an unstable state) ends the episode at once as a failure, also after the condition was met;
the renderer's own warning (`VGEOMFULL`) does not count. An episode that ends in a simulator error scores 0. A live
episode that did not start in the instance's recorded state, and a service that never wrote its record, are
infrastructure failures, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 4 | 12 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 4 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## License
AutoBio ([autobio-bench/AutoBio](https://github.com/autobio-bench/AutoBio) @ `0850421`) states **no licence** for its
code or its own assets (the digitized instruments, tubes, racks and pipette, and two binaries without source: the
thread and detent MuJoCo plugins `libmjlab.so.3.3.0` and the liquid-surface solver `meshplane.so`). No file of AutoBio
is in this repository, and the simulator image is built locally and never published; it is used here for research
evaluation only. The robot models AutoBio bundles keep their own licences: UR5e and Robotiq 2F-85 (BSD), ALOHA 2
(BSD), DexHand021 (Apache-2.0); the display font is under the SIL OFL. The simulator is MuJoCo 3.3.0 (Apache License
2.0). Details: `images/autobio/BUILD_ONLY`.
