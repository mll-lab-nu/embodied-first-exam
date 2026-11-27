# HumanCLAW · sit on the toilet, i66 (standard)

| | |
|---|---|
| Task ID | `humanclaw-sit-toilet-i66-standard` |
| Benchmark | [HumanCLAW](https://github.com/Human-CLAW/HumanCLAW) (Siyao et al., 2026), upstream `Human-CLAW/HumanCLAW@fe3d376` |
| Robot | SMPL-X neutral human body, moved by HumanCLAW's MotionDiT whole-body motion skills (no arm or gripper control) |
| Mode | standard |
| Instance | `sit-toilet`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Sit down on any toilet in the house, and stop while you are still sitting on it.

## Success criteria
Success rule (HumanCLAW's InteractSR), all three:
- the episode ends with a stop;
- the episode contains at least one sit action;
- on the last physics frame of the last motion before the stop, the body's pelvis touches the mesh of a toilet
  that the episode lists as a target.
Ending without a stop fails. The episode allows 100 actions, the stop included; each action other than the stop is
one 0.5 s motion skill.

Graded: the live episode, judged by the simulator service with HumanCLAW's own metric code; nothing is replayed. The
episode ends at the agent's stop action or `/finish` (the same thing: `/finish` runs the stop as the episode's last
action), or when the agent's time (1 h) runs out, in which case the stop is run first and the episode is then
judged. The 100th action ends the episode whatever it is; if it is not a stop, the episode fails. Holding still
(`hold`) uses no action. No success signal is shown. No reset: the one episode is graded. A simulator error raised by
the agent's own call ends the episode with 0. A frozen start that does not rebuild, or a service crash outside the
agent's calls, is an infrastructure failure, not a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 3 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 8 | 6 GiB | 1024 | 5 GiB | — |
| verifier (as `main`) | 4 | 3 GiB | no cap | no GPU | 10 GiB |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: an NVIDIA GPU of compute capability 8.0-9.0 with EGL (RTX 4090 / L40S / L4).

## License
HumanCLAW's code ([Human-CLAW/HumanCLAW](https://github.com/Human-CLAW/HumanCLAW), the source snapshot `fe3d376`) is
released under the Apache License 2.0. Habitat-Sim and its Half-Physics patch: MIT License; Bullet: zlib License.
**Non-commercial terms apply** to the data in the private image this task runs on, which may be used but not
redistributed: the HSSD scenes (`hssd/hssd-hab`) and HumanCLAW's val41 supplement (`HumanCLAW/HumanCLAW-HSSD`) are
CC BY-NC 4.0 (gated, terms accepted per user on Hugging Face); the body model derives from SMPL-X / SMPL (model
licences: non-commercial research, no redistribution); the MotionDiT `paper_fullval_v1` weights were trained on AMASS /
BABEL (non-commercial research). The image is never published (`images/humanclaw/BUILD_ONLY`): each user builds it
under their own acceptance of these terms.
