# ABC Sim

Twenty-nine tasks of [ABC Sim](https://github.com/amazon-far/abc) (`abc_sim` at d0832d1, Apache-2.0; assets CC BY 4.0 /
MIT), the MuJoCo simulator of *ABC: Scalable Behavior Cloning with Open Data, Training, and Evaluation*: two I2RT YAM
arms (6 revolute joints and a parallel two-finger gripper each, the robot of YAMLab) side by side at a table, controlled
by joint-position targets. Every task the upstream catalogue scores is here, each as one frozen instance in two modes:
58 task directories `tasks/abc-sim/abc-sim-<family>-i00-{privileged,standard}`, and a standard-realtime twin for the two
families whose scene moves by itself (`abc-sim-conveyor-pick-i00-standard-realtime`, `abc-sim-ball-tray-i00-standard-realtime`):
60 in all.

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/abc-sim -a codex -m openai/gpt-6-astra
```
The tasks need an NVIDIA GPU (the cameras render over EGL; the physics runs on the CPU). The base image is
`ghcr.io/mll-lab-nu/efe:abc-sim-0.1.0` (`images/abc-sim/`), built from public sources.

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

Left out: the four catalogue tasks upstream does not score (it has no success evaluator for them): the three
`put_markers_in_*_drawer` tasks and `build_wood_block_tower`. The count variants are one scene (upstream draws a new
counting directive at every reset whatever the variant asks); here each is a frozen instance with its own directive:
"exactly N objects" for N = 2, 3, 4, "exactly 1 red object" for one (upstream's randomizer never draws "exactly 1 object"
without a colour), and an "all of a colour and shape" directive for the generic one.

## Task definition
- **Instance.** One frozen instance per family, `instance.npz` (the privileged task's `environment/` and `tests/`, the
  standard twins' `environment/sim/`, byte-identical): the assembled scene XML (every object, its variant, size and
  pose already chosen), the full initial `qpos` at rest, and the scene's randomization record (the directive and the
  per-task parameters the evaluator and the runtime read). The scene is the one of an upstream validation demonstration
  whose physics replay succeeded and was bit-identical in two fresh processes (spell_bair has no published
  demonstration: its scene is upstream's randomizer at `reset(seed=243)`). The record's seed is set to 0 except for the
  ball tray, whose runtime seeds its perturbations with it. Two families keep state on the model that the saved scene
  XML of the demonstrations lost (the randomizer writes it at run time): drawer search (the drawer stacks' exact poses;
  the collisions of the unused objects, parked below the table, are off) and chess (the tin's collisions are on only in
  the tin scenario); the instances write it into the scene XML, so the scene is complete in the file. Without it the
  demonstrations replay 0/20 (drawer search) and start numerically unstable (chess). The state hash (MuJoCo's integration
  state and the model's numeric arrays) is recorded and checked on every load.
- **Episode.** It starts at the frozen instance. One control step = 17 physics steps of 2 ms = 0.034 s. Unused objects
  some scenes park below or far above the table (drawer search, chess, sweep) fall freely and touch nothing; they are
  upstream's.
- **Success** is upstream's evaluator for the task (`abc_sim/task_eval/`, the catalogue's `evaluator_name` and options),
  read after every control step, with three changes:
  - **The goal must hold 30 consecutive control steps (1.02 s)**; the episode then ends in success. Upstream counts any
    single step (`ever_success`), and several of its rules count an object while it passes through a region (thrown,
    carried over a bin): the hold stops a pass-through from counting.
  - **Hang a mug:** upstream's test (the mug's centre within 0.115 m of the tree's axis, between its base and 0.05 m
    above its top) also passes a mug standing on the table next to the tree; here the mug must also touch neither the
    table nor a gripper, i.e. hang from the tree, released.
  - **Ball-tray balancing:** upstream's evaluator only checks that the ball is still on the tray, so doing nothing
    scores 1. Here the task's runtime decides: the episode succeeds when its countdown (started the moment both handle
    bars are touched by the fingers, one arm on each; 11 s in the frozen instance) completes with the ball on the tray
    and both handles held throughout (each bar touched within the last 0.1 s at every control step); it fails the moment
    the ball leaves the tray or a handle is let go during the countdown (the runtime's countdown never restarts).
  Every rule is stated in words, with its thresholds, in each task's instruction.
- **Texts.** The privileged instruction names the scene's bodies and points to `s.state()`; the standard instructions
  state the goal and the rule in words, with the robot's conventions. World-frame information: the standard texts give
  no world coordinates of workspace items (no object, bin or table positions; directions are relative to the arms);
  the robot's base poses, the camera calibration and the world frame's axes are given.
- **Time limit: 3600 s**, the same for every task and mode (each task's `[agent] timeout_sec`).

## Modes
- **Privileged:** `rcb_abc.Session` (`/opt/abc-tools/rcb_abc.py` in the image) in the agent's container: reset, the scene's
  full state (every free body's pose, the evaluator's and the runtime's view, the randomization record), MuJoCo model
  and data, exact mid-episode snapshots, rendering (RGB, depth, calibration), the robot's kinematics (FK, IK), recording
  and self-replay. Deliverable `/app/output/trajectory.npz`, `(T, 14)` rows, at most 20,000. The grader
  (`/opt/abc-tools/grade.py`) checks the file (readable, `(T, 14)`, finite, not too long: otherwise `bad_trajectory`, the
  agent's 0) before it replays it twice, side by side, in fresh processes; a replay that then gives no result is
  `replay_failed` with `grader_error = 1` and `infra_error = 1`. A third replay renders `replay.mp4` after the verdict.
- **Standard (`eai-standard/2.2`):** the shared layer of `embodied_first_exam/standard/` (from the pinned
  `standard-sim-files` image) and the adapter `/opt/abc-tools/standard/server.py` (in the base image; `run.sh` starts it
  through `RCB_SERVER`):
  - action type `joint_position`: the 14 numbers per control step, as in privileged mode; `linear` or `hold` between rows
    `dt` apart; rows are executed as sent (abc_sim rounds each command to float32 and the servos clamp it to the
    actuator's range; the clamped entries are reported in `meta.clipped`, not changed: clipping a row before abc_sim's
    float32 rounding changes the physics in the last bits);
  - six cameras, 640 x 480, depth on request: `top`, `overhead`, `left_side`, `right_side` (static) and the wrist cameras
    `left`, `right` (on the arms' sixth links); default `top`, `left`, `right`;
  - proprioception: `joint_pos` (the 14 action coordinates measured), `joint_vel`, `gripper_opening` (m), `tcp_pose` (each
    arm's tool centre point, world frame, `wxyz`), `joint_effort`; never an object's pose;
  - `/kinematics`: FK of the tool frames (`left_tcp`, `right_tcp`, `left_grasp`, `right_grasp`), the arm links and the
    wrist-camera mounts; IK of the tool frames with each arm's own six joints (damped least squares, several starts);
  - resume class `exact` (MuJoCo on the CPU repeats bit for bit in a fresh process); `max_frames_per_call` 1000;
  - reset budget 0 (the mode's default): one episode. The adapter implements the optional reset capability, so a run
    can grant resets with `RCB_RESET_BUDGET`.
- **Standard-realtime (`eai-standard/2.3`):** the shared realtime layer (`rcb_realtime.py` from `standard-sim-files`,
  `rcb_service.py` byte-identical to the other realtime benchmarks' copies, in the base image at
  `/opt/abc-tools/realtime/`) and the adapter `/opt/abc-tools/realtime/server.py` on the same Session: the standard twin's
  instance, action, success rule, cameras and proprioception (not served: `/kinematics`, per-frame camera poses, depth
  modes). The scene-dynamic families get the twin: the conveyor belt carries the objects, and the tray's runtime pushes
  the ball. **S = 1**: the service's real-time factor (0.034 s of simulation per control step) is 11.2 for the conveyor
  and 17.1 for the ball tray without rendering, 5.3 and 10.2 rendering three cameras every step (RTX 4090, EGL), above
  PROTOCOL §2's 3. Reset budget 10 (the mode's default).

## Grading (standard and standard-realtime)
The verdict is the live episode's (PROTOCOL H.4): the episode the sim sidecar ran, under the task's rule as
`Session.step` applied it (the 1.02 s hold is part of the rule, run on the live simulator). Standard: the collect hook
(`/opt/abc-tools/standard/finalize.sh`) ends the service, writes `final.json` (`graded_by` = `live`, `replays` = 0) and then
renders `replay.mp4` in one pass over the trajectory (EGL on the sidecar's GPU); the video decides nothing. Realtime: the
shared layer does the same from the adapter's `step()`. The verifier is the shared `v2_1/grade.py` (from the pinned
`standard-files` image), for both modes. At a fresh episode's start the service compares the built scene's state hash
with the instance's recorded one; a mismatch gives up before the agent is served (`instance_mismatch`, `infra_error`).

## Reference solutions and oracle levels
`oracle = "full"` for all 60 directories. The reference of a family (`solution/oracle.npy`) is the commanded actions of
the validation demonstration whose scene is the frozen instance (after its first frame), replayed from the instance and
cut at the success step; spell_bair's is a hand-built trajectory (scripted inverse kinematics on the grasp frame, top-down
grasps with the clearest finger yaw, place checks and re-placing) on its seed-243 layout. The rows are float32 values
(abc_sim rounds every command to float32 anyway), so the privileged replay and the standard client execute the same rows.
Privileged: `solution/oracle_replay.py` replays and saves them. Standard: `solution/oracle_stream.py` streams them as
`joint_position` chunks. Standard-realtime: `solution/oracle_plan.py` plans them into the episode at the control steps
where they ran (`submit(..., at=step)`, sent ahead of the clock).

How the instances were chosen (the feasibility spike, 2026-10-20/21, issue #473): every validation demonstration of each
family was replayed from its recorded scene twice in fresh processes under MuJoCo 3.6.0, the version the demonstrations
were recorded with (under 3.8.1, which upstream pins now, fewer replays succeed: nuts and bolts 0/12 against 6/12);
510/510 final states were bit-identical. The first demonstration (in a fixed order) whose replay succeeded became the
instance. Replay success per family (the rest is open-loop drift: the recordings themselves mostly succeed): pouring,
grab from clutter, in-hand transfer, turn a mug and four spell words 20/20; spell yam 18/20, abc 17/21, xdof 16/20; put
relative 18/20; put bottles 18/20; count 17/20 (exactly 1 / 2 / 3 / 4: 10/10, 9/10, 10/10, 9/10); hang a mug 16/20;
drawer search 15/20; throw bottles 11/20; conveyor 10/20; dish rack 7/20 (its demonstrations fail 11/20 themselves);
nuts and bolts 6/12; sweep 5/20; LEGO 5/20; chess 3/17; ball tray (the rule above) 29/100.

## Verification (efe:abc-sim-0.1.0)
Oracle and `nop` with Harbor on an RTX 4090 workstation (AMD Ryzen 9 7950X), 2026-10-21, the image built from
`images/abc-sim/`: **oracle 60/60**, every one on its first attempt; **nop 60/60 scored 0** (`infra_error` 0). In every
family both privileged replays, the standard service's live episode and the realtime service's live episode end in the
same final state (the hash below), which is also the reference's final state on the host where the instances were frozen
(Python 3.11, NumPy 2.4.6; the image runs Python 3.12): MuJoCo 3.6.0 on the CPU is bit-exact across these processes.
The realtime oracles (the reference planned with `submit(..., at=step)` at S = 1) ran with no late step and no stall (the
largest lag 11 ms).

| family | reference rows | oracle, privileged (both replays) | oracle, standard (live) | oracle, standard-realtime (live) | final state | nop (priv / std / realtime) |
|---|---|---|---|---|---|---|
| `ball_tray` | 453 | 1 | 1 | 1 | `0d05516cffd7e620` | 0 / 0 / 0 |
| `chess` | 1872 | 1 | 1 | -- | `95d72acb81802ac4` | 0 / 0 |
| `conveyor_pick` | 274 | 1 | 1 | 1 | `80563de74a724075` | 0 / 0 / 0 |
| `count` | 277 | 1 | 1 | -- | `b505c774f544eaf8` | 0 / 0 |
| `count_four` | 671 | 1 | 1 | -- | `61409c4d0e466e6a` | 0 / 0 |
| `count_one` | 264 | 1 | 1 | -- | `dabc9c60b668c109` | 0 / 0 |
| `count_three` | 538 | 1 | 1 | -- | `cfb8e8f612a52bd7` | 0 / 0 |
| `count_two` | 291 | 1 | 1 | -- | `0514bf38465fb2ea` | 0 / 0 |
| `dish_rack` | 375 | 1 | 1 | -- | `12ee39cc6ca7725b` | 0 / 0 |
| `drawer_search` | 432 | 1 | 1 | -- | `5f4d8d12d9027048` | 0 / 0 |
| `grab_clutter` | 226 | 1 | 1 | -- | `1de5d81724c1628a` | 0 / 0 |
| `hang_mug` | 314 | 1 | 1 | -- | `c13c9ccdf019b28e` | 0 / 0 |
| `inhand_transfer` | 374 | 1 | 1 | -- | `b15263ed28fedcff` | 0 / 0 |
| `lego` | 2205 | 1 | 1 | -- | `697c1c23c81322bf` | 0 / 0 |
| `nuts_bolts` | 2872 | 1 | 1 | -- | `adc51944b0096256` | 0 / 0 |
| `pouring` | 307 | 1 | 1 | -- | `14a0bf1cea242cde` | 0 / 0 |
| `put_bottles` | 476 | 1 | 1 | -- | `011999892aad55fe` | 0 / 0 |
| `put_relative` | 237 | 1 | 1 | -- | `b3bacfe0c48af964` | 0 / 0 |
| `spell_abc` | 507 | 1 | 1 | -- | `8cbaf7ef49ff90a9` | 0 / 0 |
| `spell_agi` | 581 | 1 | 1 | -- | `6b54dcc0c6e409c3` | 0 / 0 |
| `spell_bair` | 1360 | 1 | 1 | -- | `f20fdf438e9ab63f` | 0 / 0 |
| `spell_cat` | 909 | 1 | 1 | -- | `a75f73d72cf9b18c` | 0 / 0 |
| `spell_dog` | 580 | 1 | 1 | -- | `b2090d429824e80e` | 0 / 0 |
| `spell_fish` | 675 | 1 | 1 | -- | `8a96253cc31a34ec` | 0 / 0 |
| `spell_xdof` | 719 | 1 | 1 | -- | `69efe25ba8cd6cbc` | 0 / 0 |
| `spell_yam` | 581 | 1 | 1 | -- | `0d6b71b98369775d` | 0 / 0 |
| `sweep` | 1288 | 1 | 1 | -- | `0c0685ed6ef4b04c` | 0 / 0 |
| `throw_bottles` | 563 | 1 | 1 | -- | `d5a8babe7c4be42b` | 0 / 0 |
| `turn_mug` | 561 | 1 | 1 | -- | `75511085888777f6` | 0 / 0 |

The oracle batch ran on the task directories before their last edit, which changed only texts (the ball tray's
instruction and README) and the resource declarations of `task.toml`; `nop` ran on the final directories, and so did the
oracle again on twelve of them (the ball tray's three, the conveyor's three, chess and spell bair in both modes, nuts and
bolts standard, drawer search privileged): 12/12, the same final states.
- `bash ci_checks/run_all.sh tasks/abc-sim/abc-sim-*`: every invariant holds; the one advisory finding is the root
  README's benchmark list (regenerated after merge).
- `python3 scripts/task_conventions.py --check tasks/abc-sim/abc-sim-*`: clean.
- `ci_checks/check-standard-protocol.py` against a live spell_abc service: 222 PASS, 0 FAIL, 16 WARN (velocity limits:
  the simulator enforces none).
- Crash recovery: the spell_abc service killed (`kill -9`) after 300 of the reference's 507 rows; it restarted, resumed
  the same episode (`resumes` 1, no state mismatch) and the reference ended in success at the same final state.
- In one process: a reset after 150 steps returns to the instance's hash, a replay after it ends at the fresh-process
  final state, and a mid-episode `snapshot()` / `restore()` continues bit for bit (all 29 families).
- Measured (the oracle trials): the privileged agent container 1.9 GB and its verifier 3.9 GB (chess); the standard
  sidecar 2.1 GB and 0.83 GiB of GPU memory (chess), the realtime sidecar 0.8 GB and 0.72 GiB; the client container 0.03 GB.

## Integrity
- abc_sim ships no scripted expert or policy. The image takes the package from the upstream repository at its commit
  and the asset packages by checksum in a fetch stage whose layers are not part of the image, and leaves out what
  points at the demonstrations, checkpoints or the asset mirror: the package's README files, the asset manifest, the
  Blender exporter of recorded dataset episodes and the comments of the scene XMLs (one described the training data).
  Only the meshes and textures the 29 frozen scenes open are kept (`images/abc-sim/assets.txt`), with every package's
  licence and attribution files (`/opt/abc/ASSET_LICENSES.md`).
- Nothing an agent can read names its source: the instances carry no demonstration or episode id, and the reference
  solutions live under `solution/` only.
- **Agent egress is the model APIs and the package registries** (PROTOCOL H.6). The demonstrations and checkpoints are on
  Hugging Face and the upstream mirror, both unreachable. ABC Sim is not on PyPI (`abc-sim` and `abc-minimal` do not
  exist there).

## Files
Each task directory carries its frozen instance (`instance.npz`) and its reference solution (`solution/`); the standard
twins also the task's text for the service (`environment/sim/task.json`). Everything the tasks share is in the base image
(`images/abc-sim/`: the Dockerfile, the pinned packages, the asset list, the fetch stage's assembly script, and
`tools/`: `rcb_abc.py`, `grade.py`, `video.py`, `standard/server.py`, `standard/finalize.sh`, `realtime/server.py`,
`realtime/rcb_service.py`). The tooling that froze the instances and wrote the task directories is kept outside this
repository.

## Standard-mode service details
Serves `eai-standard/2.2` (MuJoCo on the CPU, EGL rendering, resume class `exact`); `max_frames_per_call` = 1000. The
optional reset capability is implemented with a budget of 0 by default; the 2.2 client has no `reset()`, so a run that
grants resets calls `POST /reset` through `Robot._post`. The scene builds in 1-5 s (`RCB_STARTUP_TIMEOUT_S` 300).
