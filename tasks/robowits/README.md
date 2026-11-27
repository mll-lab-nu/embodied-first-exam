# RoboWits

## Overview
Fifteen seed tasks of [RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits), physical-reasoning puzzles for a
bimanual Marvin robot (two 7-DoF arms with Pika parallel grippers) on Genesis 0.4.7. Each family is one RoboWits seed
task with one success predicate. Each family is one frozen evaluation scene in two modes: 30 task directories
`tasks/robowits/robowits-<family>-i00-{privileged,standard}`.

```bash
harbor run -d embodied-first-exam@all -p tasks/robowits -a codex -m <model>
```

| | |
|---|---|
| upstream | [UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ `9cc30ae` (MIT), on Genesis 0.4.7 |
| image | `ghcr.io/mll-lab-nu/efe:robowits-0.1.1` (`images/robowits/`, public), plus the BlenderKit models for 12 of the 15 families (below) |
| GPU | any NVIDIA GPU with EGL: it renders the three cameras; the physics runs on Genesis' CPU backend |
| metadata | `simulator = "robowits"`, `robot = "marvin-bimanual"`, `family = "<family>"` |
| time limit | 3600 s for every task and mode (`[agent] timeout_sec`) |

The time limit is the same in both modes. The families are bimanual physical puzzles that take several attempts.
Every Python process pays about a minute of scene build before its first step. In standard mode a crash resume
replays the episode on the agent's clock.

**BlenderKit models.** dominos, stand_pages and stack_cubes run from the image alone. The other 12 families also load
BlenderKit models, which may not be redistributed (`images/robowits/NOTICE`). They go in a host folder named by
`RCB_ROBOWITS_BLENDERKIT`. Get them one of two ways:

```bash
# a) the encrypted research bundle: log in at https://huggingface.co/datasets/eai-v2-internal/robowits-blenderkit-encrypted
#    and accept its terms, then
pip install -U huggingface_hub && hf auth login
images/robowits/fetch_blenderkit_encrypted.sh ~/robowits-blenderkit
# b) or with your own BlenderKit Full Plan key (BLENDERKIT_API_KEY=<key> in ../.env next to the repository)
images/robowits/fetch_blenderkit.sh ~/robowits-blenderkit

export RCB_ROBOWITS_BLENDERKIT=~/robowits-blenderkit
```

Both scripts check every file against the checksums of the files the instances were frozen with
(`images/robowits/blenderkit.sha256`, `blenderkit_encrypted.sha256`).

The per-task READMEs are rendered from `tasks/robowits/readme.toml`. It holds the benchmark facts, the license and
each family's success rule, with the source lines each rule was read from.

## Upstream and license
RoboWits ([UMass-Embodied-AGI/RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) at
`9cc30aedbbebea86b975c0d66ea9ac227ca38535`, `images/robowits/Dockerfile`) is MIT-licensed, as declared in its
`pyproject.toml`; the repository ships no LICENSE file. Paper: Lin et al., 2026 (arXiv:2605.30326). Genesis 0.4.7 and
the rest of RoboWits' locked Python stack are under their own licences (Genesis: Apache-2.0). RoboWits' HuggingFace
asset bundle `XHRlyb2001/RoboWits_assets` is Apache-2.0. The image's base is `nvidia/cuda:12.9.1-base-ubuntu22.04`
(NVIDIA Deep Learning Container License).

**BlenderKit models: not redistributable; the bundle is non-commercial.** 127 BlenderKit models belong to RoboWits'
seed tasks (BlenderKit's Royalty Free license or CC0). BlenderKit licenses each model to the account that downloads
it, and its terms forbid distributing the models apart from a project. So the image, this repository and the
published results never carry them in usable form; replay videos are renders. The encrypted bundle is the only copy
distributed. Its terms: **non-commercial academic research only**, used through this benchmark's tooling only; no
other decryption, extraction or conversion; no sharing or re-upload of the files or the key. The models stay their
authors' (`ATTRIBUTION.csv` in the bundle).

## Changes from upstream
- **Physics: none.** The scenes, objects, robot and predicates (`_check_success`) are RoboWits' at the pinned
  commit, on Genesis' CPU backend (bit-exact within one CPU vendor). Control runs at 30 Hz with 4 physics substeps;
  the action is RoboWits' JOINT_ABS layout: per arm 7 joint targets and a gripper width.
- **Frozen instances.** Each family's scene is entry 0 of RoboWits' `eval_dataset_50/<NN>.json`. It is frozen in
  `instance.json`: the object poses, Genesis' convex decompositions and particle caches, the reset joint targets and
  the expected state hash, checked on every build. stand_bulb's dataset scene is simulated on until its ring and tall
  object are at rest. Its dataset entry has the two overlapping, so after RoboWits' 10 settle steps they still moved.
  Every family except stand_bulb also allows seeds 1 and 2: entries 1 and 2, each a committed instance under the
  privileged task's `tests/seeds/<seed>/`.
- **Success checks.** RoboWits' predicates are instantaneous, and most have no release or speed term. Here the
  verdict is a settle window after the episode or trajectory ends (`rcb_robowits.Session.settle_check`):
  - the robot holds its last command for 1 s (30 control steps), and nothing is checked;
  - for 2 s more (60 control steps), the goal must hold at every 6th step and at the last one;
  - each graded object must stay within 2 mm of where it was when those 2 s began.

  The goal is RoboWits' predicate, unchanged, plus:
  - no part of the robot touches the family's graded objects (Genesis' contact list); stand_pages also counts the
    bar;
  - for move_cube, the cube past the line still on the table (its bounding box's bottom no more than 2 cm below the
    table top).
- **Tooling: thin wrappers only.** The privileged tooling gives the frozen instance, the privileged state,
  recording and replay, rendering, and thin wrappers of the low-level action: joint moves, IK moves without collision
  checking, gripper and hold. It adds no task-level skill (grasp, place).
- **Not in the image.** The BlenderKit models (Upstream and license). RoboWits' published human demonstrations of
  its seed tasks are not downloaded; the agents' network allowlist makes them unreachable.

## Interface
- **Privileged.** `/opt/tools/rcb_robowits.py` (`Session`): the frozen scene, unlimited exact resets, object poses,
  thin primitives, rendering (`render_frame`, `render_depth`, `render_video`), recording and `replay`, which runs
  exactly what the verifier runs. The deliverable is `/app/output/trajectory.npz`, (T, 16) JOINT_ABS rows, one per
  1/30 s control step. A `Session` has at most 200,000 control steps between resets, a runaway guard; the wall clock
  is the budget. The privileged agent's container never sees the BlenderKit folder or the bundle's key. The task's
  `blenderkit` service mounts it, decrypts this family's models alone and serves them on `localhost:8765`. The
  tooling fetches them for each scene build into a private tmpfs folder and deletes them afterwards.
- **Standard** (`eai-standard/3.0`). The simulator runs in a `sim` sidecar, which mounts the BlenderKit folder
  read-only. Its interface:
  - actions: `joint_position` (16, streamed at the 30 Hz control rate) and `ee_pose` (16, right arm first, gripper-tip
    frame, solved per row by RoboWits' pink/pinocchio IK);
  - cameras: `ego` (static) and `wrist_right` / `wrist_left` (link-mounted, so every frame carries its pose), with
    Genesis rasterizer z-depth;
  - `/kinematics` on pinocchio (14 arm joints) and 80 proprio columns;
  - at most 1500 images per call.

  The service waits up to `RCB_STARTUP_TIMEOUT_S` = 900 s for its scene build, at least twice the slowest build
  measured (47–234 s). Crash recovery resumes the same episode, with resume class `exact`.
- **World-frame information.** Standard tasks never say where things are in the world
  (`ci_checks/check-world-frame-texts.sh`). They give no object poses or positions, and no world
  coordinates of workspace items. Their success criterion is stated in words and in distances relative to the objects
  and the table top. The predicates' table rectangle and the goal line's coordinate are withheld. Standard tasks do
  give: object names, sizes and colours; the robot, its base pose included; the cameras' calibration; and the world
  frame's convention. Privileged tasks give the privileged state through the tooling, and their criterion gives world
  coordinates.

## Grading
- **Privileged.** The verifier, without network, replays the trajectory once in a fresh process from its own copy
  of the frozen instance and runs the settle window after the last row. It scores 1 if the window passes and the
  rebuilt scene matches the frozen instance. A match means the exact state hash, or every object and joint pose
  within tolerance. The video is rendered after the verdict and never changes it.
- **Standard.** The service grades the live episode. The episode ends at `/finish` or at the end of the agent's
  session. The settle window then runs on the live simulator from the state it ends in, and its steps are part of the
  recorded episode. At the 200,000-step cap the goal is judged as it stands, with no window. A simulator error scores
  0. Nothing is replayed; the recorded rows are rendered once into `replay.mp4` after the verdict.
- **Whose failure.** The agent's (score 0):
  - no trajectory, or a file that is not the tooling's `.npz` with finite (T, 16) `actions`, T ≤ 200,000;
  - another family's file;
  - a window that fails;
  - in standard mode, a simulator error.

  The infrastructure's (`infra_error = 1`, not a result):
  - a host that cannot build or rebuild the frozen instance (Others, "Hosts: one CPU vendor");
  - a standard service that gave up after crashes it caused, or never wrote the live verdict.
- Both verifiers run with `network_mode = "no-network"`. Every asset is in the image or the mounted BlenderKit
  folder, and Genesis' caches are seeded from `instance.json`.

## Tasks
| family | RoboWits task | BlenderKit models | reference solution |
|---|---|---|---|
| align_blocks | `01-align-blocks-v0` | yes | none |
| ball_into_bottle | `12-ball-into-bottle-v0` | yes | none |
| ball_onto_tower | `17-ball-onto-tower-v0` | yes | none |
| collect_screws | `10-collect-screws-v0` | yes | none |
| cover_with_lid | `13-cover-with-lid-v0` | yes | none |
| dominos | `06-dominos-v0` | no | partial |
| gap_retrieve | `03-gap-retrieve-v0` | yes | none |
| hold_cup | `09-hold-cup-v0` | yes | none |
| move_cube | `28-move-cube-v0` | yes | none |
| raise_platform | `24-raise-platform-v0` | yes | none |
| retrieve_cube | `02-retrieve-cube-v0` | yes | none |
| stack_bowls | `19-stack-bowls-v0` | yes | none |
| stack_cubes | `14-stack-cubes-v0` | no | partial |
| stand_bulb | `16-stand-bulb-v0` | yes | none |
| stand_pages | `07-stand-pages-v0` | no | none |

- RoboWits ships no expert or planner. dominos and stack_cubes have a written reference solution (`solution/`,
  `oracle = "partial"`); the other families have none (`oracle = "none"`).
- The frozen instance is `environment/instance.json` of each privileged task, with copies in `tests/` and in the
  standard task's `environment/sim/`. ball_into_bottle's is 2.05 MB, almost all of it the frozen Genesis convex
  decomposition of its meshes.
- No task directory carries the tooling. The task Dockerfiles copy it from the files image `robowits-files`
  (`images/robowits-files/FILES.json`, sources in `embodied_first_exam/benchmarks/robowits/`):
  - `privileged/tests/rcb_robowits.py`, the tooling, at `/opt/tools/`, `/tests/` and `/srv/`;
  - `privileged/tests/grade.py`, the privileged grader;
  - `sim/server.py`, the standard service, at `/srv/server.py`;
  - `standard/tests/grade.py`, the standard grader.

  The shared standard layer comes from `standard-files` (`embodied_first_exam/standard/`).

## Others
- **Hosts: one CPU vendor.** Genesis' CPU backend is bit-exact only within one CPU vendor. The default instances were
  frozen on Intel, the other seeds' instances on AMD. On a host of the other vendor, the rebuilt instance's state hash
  differs. The tolerance check still accepts it: every object within 2 mm and 0.02 in quaternion, every joint within
  0.002 rad. A trajectory recorded on one vendor can still fail on the other. A task bound to one vendor would carry
  `host_cpu_vendor = "GenuineIntel"` in `[metadata]`; no task here needs it.
  - Privileged: a host that cannot rebuild the instance gives `success = 0`, `instance_ok = 0` and
    `infra_error = 1`. A scene that does not build at all also gives `instance_build_failed = 1` and
    `grader_error = 1`.
  - Standard: the service checks the rebuilt instance once, at its first start. On a mismatch it gives up before
    serving the agent: `final.json` reason `instance_mismatch`, `infra_error = 1`.
- ball_into_bottle: the red bottle's base collides as a thin shell (about 3.5 mm). A ball that falls fast down the
  bottle can pass through it onto the table. A thicker base would change the frozen scene.
- A JSON `/submit` body whose `actions` is an object fails in the shared layer before the adapter sees it (500; the
  episode ends). So does an RCB1 header with no `actions` part whose `meta` is not an object. The official client
  always sends an RCB1 `actions` array.
