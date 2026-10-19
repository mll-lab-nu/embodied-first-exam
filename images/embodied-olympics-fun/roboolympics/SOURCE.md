# The RoboOlympics simulator files in this image

Copied unchanged from [RoboOlympics](https://github.com/CHIGUI0/roboolympics) (MIT, `LICENSE.roboolympics`; the
repository is private), commit `7df999b3f553063a9b6b7cc3130b77dbee7bb9c8` (branch `athletics-v3`; `bodies/` is the
robot library at revision g1-4 of its Unitree G1 and h1-4 of its Unitree H1-2):

| here | RoboOlympics | what |
|---|---|---|
| `bodies/{__init__,assembly,servo,limits,sources,selfcollision,trajopt}.py` | `bodies/` | the robot library: the one limit / servo path, self-collision pairs, jerk-limited trajectories |
| `bodies/control/{arbiter,kinematics}.py` | `bodies/control/` | the joint-group arbiter (walking policy, joint plans, handovers) and FK / IK |
| `bodies/hands/` | `bodies/hands/` | attachment fragments on the wrist mount |
| `bodies/unitree_g1/` | `bodies/unitree_g1/` without `meshes_25k/`, `tools/`, `policy/motion.pt` and the kick skill (`kick.py`: a task-level skill, which this benchmark's tooling does not offer; the arbiter's `kick()` answers "no kick skill") | the G1: `model.xml`, `meshes/`, `body.toml` (limits with sources, motor curves), `body.py`, Unitree's walking policy (`policy/motion.npz`), and the two optional walking policies with their weights and licences: FALCON (`falcon.py`, `policy/falcon_g1_29dof.npz`, `policy/LICENSE.falcon`) and AGILE (`agile.py`, `policy/agile_g1_velocity_height.npz`, `policy/LICENSE.agile`); the benchmark's `walk_falcon` / `walk_agile` action types step them (since image 0.2.0) |
| `bodies/unitree_h1/` | `bodies/unitree_h1/` without `meshes_25k/`, `meshes_fine/`, `tools/` | the Unitree H1-2 at revision h1-4: `model.xml`, `meshes/`, `body.toml`, `body.py`, Unitree's H1-2 walking policy (`policy/motion.npz`) |
| `athletics/run_policy.py`, `athletics/policy/` | `sports/athletics/` | the G1 running policy in numpy, its weights, licence and notice |

Third-party parts and their licences (each licence file is next to the files):
- Unitree G1 model and meshes: MuJoCo Menagerie `unitree_g1` @ `f054586a8e90465d49ee5be15335c4a0c7f57caf`, BSD-3-Clause
  (`bodies/unitree_g1/LICENSE`), modified by RoboOlympics (`tools/make_model.py` there lists every change).
- Unitree's pretrained G1 walking policy (`policy/motion.npz`): unitree_rl_gym @ `276801e46c5d433564f24658bac64f254b7d2d4b`,
  BSD-3-Clause (`policy/LICENSE.unitree_rl_gym`).
- Unitree H1-2 model, meshes and pretrained walking policy: unitree_rl_gym (`resources/robots/h1_2`, the `h1_2` deploy
  policy), BSD-3-Clause (`bodies/unitree_h1/LICENSE`, `bodies/unitree_h1/policy/LICENSE.unitree_rl_gym`), modified by
  RoboOlympics (`tools/make_model.py` there lists every change).
- FALCON's G1 policy (`policy/falcon_g1_29dof.npz`): the weights of LeCAR-Lab/FALCON's released `sim2real/models/falcon/g1_29dof.onnx`
  (FALCON @ a967a6d), exported unchanged by RoboOlympics' `tools/export_falcon.py`, MIT (`policy/LICENSE.falcon`, © 2025 Yuanhang Zhang).
- AGILE's G1 velocity-height policy (`policy/agile_g1_velocity_height.npz`): the weights and graph constants of nvidia-isaac/WBC-AGILE's
  released LEAPP bundle `Velocity-Height-G1-History-v0.onnx` (WBC-AGILE @ 6830cf9), exported unchanged by RoboOlympics'
  `tools/export_agile.py`, Apache-2.0 (`policy/LICENSE.agile`, © NVIDIA CORPORATION & AFFILIATES).
- The G1 running policy (`athletics/policy/g1_running.npz`): C1801SYQ/g1_running @
  `de56c7adeadfa1b639fda5332f57f32588133228`, Apache-2.0 (`athletics/policy/LICENSE.g1_running`, `NOTICE.md`).

`manifest.sha256` lists every file; the image build checks it. To update: copy the files again from a RoboOlympics
checkout, `find . -type f ! -name manifest.sha256 | sort | xargs sha256sum > manifest.sha256`, bump `../VERSION`.
