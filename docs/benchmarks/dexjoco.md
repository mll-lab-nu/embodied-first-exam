# DexJoCo

Dexterous manipulation with a 16-DoF Allegro hand on a Franka Panda arm (or two of them), from DexJoCo
([brave-eai/dexjoco](https://github.com/brave-eai/dexjoco), MIT): its 11 tasks, each on one frozen scene instance taken
from a public human demonstration, in both modes (`scripts/dexjoco/`).

| | |
|---|---|
| upstream | DexJoCo @ `8d23b0f` (MIT); human demonstrations: Hugging Face dataset `DexJoCo/DexJoCo-Datasets-Raw` (public) |
| simulator | `dexjoco`: DexJoCo's gymnasium envs on MuJoCo 3.4.0, CPU physics (bit-exact replay in a fresh process), OSMesa rendering; no GPU |
| robots | `franka-allegro` (6 tasks), `franka-allegro-bimanual` (5 tasks, two arms side by side) |
| score | binary: DexJoCo's own success check (its episode ends at the first success or task failure); `water_plant` adds an aiming condition (below) |
| tasks | 11 families × 2 modes: `tasks/dexjoco-<family>-i00-privileged` and `-standard` (`eai-standard/2.2`) |
| image | `ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2` (`images/dexjoco/`: DexJoCo @ 8d23b0f and its pinned dependency closure; no demonstrations, no policies) |
| oracle | full, both modes: the demonstration's own actions |
| agent time budget | 5400 s for every task (D8: dexterous control of 16 hand joints per arm through a thin interface; the model runs we made used most of it) |
| egress | allowlisted to the model APIs in both modes: the reference demonstrations are public (PROTOCOL §2.7) |

## Tasks

| family | robot | asks | oracle rows (50 Hz) |
|---|---|---|---|
| water_plant | single | spray the plant: the trigger held while the nozzle is near the plant and aimed at it, 30 steps | 307 |
| click_mouse | single | put the mouse on the pad and click, then keep it there 10 steps | 560 |
| hammer_nail | single | drive the nail at least 4 cm deep with counted strikes | 202 |
| pick_bucket | single | put the boxed food into the bucket and lift the bucket 15 cm | 580 |
| pinch_tongs | single | three pinches with the tongs held 10 cm up, then 30 steps | 375 |
| fold_glasses | single | fold both temples and put the glasses into the case, 50 steps | 612 |
| bimanual_hanoi | bimanual | the three-disk tower moved to post C, 20 steps; an illegal stack fails | 1085 |
| bimanual_microwave_cook | bimanual | hot dog in, door closed, start pressed | 815 |
| bimanual_unlock_ipad | bimanual | enter 1-2-3 with a fingertip, unlocked 10 steps; a wrong digit fails | 392 |
| bimanual_assembly | bimanual | peg into the tray's socket, touching the bottom 30 steps | 586 |
| bimanual_photograph | bimanual | camera held 0.4 m in front of the logo, axis within 10 deg, shutter pressed | 260 |

## Task definition
- **Instance.** The task's env after DexJoCo's reset, with the initial object poses and table height of one human
  demonstration restored by DexJoCo's own state restorer (demo `state[0]`). DexJoCo's reset samples poses from the
  global RNG and its restorers edit the MuJoCo model (table height, fixed bodies), so the instance is a snapshot, not a
  seed: `instance.npz` holds the full physics state (`mjSTATE_INTEGRATION`), mocap targets, controls, every numeric
  `MjModel` array a task can change, and the env's Python-side task state (counters, flags). Its hash is checked
  whenever a task rebuilds it (privileged verifier, standard service, every replay).
- **Action.** DexJoCo's own row per control step (50 Hz, 10 physics substeps of 2 ms): per arm the tcp target pose
  (xyz, quaternion wxyz, world frame), which DexJoCo's operational-space controller tracks, and 16 Allegro joint targets.
  Single arm 23 values, bimanual 46 (right first; the left hand's fingers in DexJoCo's mirrored order).
- **Episode.** As in DexJoCo's evaluation: it ends at the first success or task failure. DexJoCo's episode cap, its
  real-time pacing, its per-step camera rendering and hanoi's wall-clock auto-reset are lifted (`rcb_dexjoco.py`):
  the wall clock is the only budget.
- **water_plant.** Upstream's zone + trigger test passes with the bottle lying on the table and spraying away from the
  plant (two Opus 5.5 runs did exactly that). The task also requires the spray direction (the bottle's local +z) within
  45 deg of the nozzle-to-plant line, held with the rest for 30 steps; the demonstration sprays 33 deg off.

## Privileged mode
`rcb_dexjoco.Session` on the frozen instance: unlimited exact resets, live object poses (`s.objects()`), DexJoCo's state
dict, thin primitives (tcp-target moves, hand-joint interpolation, hold), rendering, recording and self-replay. The
deliverable is `/app/output/trajectory.npz`; the verifier replays it twice in a fresh process from its own copy of the
instance: success = both replays succeed ∧ same final-state hash ∧ the instance rebuilt exactly.

## Standard mode (`eai-standard/2.2`)
The 2.2 adapter `scripts/dexjoco/shared/standard/server.py` on the shared layer (`scripts/eai_standard/`, copied
unchanged), resume class `exact`:
- **actions:** `ee_pose` (DexJoCo's own row) and `joint_position` (per arm 7 arm + 16 hand joint targets; the arm part
  becomes a tcp target by forward kinematics, the same controller tracks it). The service journals and records the
  executed DexJoCo row, so the recorded trajectory replays in the privileged tooling unchanged.
- **observations:** every camera of the scene (static `front`, `back`, `left`, `right`, `top0`; the hand cameras on each
  hand's mount) at 640 x 480 with calibration (static pose or mount link), optional z-depth from the same renderer;
  proprioception `joint_pos`, `joint_vel`, `joint_effort` (7 + 16 per arm), `tcp_pose`, plus `tcp_target` and
  `hand_target` (the targets being tracked); no gripper-opening column (a dexterous hand).
- **kinematics:** stateless FK of the arm links, the hand mount and the tcp; IK of each tcp over its arm's 7 joints
  (damped least squares within the joint ranges).
- **robot_spec:** joints with the simulator's limits (arm torque limits; hand position actuators unlimited in effort),
  the hand drives' gains, the tcp definition (DexJoCo's `attachment_site`, the flange), the arm bases.
- **evidence and grading:** the collect hook (`finalize.sh`) ends the service, replays the recorded trajectory in two
  fresh processes and renders `replay.mp4` in a third; success = live ∧ both replays ∧ deterministic.
- `ci_checks/check-limited-protocol.py` passes against a live service of a single-arm and a bimanual task (velocity limits are null:
  WARN only). Crash recovery: the service killed between calls and inside a call resumes the same episode
  (`resumes = 2`, exact hash) and the oracle still ends in success with `live_matches_replay`.

## World-frame information (D7)
Privileged mode gives world coordinates (object poses through the tooling, the table height and the arm bases in the
instruction). Standard mode gives the robot's own pose only: each arm's base pose in `robot_spec`, the tcp in
proprioception, the cameras' calibration; no table height, no object or workspace coordinates in `/spec` or the texts.
The goals state their thresholds as relative distances (e.g. "within 0.20 m of the plant").

## Reference solutions
The demonstration's own actions (`scripts/dexjoco/instances/<family>/oracle_trajectory.npz`, built by
`make_instances.py` in the image), replayed until the episode ends in success. The standard client sends float32, so
the rows are rounded to float32 for both modes; every family still succeeds, `bimanual_hanoi` after holding its last row
8 more steps (the rounded rows end its 20-step hold count short). Standard mode streams the same rows through the client
as `ee_pose` chunks; the recorded trajectory is then exactly the privileged reference.

## Regenerating
```bash
python3 scripts/dexjoco/get_demo.py water_plant 1 /tmp/demos          # only to rebuild an instance from its demo
docker run --rm --user $(id -u):$(id -g) -e HOME=/tmp -v $PWD:/repo -w /repo ghcr.io/mll-lab-nu/eai-dexjoco:0.1.2 \
    python scripts/dexjoco/make_instances.py --all                     # check the instances and oracles, refresh facts.json
python3 scripts/dexjoco/generate.py && python3 scripts/dexjoco/generate.py --check
```
