# HumanCLAW · go to the TV, i139 (privileged)

| | |
|---|---|
| Task ID | `humanclaw-nav-tv-i139-privileged` |
| Benchmark | [HumanCLAW](https://github.com/Human-CLAW/HumanCLAW) (Siyao et al., 2026), upstream `Human-CLAW/HumanCLAW@fe3d376` |
| Robot | SMPL-X neutral human body, moved by HumanCLAW's MotionDiT whole-body motion skills (no arm or gripper control) |
| Mode | privileged |
| Instance | `nav-tv`, seed 0 |
| Time limit | 1 h |
| Reference solution | None |

## Task
Walk up to any TV in the house and stop right next to it, about a hand's length away or closer.

## Success criteria
Success rule (HumanCLAW's NavSR@20cm): the episode ends with a stop, and at that moment the shortest distance from
the body to the bounding box of any TV in the house that the episode lists as a target is at most 0.2 m.
Ending without a stop fails, wherever the body is. The episode allows 100 actions, the stop included; each action
other than the stop is one 0.5 s motion skill.

Graded file: `/app/output/trajectory.npz` with `actions`, a numeric array of 1 to 100 rows `[action_id, value]`, as
`Env.save()` writes it. After the agent's session it is replayed once from the frozen start, in a fresh process of a
separate verifier container without network, on the same GPU model the agent ran on. The rows run in order until the
episode ends; rows after the end are not run. A trajectory whose actions end without a stop fails. A missing file, a
file that is not such an array, or an invalid row (an unknown action id, a walk distance other than 0.2, 0.4 or 0.6 m,
a turn or side step of 0) scores 0. A replay that crashes or times out, or a frozen start that does not rebuild with
its recorded hash, is reported as `grader_error` (infrastructure), not as a score.

## Resource requirements
Caps per container.

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 6 | 8 GiB | 1024 | 8 GiB | 10 GiB |
| verifier | 8 | 5 GiB | 1024 | 8 GiB | 10 GiB |

- GPU: any NVIDIA GPU, held by `main`.
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
