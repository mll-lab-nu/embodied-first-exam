# ABC Sim

## Overview
Twenty-nine tasks of [ABC Sim](https://github.com/amazon-far/abc), the MuJoCo simulator of *ABC: Scalable Behavior
Cloning with Open Data, Training, and Evaluation*: two I2RT YAM arms (6 revolute joints and a parallel two-finger
gripper each) side by side at a table, controlled by joint-position targets. Every task the upstream catalogue scores
is here, each as one frozen instance in two modes: 58 task directories `tasks/abc-sim/abc-sim-<family>-i00-{privileged,standard}`,
plus a realtime task for the two families whose scene moves by itself (`abc-sim-conveyor-pick-i00-realtime`,
`abc-sim-ball-tray-i00-realtime`): 60 in all.

```bash
harbor run -d embodied-first-exam@all -p tasks/abc-sim -a codex -m <model>
```

| | |
|---|---|
| upstream | `abc_sim` of [amazon-far/abc](https://github.com/amazon-far/abc) @ `d0832d1` (Apache-2.0), on MuJoCo 3.6.0 |
| images | `ghcr.io/mll-lab-nu/efe:abc-sim-0.3.0` (privileged) and `abc-sim-0.5.1` (standard and realtime): `images/abc-sim/`, built from public sources |
| GPU | any NVIDIA GPU with EGL: the cameras render over EGL, the physics runs on the CPU |
| metadata | `simulator = "mujoco"`, `robot = "i2rt-yam-bimanual"`, `family = "<family>"`, `oracle = "full"` |
| time limit | 3600 s for every task and mode (`[agent] timeout_sec`) |

The per-task READMEs are rendered from `tasks/abc-sim/readme.toml` (benchmark, license and each family's success
rule, with the source lines it was read from).

## Upstream and license
ABC Sim (`abc_sim` of [amazon-far/abc](https://github.com/amazon-far/abc) at `d0832d12651d1b260a652861a14648dc5f3660c7`),
Apache License 2.0; paper: Allshire et al., 2026 (arXiv:2606.27375). Its simulator assets are under CC BY 4.0 (RoboCasa's
Objaverse, LightWheel and AI-generated packs, Google Scanned Objects, individually credited Sketchfab creators), CC0
(freepoly.org), MIT (the I2RT YAM robot model, a LIBERO drawer fixture) and Apache-2.0 (everything modelled in-house).
No non-commercial terms apply. The licences and per-object credits ship in the image (`/opt/abc/ASSET_LICENSES.md`,
from `images/abc-sim/ASSET_LICENSES.md`, and the packages' own attribution files). MuJoCo 3.6.0 is Apache-2.0.

## Changes from upstream
- **Physics: none.** The scenes, robot model and evaluators are upstream's at the pinned commit, on MuJoCo 3.6.0, the
  version the demonstrations were recorded with.
- **Frozen instances.** One instance per family, `instance.npz`: the assembled scene XML (every object, its variant,
  size and pose already chosen), the full initial `qpos` at rest, and the scene's randomization record (the directive
  and the per-task parameters the evaluator and the runtime read). The scene is that of an upstream validation
  demonstration whose physics replay succeeded and was bit-identical in two fresh processes; spell_bair has no
  published demonstration, so its scene is upstream's randomizer at `reset(seed=243)`. Two families keep state on the
  model that the saved scene XML lost (the randomizer writes it at run time): drawer search (the drawer stacks' exact
  poses; the collisions of the unused objects, parked below the table, are off) and chess (the tin's collisions are on
  only in the tin scenario). The instances write it into the scene XML. The state hash (MuJoCo's integration state and
  the model's numeric arrays) is recorded and checked on every load. Several families allow further seeds, each a
  committed instance under the privileged task's `tests/seeds/<seed>/`.
- **Success checks.** Upstream's evaluator for each task (`abc_sim/task_eval/`), read after every control step, with
  three changes:
  - **The goal must hold 30 consecutive control steps (1.02 s).** Upstream counts any single step, and several of its
    rules count an object while it passes through a region (thrown, carried over a bin).
  - **Hang a mug:** upstream's test also passes a mug standing on the table next to the tree; here the mug must also
    touch neither the table nor a gripper finger.
  - **Ball-tray balancing:** upstream's evaluator only checks that the ball is still on the tray, so doing nothing
    scores 1. Here the task's runtime decides: its countdown (started when both handle bars are touched, one arm on
    each) must complete with the ball on the tray and both handles held throughout.
- **Left out.** The four catalogue tasks upstream does not score (it has no evaluator for them): the three
  `put_markers_in_*_drawer` tasks and `build_wood_block_tower`. The count variants are one upstream scene, which draws
  a new counting directive at every reset; here each is a frozen instance with its own directive ("exactly N objects"
  for N = 2, 3, 4; "exactly 1 red object", since upstream's randomizer never draws "exactly 1 object" without a colour;
  "all of a colour and shape" for the generic one).
- **Removed from the image.** abc_sim ships no scripted expert or policy. The image leaves out what points at the
  demonstrations, checkpoints or asset mirror: the package's README files, the asset manifest, the exporter of
  recorded dataset episodes and the comments of the scene XMLs. Only the meshes and textures the frozen scenes open are
  kept (`images/abc-sim/assets.txt`), with every package's licence and attribution files.
- **Added.** The tooling module `rcb_abc.py` (privileged session, replay, rendering, kinematics), the privileged grader
  `grade.py`, and the standard and realtime adapters (`images/abc-sim/tools/`).

## Interface
- **Actions (every mode).** 14 joint-position targets per control step, `[left_joint1..6, left_gripper,
  right_joint1..6, right_gripper]`: radians for the joints, the gripper opening from 0 (closed) to 1 (open, each finger
  0.0475 m from closed; up to 1.042). The servos clamp a target to the actuator's range; abc_sim rounds every command
  to float32. One control step = 17 physics steps of 2 ms = 0.034 s.
- **Privileged.** `rcb_abc.Session` (`/opt/abc-tools/rcb_abc.py`) in the agent's container: reset, the full scene
  state (every free body's pose, the evaluator's and the runtime's view, the randomization record), MuJoCo model and
  data, exact mid-episode snapshots, rendering (RGB, depth, calibration), forward and inverse kinematics, recording and
  self-replay. Deliverable: `/app/output/trajectory.npz`, `(T, 14)` rows, at most 20,000.
- **Standard.** The robot is a service in the `sim` sidecar (adapter `/opt/abc-tools/standard/server.py` on the shared
  layer of `embodied_first_exam/standard/`), served under the rules of eai-standard/3.0: `joint_position` chunks
  (`linear` or `hold` between rows `dt` apart; rows executed as sent, clamped entries reported in `meta.clipped`); six
  cameras at 640 x 480 with depth on request (`top`, `overhead`, `left_side`, `right_side` fixed; the wrist cameras
  `left`, `right`; default `top`, `left`, `right`); proprioception `joint_pos`, `joint_vel`, `gripper_opening`,
  `tcp_pose`, `joint_effort`, never an object's pose; `/kinematics` (FK of the tool frames, the arm links and the
  wrist-camera mounts; IK of the tool frames); at most 1000 frames per call; resume class `exact`. Reset budget 0.
- **Realtime.** The shared realtime layer with the adapter `/opt/abc-tools/realtime/server.py` on the same Session:
  the standard task's instance, action, success rule, cameras and proprioception, without `/kinematics`, per-frame
  camera poses and depth modes. Slowdown S = 1: the service runs 5.3 (conveyor) and 10.2 (ball tray) times faster than
  real time while rendering three cameras every step on an RTX 4090. Reset budget 0.
- **World-frame information.** The privileged instruction names the scene's bodies and points to `s.state()`. The
  standard and realtime texts give no world coordinates of workspace items (no object, bin or table positions;
  directions are relative to the arms); the arms' base poses, the camera calibration and the world frame's axes are
  given.

## Grading
- **Rule.** Each family's success rule (its upstream evaluator, with the changes above) is checked after every control
  step; every rule but the ball tray's must hold 30 consecutive control steps. Each task's README states the rule
  exactly.
- **Privileged.** `/opt/abc-tools/grade.py` checks the file (readable, `(T, 14)`, finite, 1 to 20,000 rows; otherwise
  the agent's 0) and replays it once, in a fresh process, from the verifier's copy of the instance; the replay stops
  where the episode ends. A replay that gives no result is a grader error. A second replay renders `replay.mp4` after
  the verdict.
- **Standard and realtime.** The verdict is the live episode's, on the state the episode ends in (`/finish` or the
  end of the agent's session). For a hold rule the service, after the agent is gone, holds the robot's last command
  for the 30-step window and the goal must hold for all of it (standard: on a snapshot, `end_window` in `final.json`;
  realtime: `end_window_steps`). Ball tray: the countdown has completed and the ball is still on the tray; the ball
  leaving the tray ends the episode with 0. The collect hook (`/opt/abc-tools/standard/finalize.sh`) writes
  `final.json` and then renders `replay.mp4` from the trajectory (EGL on the sidecar's GPU); the video decides nothing.
  The verifier is the shared `embodied_first_exam/standard/sidecar/grade.py` for both modes. A fresh episode whose built
  scene does not match the instance's state hash gives up before the agent is served (`instance_mismatch`,
  infrastructure).

## Tasks
| family | upstream task | directive of the frozen instance | reference rows |
|---|---|---|---|
| `throw_bottles` | `throw_plastic_bottles_in_bin` | throw plastic bottles in bin | 563 |
| `put_bottles` | `put_plastic_bottles_in_bin` | put the plastic bottles in the bin | 476 |
| `conveyor_pick` | `conveyor_pick` | pick objects from the conveyor belt and put them in the bin | 274 |
| `count` | `count_into_opaque_box` | put all yellow triangles in the box | 277 |
| `count_one` | `count_one_into_opaque_box` | put exactly 1 red object in the box | 264 |
| `count_two` | `count_two_into_opaque_box` | put exactly 2 objects in the box | 291 |
| `count_three` | `count_three_into_opaque_box` | put exactly 3 objects in the box | 538 |
| `count_four` | `count_four_into_opaque_box` | put exactly 4 objects in the box | 671 |
| `put_relative` | `put_relative` | put the soap dispenser to the right of the boxed food | 237 |
| `grab_clutter` | `grab_specific_object_from_clutter` | grab the ketchup and place it in the box | 226 |
| `ball_tray` | `ball_tray_balancing` | grab the tray handles and keep the ball balanced on the tray | 453 |
| `inhand_transfer` | `inhand_transfer_item_to_other_side` | inhand transfer the item to other side (a cream cheese stick) | 374 |
| `drawer_search` | `multi_drawer_search` | find the measuring cup, then the dish brush | 432 |
| `pouring` | `pouring` | pour from one container into another | 307 |
| `hang_mug` | `hang_mug_on_mug_rack` | hang mug on mug rack | 314 |
| `turn_mug` | `turn_mug_right_side_up` | turn mug right side up (two mugs) | 561 |
| `sweep` | `sweep_away_paper_scraps_from_table` | sweep away paper scraps from the table (two scraps) | 1288 |
| `nuts_bolts` | `sort_nuts_and_bolts` | sort the nuts and bolts into their matching bins (9 nuts, 10 bolts) | 2872 |
| `lego` | `sort_lego_blocks` | sort the red, yellow, and blue lego blocks into their matching bins (12 blocks) | 2205 |
| `dish_rack` | `load_plates_into_dish_rack` | load plates into tabletop dish rack (one plate) | 375 |
| `chess` | `set_up_chess_pieces_on_board` | set up chess pieces on the board (six black pieces on the table) | 1872 |
| `spell_cat`, `spell_dog`, `spell_fish`, `spell_bair`, `spell_xdof`, `spell_abc`, `spell_yam`, `spell_agi` | `spell_<word>` | spell <word> | 909, 580, 675, 1360, 719, 507, 581, 581 |

- **Reference solutions** (`oracle = "full"` for all 60 directories). A family's reference (`solution/oracle.npy`) is
  the commanded actions of the validation demonstration whose scene is the frozen instance, replayed from the instance
  and cut at the success step; spell_bair's is a hand-built trajectory on its seed-243 layout. The rows are float32
  values, so the privileged replay and the standard client execute the same rows. Privileged: `solution/oracle_replay.py`
  replays and saves them. Standard: `solution/oracle_stream.py` streams them as `joint_position` chunks. Realtime:
  `solution/oracle_plan.py` plans them into the episode at the control steps where they ran (`submit(..., at=step)`).
- **Files.** Each task directory carries its frozen instance (`instance.npz`) and its reference solution
  (`solution/`); the standard and realtime tasks also the task's text for the service (`environment/sim/task.json`).
  Everything the tasks share is in the base image (`images/abc-sim/`).

## Others
- **Determinism.** MuJoCo 3.6.0 on the CPU repeats bit for bit across fresh processes: in every family both
  privileged replays, the standard service's live episode and the realtime service's live episode end in the same
  final state. Under MuJoCo 3.8.1, which upstream pins now, fewer demonstrations replay successfully, so the image
  stays on 3.6.0.
- **Egress.** The agent reaches the model APIs and the package registries only. The demonstrations and checkpoints
  are on Hugging Face and the upstream mirror, both unreachable; ABC Sim is not on PyPI.
