# RoboWits

[RoboWits](https://github.com/UMass-Embodied-AGI/RoboWits) @ 9cc30ae on Genesis 0.4.7: physical-reasoning puzzles for the
bimanual Marvin robot. `simulator = "robowits"`, `robot = "marvin-bimanual"`. 29 families, each as a privileged task
`robowits-<family>-i00-privileged` and its standard twin `robowits-<family>-i00-standard`, on the same frozen evaluation scene.

## Tasks and generators
- Template tasks: `tasks/robowits-stack-cubes-i00-privileged` and its standard twin. A new family = a copy of the template:
  `scripts/robowits_mk_task.py` (privileged; `--blenderkit` for families that load BlenderKit models), `make-instance` in
  the image (freezes the evaluation scene and its state hash), then `scripts/robowits_mk_limited.py` (the standard twin).
- RoboWits ships no expert: reference solutions exist where we wrote one (`solution/`, with the skills they were written
  with in `solution/ref_primitives.py`); the other families declare their oracle level and evidence (PROTOCOL §2.7).
- align_chopsticks is not included: its frozen scene hits NaN constraint forces within a few steps.

## Image and host
- `images/robowits/` (Genesis 0.4.7, RoboWits' locked stack, RoboWits' Apache-2.0 asset bundle); public in the EAI
  registry. The GPU renders the three cameras; physics runs on the CPU.
- 26 families load BlenderKit models, which may not be redistributed (`images/robowits/NOTICE`). Each user fetches them
  with their own key (`scripts/fetch_robowits_blenderkit.sh`) or uses the encrypted research bundle
  (`scripts/fetch_robowits_blenderkit_encrypted.sh`); the tasks mount the folder read-only from `$RCB_ROBOWITS_BLENDERKIT`.
- Bit-exact means on one CPU vendor: the instances were frozen on Intel; on AMD hosts differentiate_cubes, ball_into_jar
  and stand_bulb fail their frozen-instance check, so these three run on Intel hosts only.

## Time budget (D8)
5400 s for every task of both modes (a longer budget than the default 3600 s: bimanual puzzles that need several attempts,
and every Python process pays about a minute of scene build).

## Grading and determinism
- Physics on Genesis' CPU backend (single-threaded): bit-exact, in-process repeats included. The privileged verifier
  replays the trajectory twice and compares final-state hashes; the standard service grades in-process.
- The particle families separate_marbles_and_sand and stabilize_bottle run on the GPU backend (`RCB_ROBOWITS_BACKEND=gpu`:
  their CPU-backend builds take 39–56 min), which is not bit-exact: their graders report determinism without requiring it,
  and drop the frozen-state check.
- Crash recovery (standard mode, docs/STANDARD_MODE_2_2.md §13): resume class `exact` on the CPU backend, `approx` on the
  GPU backend. Scene builds: 47–234 s on the CPU backend (the 900 s watchdog default is enough); a particle family built
  on the CPU backend needs `RCB_STARTUP_TIMEOUT_S` ≥ 7200.

## Tooling (file names)
| main's convention | RoboWits |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_robowits.py` (`Session`: the frozen instance in `instance.json`, thin primitives, rendering, recording, replay) |
| `tests/rcb_traj.py` (the verifier's copy) | `tests/rcb_robowits.py` |
| standard sidecar (`environment/sim/server.py`) | `environment/sim/server.py` (the 2.2 adapter) + `environment/sim/rcb_robowits.py` |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`) |

The tooling records (T, 16) JOINT_ABS rows (per arm 7 joints + gripper width) at the 30 Hz control rate. Every copy of
`rcb_robowits.py` and of the standard sidecar files is byte-identical across the benchmark (`check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** The agent's tooling gives the frozen instance, the privileged state, recording and
  replay, rendering (`render_frame` / `render_grid` / `render_video`) and thin wrappers of the low-level action (joint
  moves, IK moves without collision checking, gripper, hold). Task-level skills (grasp, place, navigate) are never added
  to it; reference solutions keep theirs under `solution/`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`); the robot's base pose and the world frame's convention are given. Privileged tasks give the
  privileged state through the tooling.

## Standard mode (eai-standard/2.2)
`joint_position` (16) and `ee_pose` (16, right arm first, IK per row on RoboWits' pink/pinocchio IK, gripper-tip frame);
cameras `ego` (static) and `wrist_right` / `wrist_left` (link-mounted); Genesis rasterizer depth; `/kinematics` on
pinocchio (14 arm joints); 80 proprio columns. STANDARD_MODE_2_2.md §16.

## Licences
RoboWits: MIT (declared in its pyproject.toml); Genesis: Apache-2.0; RoboWits' asset bundle: Apache-2.0; BlenderKit models:
licensed to whoever downloads them, never in the image or the repository (`images/robowits/NOTICE`).

## Known issues
During the standard service's in-process grading replay, a late `/status` reports the replay's counter.
