# DexHand

DexHand is a benchmark of dexterous-hand manipulation in MuJoCo 3.4.0 (CPU physics, software rendering). It has thirty
task families (the ten of the first release and twenty household scene families of wave 2), each with one
frozen scene, in privileged and standard mode (60 task directories,
`dexhand-<family>-i00-{privileged,standard}`, standard mode on `eai-standard/2.2`):

## Quick start
```bash
harbor run -d embodied-first-exam@all -p tasks/dexhand -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| Family | Robot | Row width (Sharpa / Wuji) | Control | Oracle (Sharpa) |
|---|---|---|---|---|
| `essential_cube_layer` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 450 rows |
| `essential_held_joystick` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 415 rows |
| `essential_pen_regrasp` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 385 rows |
| `essential_two_object` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 408 rows |
| `essential_rotary_gait` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 15,620 rows |
| `essential_cube_reorient` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 153 rows |
| `assemble_hamburger` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 6,090 rows (standard: 5,793) |
| `paper_half_fold` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 40 x 0.5 ms | 1,108 rows (+ 250 hold rows) |
| `sweep_dustpan` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 2000 Hz, one 0.5 ms step | 132,521 rows (+ 16,000 hold rows) |
| `pot_shelf_transfer` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 500 Hz, one 2 ms step | 8,850 rows |
| `remote_battery_swap` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 2,416 rows |
| `coffee_stir` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 1,882 rows |
| `jar_lid_open` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 1,159 rows |
| `grinder_crank` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 1,096 rows |
| `pancake_serve` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 20 x 1 ms | 1,167 rows |
| `vacuum_bin_reseat` | two hands, each on its own six-DoF wrist stage | 56 / 52 | 50 Hz, 20 x 1 ms | 1,331 rows |
| `drying_rack_unfold` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 2,415 rows |
| `picture_hang` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 869 rows |
| `usb_plug_insert` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 1,595 rows |
| `fan_guard_install` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 2,665 rows |
| `stool_brace_insert` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 3,006 rows |
| `ram_module_install` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 1,529 rows |
| `boot_sole_brush` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 1,688 rows |
| `paper_staple` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 942 rows |
| `binder_page_load` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 3,095 rows |
| `envelope_letter_insert` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 2,446 rows |
| `book_page_turn` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 553 rows |
| `tray_glass_carry` | two hands, each on its own six-DoF wrist stage | 56 / 52 | 50 Hz, 10 x 2 ms | 1,072 rows |
| `batter_whisk` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 1,916 rows |
| `bicycle_pump_stroke` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 4,299 rows |

The default hand is a right (on the arms and the two-stage rigs: a left and a right) **Sharpa Wave** with 22 actuated finger joints; every
family also runs with the genuine **Wuji Hand 2.2** (20 finger joints) mounted in its place, selected per
episode (`essential_two_object` and `sweep_dustpan` with a Wuji-specific start, see Hands). There
is no assisted grasp: no welds, attachments, scripted object motion or forces on objects; objects move only through
contact and gravity. Every family's reference solution is a recorded physical Sharpa episode (`oracle = "full"`);
nine of the first ten (all but `sweep_dustpan`) and two of the wave-2 families also package a successful Wuji Hand 2.2 episode, which the oracle uses when a
run selects Wuji (see Hands).

`release_status = "provisional"`: a maintainer's solvability review and agent-trial calibration are pending
(PROTOCOL §4). The agent's time limit is each task's own `[agent] timeout_sec` (3600 s in both modes).

## Strict success and failure

Every family follows the same three rules, checked by the trusted runtime from simulator state:

1. **Fail-fast.** The first failure ends the episode and is permanent: a task object dropped, knocked off its support,
   below the table or support, outside its workspace, an invariant or guard violated, or unstable physics. Later rows
   are not executed, so nothing can recover a failure. The checks run at every physics substep, not only at control
   boundaries.
2. **No partial credit.** Success needs every ordered stage and the terminal (released or held) condition for its full
   window of consecutive samples; four of five layers, five of six debris pieces or a placed but still-held pot is a
   failure. Success ends the episode too.
3. **Judged by a trusted simulator, never claimed.** Privileged: the grader rebuilds the frozen scene with the
   recorded hand in fresh processes and replays only the motor targets; two replays must succeed with identical final
   state hashes. Standard: the sim service's own record of the episode it ran is the verdict (no replay; see
   "Standard-mode grading by the live episode" below). Success flags, object poses,
   configuration overrides or any other member of an agent's archive are never read.

## Hands

| id | model | finger actuators | source (pinned) | license | image path |
|---|---|---|---|---|---|
| `sharpa` (default) | Sharpa Wave | 22 | MuJoCo Menagerie `sharpa_wave` @ `0059d4335f8156206f63a35662313385f7ad6d74` (from Sharpa Robotics `6eea427eb24189519f32b9f21674cd534d3f973c`) | Apache-2.0 | `/opt/dexhand/hand` (`DEXHAND_ASSET_DIR`) |
| `wuji` | Wuji Hand 2.2 (`hand2/hand2_2`) | 20 | `wuji-technology/wuji-description` @ `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` | MIT | `/opt/dexhand/wuji_v2_2` (`WUJI_ASSET_DIR`) |

**Selection.** Privileged: `Session(task, hand="wuji")`, else the environment variable `DEXHAND_HAND`, else `sharpa`;
an unknown id is an error, never a silent fallback. Standard: `DEXHAND_HAND` on the `sim` service, read once at
start (the compose file passes `DEXHAND_HAND: ${DEXHAND_HAND:-sharpa}`, so `DEXHAND_HAND=wuji harbor run ...`
selects Wuji for a trial); `spec()["hand"]` names it, the agent cannot switch it, and the episode records it.

**Composition.** Each task's `hands.py` (`replace_wave_hands`) replaces each Sharpa Wave root body by a
fixed wrapper of the same name and pose and mounts the manufacturer's Wuji MJCF inside it with a rigid per-side
rotation that aligns fingers, palm normal and thumb side with the Wave's. Wave actuators, sensors, contacts and
equalities of the removed hand are dropped, Wuji names get the prefix `<side>_wuji_`, and Wuji actuators follow the
remaining (wrist or arm) actuators. Everything above the mount (wrist stage, arm joints, objects, task geometry,
physics options) is unchanged. Every Wuji file is checked against `images/dexhand/wuji-asset-manifest.json` (sha256 and
size) before composing. In the essential families the Wuji collision geoms are renamed to the predicate's roles
(`right_<finger>_...`, fingertip pads, `palm...`; meshes and contact parameters unchanged) so per-finger contact counts
mean the same for both hands; `hands.finger_of` takes the finger named first in a link name (`r_ring_finger_middle` is
the ring finger's middle phalanx, not the middle finger).

**Row layouts.** Wrist-stage families: Sharpa 28 = `wrist_x, wrist_y, wrist_z` (m), `wrist_rx, wrist_ry, wrist_rz`
(rad, serial XYZ joints) + 22 finger targets in native order (`right_thumb_CMC_FE ... right_pinky_DIP`); Wuji 26 = the
same six wrist targets + `r_wuji_r_THJ0..3, r_wuji_r_FFJ0..3, r_wuji_r_MFJ0..3, r_wuji_r_RFJ0..3, r_wuji_r_LFJ0..3`.
Dual-arm families: the 14 arm joint targets (left J1-J7, right J1-J7), then the left hand's and the right hand's finger
targets (22 each for Sharpa, 20 each for Wuji). `Session.actuator_names` (privileged) and
`spec()["action_types"]["joint_position"]["layout"]` (standard) give the exact order. Finger targets are radians
within `model.actuator_ctrlrange`. Each family declares its Wuji reset finger pose (or neutral fingers); the Sharpa
reset is the accepted episode's, bit for bit.

**Archive and rejections.** `/app/output/trajectory.npz` holds `actions` (finite numeric `(T, width)`), `hand`
(0-d string; absent = `sharpa`) and optionally `task` and `actuator_names`, written by `Session.save_trajectory`.
The archive file may be at most 64 MB (`tests/grade.py` checks the size before any replay; one number in every
family), so save it compressed (`numpy.savez_compressed`; `save_trajectory` does): uncompressed, the longest allowed
sweep_dustpan episode (160,000 rows of 58 float64 targets) is 74.2 MB. Members are read by exact name with
`allow_pickle=False` after header and payload checks. A width that does not match
the hand, an unknown or ambiguous hand label, a task or actuator-name mismatch, NaN or infinite values, object arrays,
pickles, malformed headers, too many rows and out-of-range targets (and, in the essential families, any change of the
locked wrist targets beyond float32 rounding) give reward 0 with `bad_trajectory = 1`, never an infrastructure error;
rows are never padded, truncated or converted between hands. A missing file is reward 0 with
`missing_trajectory = 1`.

**Wuji acceptance.** In every family, the Wuji scene composes from the image's assets in both
modes, a no-op scores 0, and short hold or seeded replays are deterministic in fresh processes. Wuji trajectories are
graded exactly like Sharpa ones.

**Wuji reference solutions.** A family may carry a successful trajectory for a hand other than the default one
next to its Sharpa solution, as `solution/<hand>/trajectory.npz` (or `trajectory.json` with parts below 2 MB) of both
task directories (the archive's `hand` is that hand, rows of that hand's width, the family's task and row limit),
next to unchanged copies of the shared oracle runner and `solution_parts.py`; that pair's `solve.sh` then picks the folder of the selected hand
(privileged: `DEXHAND_HAND` in the oracle's environment, default `sharpa`; standard: the sim service's
`spec()["hand"]`). Other hands, and every family without such a folder, keep the Sharpa oracle unchanged (the
single-hand `solve.sh`, byte for byte): with Wuji selected, its privileged oracle still hands in the Sharpa rows
(graded as a Sharpa episode) and its standard oracle stops at the hand check (reward 0). Eleven families package a
Wuji success, each made from motor targets only by an authoring script (not in this repository) that rewrites the
identical rows; float64 replays are bit-deterministic, so rows after the
success are never needed (the six essential ones end exactly at success; float32-rounded rows succeed at the same
control except for `essential_two_object` and `essential_pen_regrasp`, which need the float64 rows the oracles send):

| Family | Wuji rows | success at | method |
|---|---|---|---|
| `essential_cube_layer` | 940 x 26 | control 940 | thumb pad drags the layer about its axis, lifting and landing again |
| `essential_held_joystick` | 146 x 26 | control 146 | thumb on the stick cap, then thumb targets from short physics rollouts |
| `essential_pen_regrasp` | 1,571 x 26 | control 1,571 | five beam searches over finger-target segments; thin margins: stage-2 pen angle 0.913 rad (window up to 0.92), hold speed 0.057 (limit 0.06); float32 rows do not complete the hold |
| `essential_two_object` | 266 x 26 | control 266 | physics-shooting MPC rotates and returns walnut A, then a two-via-point release while ring and pinky keep B; thinnest margin: `b_finger_contacts` at its minimum 1 for a few substeps; float32 rows do not complete the release |
| `essential_rotary_gait` | 1,498 x 26 | control 1,498 | index and middle fingers on antiphase joint-space orbits; thin margin: final angle 0.080 rad above the terminal window's lower bound |
| `essential_cube_reorient` | 165 x 26 | control 165 | cross-entropy search over finger targets on model copies; thin margins: peak object speed 10.5 (limit 12), displacement 0.0615 m (limit 0.07 m) |
| `assemble_hamburger` | 5,847 x 26 | control 5,847 | pinch IK over wrist, thumb and index, per-layer parameters |
| `paper_half_fold` | 620 x 26 | control 554 | fingertip pads under the overhang, rigid rotation about the fold line, press, lift |
| `pot_shelf_transfer` | 8,266 x 54 | step 8,266 | the Sharpa authoring controller's phases with a Wuji power-grip posture |
| `jar_lid_open` | 1,242 x 54 | control 1,097 | the old Wuji hand path tracked by the arm, slowed for the Wuji servos |
| `tray_glass_carry` | 1,148 x 52 | control 1,028 | the Sharpa controller's waypoints with a deeper 30-35 mm hook insertion |

**Wuji start states that differ from the Sharpa start.** Two families need a Wuji-specific start because the Sharpa
start cannot be held by the Wuji geometry; only hand joints (and, where physically necessary, the held objects' start
poses) differ, found by closing the Wuji fingers in physics; the task, predicate and fail-fast rules are unchanged:
- `essential_two_object`: its `wuji_reset.json` (in the task's `environment/`) declares the Wuji finger targets and
  both walnuts' start poses in the Wuji grasp (`initial_objects`; formed by releasing the walnuts above the open hand
  while the fingers close). Walnut B's (and A's) reference pose is its pose after the reset settle, as for Sharpa. The
  start holds both walnuts for 60 s of hold actions; a searched open-loop finger controller completes stage 1.
- `sweep_dustpan`: `assets/reset_wuji.npz` keeps every arm, tool, debris and bristle coordinate and every arm target of
  the frozen start and declares only the 40 Wuji finger joints and targets (closed onto the frozen shafts); holding
  them keeps both tools for the full 80 s horizon.

A family may still offer fewer hands (`task.toml` `hands`, and `offered_hands.json` beside `hands.py` in the task's
runtime); none of the families does. Such a task's
instruction and README offer no other hand; `Session(..., hand="wuji")` (or `DEXHAND_HAND=wuji`) raises `HandError`;
a standard service started with `DEXHAND_HAND=wuji` starts no episode (`final.json` reason `hand_not_offered`,
`infra_error = 1`: the runner's misconfiguration, not the agent's failure); a privileged archive labelled `wuji` is a
`bad_trajectory` (reward 0).

## Robot and assets

The wrist-stage families mount the right hand (root body `right_hand_C_MC`, site `wrist_site`) on three prismatic and
three serial revolute joints, position actuated under native force bounds: a positioning mechanism that isolates
dexterous contact control from arm reachability, not a model of a commercial arm. The six essential families lock
all six wrist joints with native equality constraints. The dual-arm families use the accepted scenes' Tianji Marvin
base with two seven-joint arms (arm meshes: DexForce `embodichain_data` `TianjiMarvin.zip`, Apache-2.0; inertias from
Genesis' `dual_arms_primitives.urdf`, MIT; `images/dexhand/tianji/NOTICE.md`).

The image `ghcr.io/mll-lab-nu/efe:dexhand-<version>` (`images/dexhand/`, tag from `images/dexhand/VERSION`) contains MuJoCo 3.4.0,
numpy, scipy, imageio and OSMesa (`images/dexhand/requirements.txt`) and bakes the three asset sets: Sharpa Wave at
`/opt/dexhand/hand`, the Wuji physics subset at `/opt/dexhand/wuji_v2_2` and the Tianji meshes at `/opt/dexhand/tianji`
(`TIANJI_ASSET_DIR`). `python3 images/dexhand/prepare_assets.py` fetches all three from their pinned public sources
into the ignored `images/dexhand/assets/` and checks every file against `asset-manifest.json`,
`wuji-asset-manifest.json` and `tianji-asset-manifest.json` (the Tianji meshes are rebuilt by the pinned conversion
`images/dexhand/tianji/tianji_model.py` and must match byte for byte). Task code is not in the image: each task
directory carries its own runtime copy. No asset, policy or demonstration is downloaded at run time, and the image
holds no reference trajectory.

**Arm rig.** `arm_rig.py` (`mount_marvin`, in the task directories of the families that use it) replaces a family's floating
wrist stage by the Tianji Marvin stand of `pot_shelf_transfer` / `sweep_dustpan`: the same two seven-joint arms
(kinematics, inertias, meshes, joint limits, damping, armature, contact excludes, position servos kp 700 / kv 48 with
force limits 108/108/66/66/18/18/18 N m) with a hand on each flange (robot id `marvin-bimanual-sharpa-wave`;
`DEXHAND_HAND=wuji` swaps both hands for the Wuji Hand 2.2). One row holds the 14 arm joint targets (left arm J1-J7,
then right arm J1-J7), then the left hand's and the right hand's finger targets (Sharpa 14 + 22 + 22 = 58, Wuji 14 +
20 + 20 = 54), the layout of `pot_shelf_transfer`. Both arms and both hands are always present: a one-hand task keeps
the other arm parked (`arm_rig.PARK`, hanging beside the torso, its hand idle). The stand stands on the scene's floor
without passing through furniture; each family's section names its stand pose. The arm rows
of wrist-stage episodes come from authoring tooling (damped-least-squares IK, forward kinematics of the old wrist
stage, closed-loop tracking) that is never copied into a task; every packaged oracle replays open loop.

## World-frame facts in instructions

DexHand instructions state the frozen static layout of each scene in world coordinates (metres, z up): the locked
wrist pose of the essential families, table-top height and edge, support, shelf and target positions, an object's
initial extent, fold lines, workspace boxes and every threshold of the success and failure predicates. They never
state an object's state after reset beyond what the frozen instance fixes, nor any planned motion. The same rule
holds in both modes; in standard mode the agent measures everything else through cameras, depth, its own joints and
forward kinematics.

## Essential dexterity families

Six fixed-wrist scenes isolate finger control. Each family's `scene.py`, packaged assets, oracle (`solution/`) and
`wuji_reset.json` are in its task directories; its full specification is each task's `instance.json` and
`catalog.json`.

All six wrist targets are locked; the runtime rejects any row that changes them (float32 wire rounding is accepted
and normalized). Finger targets keep the manufacturer's joint and force limits; Sharpa velocity feedback is
dissipative with its coefficient frozen in the instance. Objects have no motors, welds, attachments, compensating
forces or scripted motion. Features are computed from MuJoCo state, contact pairs and contact forces by
each task's `checker.py`: ordered stages with consecutive holds, guards while a stage is active, global invariants and a
terminal hold. A stage or the terminal hold counts a control sample only if its bounds held at every 2 ms substep of
that control interval; stages complete in order and a stage cannot use the sample that completed the previous one;
missing or non-finite features fail closed; the first violated invariant or guard, a non-finite feature or unstable
physics fails the episode immediately and permanently; success ends the episode at the end of the terminal hold. The
instructions render the exact predicate and define every feature (`force`: largest contact force on any task object,
N; `speed`: largest task-object velocity, m/s or rad/s; `palm_drift` / `wrist_rotation`: palm motion from reset;
`support`: object-environment contacts; contact counts in fingers). The bounds below are the frozen instances' (six
significant digits).

### `essential_cube_layer` (free-held cube layer reversal)
A free cube with a passive top-layer hinge above a rigid two-layer base (a one-face abstraction, not a six-face
puzzle): turn only the top layer +90°, return it to zero, turn it +90° again, keeping the free body stable with other
fingers and no external support.

1. `quarter_turn`: `1.4508 <= top_turn <= 1.6908`, `1 <= base_contacts <= 5`, `1 <= mechanism_contacts <= 5`; 5 consecutive controls.
2. `return_zero`: `-0.12 <= top_turn <= 0.12`, `1 <= base_contacts <= 5`, `1 <= mechanism_contacts <= 5`; 5 consecutive controls.
3. `repeat_quarter_turn`: `1.4508 <= top_turn <= 1.6908`, `1 <= base_contacts <= 5`, `1 <= mechanism_contacts <= 5`; 5 consecutive controls.
4. Terminal hold: `1.4508 <= top_turn <= 1.6908`, `1 <= base_contacts <= 5`, `0 <= speed <= 0.12`; 15 consecutive controls.

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 20`, `0 <= palm_drift <= 0.006`, `0 <= wrist_rotation <= 0.035`, `support == 0`, `0 <= body_drift <= 0.02`, `0 <= body_rotation <= 0.35`. Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

### `essential_held_joystick` (held Joy-Con thumbstick sequence)
A free right Joy-Con (80 % scale, about 81 x 29 x 25 mm, three convex shell pieces) with a passive spring-centred
thumbstick: left, front, right, back, centre, measured as joint angles relative to the shell, with the controller held
steady.

1. `left`: `-0.4 <= joystick_x <= -0.2`, `-0.1 <= joystick_y <= 0.1`, `1 <= base_contacts <= 5`; 5 consecutive controls.
2. `front`: `-0.1 <= joystick_x <= 0.1`, `0.2 <= joystick_y <= 0.4`, `1 <= base_contacts <= 5`; 5 consecutive controls.
3. `right`: `0.2 <= joystick_x <= 0.4`, `-0.1 <= joystick_y <= 0.1`, `1 <= base_contacts <= 5`; 5 consecutive controls.
4. `back`: `-0.1 <= joystick_x <= 0.1`, `-0.4 <= joystick_y <= -0.2`, `1 <= base_contacts <= 5`; 5 consecutive controls.
5. `center`: `-0.1 <= joystick_x <= 0.1`, `-0.1 <= joystick_y <= 0.1`, `1 <= base_contacts <= 5`; 5 consecutive controls.
6. Terminal hold: `-0.08 <= joystick_x <= 0.08`, `-0.08 <= joystick_y <= 0.08`, `1 <= base_contacts <= 5`, `0 <= speed <= 0.12`; 15 consecutive controls.

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 20`, `0 <= palm_drift <= 0.006`, `0 <= wrist_rotation <= 0.035`, `support == 0`, `0 <= body_drift <= 0.02`, `0 <= body_rotation <= 0.35`. Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

### `essential_pen_regrasp` (palm-to-tripod pen regrasp)
A free 150 mm x 12 mm ballpoint pen (Paper Mate source mesh, fitted capsule shaft and convex tip and tail) resting on
the central palm within 10° of horizontal: advance it 30 mm along its initial axis, turn its axis by 45° and hold its
30 mm grip band with thumb, index and middle fingertips, clear of the central palm. Other finger links may give
auxiliary contact.

1. `advance_pen`: `0.024 <= pen_axial <= 0.036`, `0 <= pen_angle <= 0.2`, `2 <= contacts <= 5`; 5 consecutive controls.
2. `turn_and_tripod_grip`: `0.024 <= pen_axial <= 0.036`, `0.65 <= pen_angle <= 0.92`, `3 <= pen_grip_contacts <= 5`, `contact_thumb == 1`, `contact_index == 1`, `contact_middle == 1`, `pen_palm_contacts == 0`, `pen_grip_thumb == 1`, `pen_grip_index == 1`, `pen_grip_middle == 1`; 5 consecutive controls.
3. Terminal hold: `0.024 <= pen_axial <= 0.036`, `0.65 <= pen_angle <= 0.92`, `3 <= pen_grip_contacts <= 5`, `contact_thumb == 1`, `contact_index == 1`, `contact_middle == 1`, `pen_palm_contacts == 0`, `0 <= speed <= 0.06`, `pen_grip_thumb == 1`, `pen_grip_index == 1`, `pen_grip_middle == 1`; 25 consecutive controls.

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 12`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `support == 0`, `0 <= object_displacement <= 0.07`, `0.18 <= object_height <= 0.6`, `object_hand_contacts >= 1`, `pen_initial_palm_contacts >= 1`, `0 <= pen_initial_horizontal_error <= 0.174533`. Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

### `essential_two_object` (independent walnut rotation and selective release)
Two scanned walnuts (28 mm maximum extent, convex collision hulls of at most 64 vertices): turn walnut A +90° about
palm-local Y, return it, then release only A into the catch tray, while B stays in place and held and the walnuts never
touch. Both hands; the Wuji start (`wuji_reset.json`) holds both walnuts in the Wuji grasp.

1. `rotate_a_keep_b`: `0 <= a_quarter_turn_error <= 0.16`, `1 <= a_finger_contacts <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls. While active (fail-fast): `a_hand_contacts >= 1`, `a_support == 0`, `0 <= a_position_error <= 0.035`, `0 <= speed <= 12`.
2. `return_a_keep_b`: `0 <= a_orientation_error <= 0.16`, `1 <= a_finger_contacts <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls. While active (fail-fast): `a_hand_contacts >= 1`, `a_support == 0`, `0 <= a_position_error <= 0.035`, `0 <= speed <= 12`.
3. `release_a_only`: `a_hand_contacts == 0`, `deposit_support_a >= 1`, `0 <= a_deposit_distance <= 0.04`; 5 consecutive controls. While active (fail-fast): `0 <= a_linear_speed <= 2.5`, `0 <= a_angular_speed <= 80`.
4. Terminal hold: `a_hand_contacts == 0`, `deposit_support_a >= 1`, `0 <= a_deposit_distance <= 0.04`, `1 <= b_finger_contacts <= 5`, `0 <= speed <= 0.06`; 25 consecutive controls.

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `ball_pair_contacts == 0`, `0 <= b_position_error <= 0.015`, `0 <= b_orientation_error <= 0.2`, `b_support == 0`, `b_hand_contacts >= 1`, `1 <= b_finger_contacts <= 5`, `0 <= a_linear_speed <= 2.5`, `0 <= a_angular_speed <= 80`, `0.135 <= a_height <= 0.6`, `0 <= a_deposit_distance <= 0.1`. Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

### `essential_rotary_gait` (multi-turn encoder knob)
A real rotary-encoder cap (about 53.7 mm diameter, 15 mm thick) on a passive unlimited-turn hinge with bearing friction
in a stationary panel: turn it to +720°, reverse to +360° and hold it still, with load-bearing contact throughout and
at least four finger handoffs (a new finger set sharing a finger with the previous one, stable for 40 ms).

1. `two_forward_turns`: `12.4464 <= turn <= 12.6864`, `rotor_handoffs >= 4`, `1 <= rotor_fingers <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls.
2. `one_reverse_turn`: `6.16319 <= turn <= 6.40319`, `1 <= rotor_fingers <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls.
3. Terminal hold: `6.16319 <= turn <= 6.40319`, `1 <= rotor_fingers <= 5`, `0 <= speed <= 0.06`; 25 consecutive controls.

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 12`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `rotor_hand_contacts >= 1`. Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

### `essential_cube_reorient` (multi-axis marked-sphere reorientation)
A free sphere with asymmetric direction markers (the family id is kept from its cube prototype): +90° about
palm-local Y, then +90° about palm-local X from that pose, then back to the initial orientation, with at least two
fingertips at every checkpoint.

1. `first_axis_quarter_turn`: `0 <= cube_error_1 <= 0.16`, `2 <= contacts <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls.
2. `second_axis_quarter_turn`: `0 <= cube_error_2 <= 0.16`, `2 <= contacts <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls.
3. `return_to_initial`: `0 <= cube_error_3 <= 0.16`, `2 <= contacts <= 5`, `0 <= speed <= 0.25`; 5 consecutive controls.
4. Terminal hold: `0 <= cube_error_3 <= 0.16`, `2 <= contacts <= 5`, `0 <= speed <= 0.06`; 25 consecutive controls.

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 12`, `0 <= palm_drift <= 0.003`, `0 <= wrist_rotation <= 0.01`, `support == 0`, `0 <= object_displacement <= 0.07`, `0.18 <= object_height <= 0.6`, `object_hand_contacts >= 1`. Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

**Oracles.** Each family's `solution/trajectory.npz` (rotary gait: `trajectory.json` with two parts under 2 MB,
concatenated and sha256-checked) is the validated Sharpa actuator trajectory of the frozen instance.
It matches the recorded evidence (archive hash, Sharpa model hash, two fresh
replays ending in the validated final state hash, and success of the float32-rounded rows). All six also carry a
Wuji oracle, `solution/wuji/trajectory.npz` (see
Wuji reference solutions). The Wuji resets are declared in
`wuji_reset.json` (pen, knob, walnuts: finger targets, for the walnuts also their start poses) or neutral (cube,
Joy-Con, sphere rest on the neutral Wuji hand).

## Hamburger assembly (`assemble_hamburger`)

The bottom bun starts on the plate; patty, cheese,
tomato, lettuce and the sesame top bun start on preparation supports. **Success**, all at the same time: every
ingredient centre within 12 mm horizontally of the plate centre, every layer upright within 0.22 rad, heights strictly
increasing in the order bottom bun, patty, cheese, tomato, lettuce, top bun, all five consecutive pairs in physical
contact and the bottom bun touching the plate; then released: no hand contact on any ingredient, every ingredient
slower than 0.025 m/s and 0.25 rad/s, the whole condition for 100 consecutive controls (2 s). Success ends the episode;
a partial stack never counts. **Immediate failure**, checked after every 2 ms substep: an ingredient touches the table
top or the floor (`ingredient_dropped`), an ingredient body falls below the table top (z < 0.30 m), an ingredient
leaves the box x in [-0.64, 0.64] m, y in [-0.52, 0.52] m, z in [0.30, 0.80] m, a cheese or lettuce bending angle
exceeds 0.65 rad, unstable physics, or 7,500 controls (at 50 Hz) without success.

Cheese and lettuce are three passive elastic strips each; the other ingredients are rigid cylinder contacts with
original decorative geometry. No continuum food elasticity, tearing or crushing is modelled. Oracle: the 6,090-row
Sharpa witness (privileged; success at control 5,794) and the 5,793-row standard episode; with Wuji, the 5,847-row
Wuji episode in both modes (`solution/wuji/`, success at control 5,847). Wuji Hand 2.2 mounts on the
same wrist stage (26-wide rows, fingers at 0).

## Paper half-fold (`paper_half_fold`)

The accepted T06 scene. A 160 x 100 mm, 1.28 g sheet lies
flat on the table at z = 0.3012 m (x from 0 to 0.16 m, y from -0.05 to 0.05 m; 9 x 5 vertices, 20 mm by 25 mm
spacing); the half with x <= 0.08 m is glued to a backing next to a dark clamp, the free half overhangs the table edge
(x = 0.135 m) by 25 mm. Fold line x = 0.08 m.
**Success**: 100 consecutive 50 Hz samples (2 s) with no hand-paper contact and fold angle of the free half above
2.6 rad, mean plastic crease on the centre line above 2.2 rad with at least 90 % of its hinges above 2.2 rad, free edge
within 18 mm of the fixed edge, stretch below 8 %, and the whole sheet over the table top: every vertex within
x from -0.345 to 0.135 m, y from -0.30 to 0.30 m and at z >= 0.298 m (2 mm tolerance). Success ends the episode. **Immediate
failure**, checked every 0.5 ms: a vertex more than 10 mm below the table top (z < 0.29 m), a vertex outside the
workspace box x from -0.03 to 0.19 m, y from -0.09 to 0.09 m, z <= 0.45 m, stretch above 8 %, unstable physics, or 1,500 controls
(30 s) without success. A fold that springs back, a crease that is not permanent or a hand still touching the paper
is not a success.

The paper is a passive elastic/plastic shell (hinges bend elastically up to 0.5 rad beyond their rest angle, then
yield; effective thickness 0.7 mm), a reduced model with uncalibrated material parameters. The frozen compiled-model
XML compiles to the accepted model byte for byte (checked at every session start): 0.5 ms implicitfast, 40 substeps
per control. The packaged oracle (1,108 accepted rows plus 250 copies of the last row, which float32 transport needs
to finish the hold one control later and which a float64 replay never executes) reproduces every control-boundary
state of the accepted episode exactly. The Wuji oracle (`solution/wuji/`, 620 rows) succeeds at control 554: the
fingertip pads slide under the overhang and the hand turns rigidly about the fold line.

## Sweeping into a held dustpan (`sweep_dustpan`)

The accepted T13 scene. A fixed Tianji Marvin base with two
seven-joint arms: the right hand holds a free broom (54 passive bristle-bundle hinges), the left hand a free dustpan
whose entrance ramp rests on the floor (z = -0.10 m) next to six free rigid debris pieces. One row sets every motor
target for one 0.5 ms physics step (2000 Hz), because the accepted controls change at every step; at most 160,000 rows
(80 s). **Success**: 2000 consecutive steps (1.0 s) in which, in the dustpan's frame, every collision shape of all six
pieces lies over the pan floor (at least 1 mm inside its 460 mm width, inside its 262 mm depth, no lower than 1 mm below
the top of the floor plate and no higher than 110 mm above the pan origin), all six pieces touch the pan (at least
1 mN), the pan origin is at least 50 mm above the floor, every piece moves slower than 0.03 m/s and 0.8 rad/s, and
every piece has been touched by the bristles. **Immediate failure**: a piece leaves the floor work area (x outside
[0.45, 1.00] m, y outside [-0.50, 0.40] m, or its centre more than 0.25 m above or 0.01 m below the floor), any robot
part touches debris with at least 1 mN, from 1.2 s on fewer than two collision parts of a tool's own hand press on its
handle with at least 0.01 N each or the handle's grip point moves more than 25 mm or turns more than 0.25 rad relative
to that palm since 1.2 s (dropped or slipping tool), a tool pressed (more than 0.01 N) by any robot part other than its
own hand, arm, torso or cross-hand collisions, or unstable physics. Five of six pieces, an unlifted pan or a hold
shorter than 1 s is not a success.

The oracle is the accepted 132,521-row Sharpa trajectory plus 16,000 copies of its last row (an 8 s hold that only
adds margin; stored as five sha256-checked parts under 2 MB); it reproduces the accepted run bit for bit and succeeds
after 132,392 steps. Its float32-rounded rows fail (the tool grip slips), so the standard oracle submits float64 rows;
an agent's controls must not depend on the last bits either. Wuji Hand 2.2: the start keeps the frozen
arm/tool/debris state and closes the Wuji fingers on the same shafts (`assets/reset_wuji.npz`; see Hands); no Wuji
solution is claimed. Simulating one second costs a few seconds of CPU; the standard
service renders frames with OSMesa, so agents should keep `video_fps` low.

## Pot-to-shelf transfer (`pot_shelf_transfer`)

The accepted T17 scene. Two Tianji Marvin seven-joint
arms on a fixed stand with a Sharpa Wave hand on each wrist lift a free 1 kg two-handle stockpot off a worktop (top
z = 0.75 m), carry it into an open kitchen shelf (board top z = 0.79 m), set it down upright at the target, release and
withdraw. The pot (286 mm vessel diameter, 438 mm across its loop handles) starts upright with its base centre at
(0.52, -0.05, 0.75). One row is one 2 ms physics step (500 Hz). The accepted trial-14 MJCF is frozen byte for byte (mesh paths
resolved to the image's hash-checked Sharpa and Tianji assets). **Success**, both stages in order: (1) bimanual carry,
at least 0.5 s in total (250 steps) with the pot base above z = 0.785 m, no worktop or shelf load, and each hand pushing
it upward with at least 0.5 N; (2) released on the shelf for 2.0 s (1,000 consecutive steps): base centre within 0.04 m
horizontally of (0.46, 0.31) and within 0.012 m of z = 0.79, axis within 0.10 rad of +z, slower than 0.03 m/s and
0.15 rad/s, the shelf board bearing it with nothing else touching, the vessel footprint (radius 0.143 m) on the board,
every part of the pot inside the bay and at most 0.05 m in front of the board's front edge at y = 0.12 (y >= 0.07: a
50 mm open-front allowance, because the 438 mm handle span reaches about 34 mm past the front edge at the target; side
walls, back wall and top board are strict),
and every hand collision surface at least 0.04 m from the pot. Success ends the episode. **Immediate failure**, the only early failures ("touches" means at least 0.02 N):
1. the pot base below z = 0.70 m;
2. the base outside x in [-0.10, 1.10] m, y in [-0.50, 0.85] m, z <= 1.45 m;
3. the axis more than 0.5 rad from +z;
4. a downward speed above 0.6 m/s, or no contact at all for more than 0.06 s (30 steps);
5. the pot touching anything but the two hands, the worktop and the shelf board;
6. a robot link touching furniture or floor, or two robot parts colliding (contacts within one hand excepted);
7. hand-pot penetration above 3 mm;
8. a joint more than 0.005 rad past its range;
9. unstable physics;
10. 30,000 rows (60 s) without success.

Setting the pot back on the worktop, re-contact and regrasping are allowed; the 0.5 s carry is
counted over the whole episode, the 2 s hold must be consecutive.

The packaged oracle (the 8,850 accepted rows) reproduces every recorded state exactly and succeeds at row 8,602 (the
remaining rows are not executed). The accepted release lets the pot drop about 13 mm (0.499 m/s peak, below the
0.6 m/s limit). Wuji Hand 2.2 composes on the same arm mounts (54-wide rows, neutral fingers); its packaged oracle
(`solution/wuji/`, 8,266 rows) completes the hold at its last row with both hands bearing the pot during the carry.

## Wave-2 household scene families

Twenty families (the scene-expansion scene id is in each heading) turn
household scenes that were kinematic demonstrations (object motion prescribed, mostly without hands) into physical
tasks: a hand on the six-DoF wrist stage, two hands on two six-DoF wrist stages (`tray_glass_carry`,
`vacuum_bin_reseat`), or the Tianji Marvin arms of the arm rig above with a hand on each
flange (`batter_whisk`, `book_page_turn`, `grinder_crank`, `picture_hang` with both arms; `bicycle_pump_stroke`,
`boot_sole_brush`, `coffee_stir`, `envelope_letter_insert`, `jar_lid_open`, `pancake_serve`, `paper_staple`,
`remote_battery_swap`, `usb_plug_insert` with the right arm, the left one parked) completes each one with motor targets
only. Mechanisms are passive joints with limits, damping, friction loss and springs (hinges, slides, detents, latches);
nothing is welded to a hand, scripted or pushed, and object state is written only at reset. A medium that is not
simulated (coffee, batter, air, the liquid in a glass) is summarised by a quantity the checker derives from simulator
state (revolutions, strokes, tilt), and the instruction says so. The three rules above apply: fail-fast at the first
violating physics substep (unless the section says otherwise), ordered stages, no partial credit, and a released or held
terminal window. Each instruction states the exact predicate and every threshold. All run at 50 Hz (10 x 2 ms), `oracle =
"full"` (a recorded physical Sharpa episode), with Wuji selectable; a Wuji success, where one exists, is packaged as
`solution/wuji/` (see Hands). The families whose sections say "Wave 3" keep the source scene's details (no pre-closed or
pre-placed parts, enlarged parts or widened clearances), each section naming what was restored and what remains, with
the reason.

### TV remote battery replacement (`remote_battery_swap`, T07)

Wave 3: the right Tianji Marvin arm and hand (stand at base (-0.45, 0.15, -0.45) facing +x, the left arm parked). Layout
change for this hand-scale scene: the floor is lowered with the stand to z = -0.55 m, so the source's 0.30 m table top
stands 0.85 m above the floor. A TV remote at the source size (shell 160 x 64 mm) lies on the table; its sliding battery
door (a passive slide, 85 mm travel) is shut and latched over a one-cell compartment holding an old gray AA cell: a
spring-loaded thumb tab on the door (5 mm, 120 N/m) carries a hook in front of a fixed latch stop, so the door slides
only while the tab is pressed; a new green AA cell lies on the table next to an empty receiving tray. **Success**, in
order: (1) the latch released and the door at least 0.060 m open; (2) the gray cell resting on the tray floor (centre
inside the tray's inner box |x| <= 0.037 m, |y| <= 0.032 m, at most 0.014 m above the tray origin, no hand contact); (3)
the green cell seated with correct polarity (centre within 5 mm along, 3 mm across and 2 mm in height of the slot
centre, on both cradle ribs, axis within 10 degrees of the remote's long axis, + end at the gold contact); (4) the door
shut and latched (at most 0.002 m open, tab released); then, with no hand contact on any task object and every object at
rest (<= 0.02 m/s, <= 0.5 rad/s), the condition held for 50 controls (1 s). **Immediate failure**, after every 2 ms
substep: a cell, the door, the remote or the tray below the table top or outside the workspace box, or on the floor; the
remote or the tray slid more than 0.03 m or tilted more than 15 degrees; the gray cell touching the table top; the green
cell touching the table again after it was lifted; a cell without hand contact falling faster than 0.886 m/s, or a cell
touching nothing falling faster than 0.5 m/s (no grace period); unstable physics; 6,000 controls. Wave 3 restored the
source size (the shell was widened 1.25 times) and the door latch (the door was held by friction only). Remaining
deviation: the compartment's compressible - spring (80 N/m in the source) is replaced by fixed terminals with 3 mm play;
a spring version was not attempted. Oracle: 2,416 Sharpa rows on the arm (success at 2,266); no Wuji solution.

### Stir milk into coffee (`coffee_stir`, T11)

Wave 3: the right Tianji Marvin arm and hand (stand at the world origin facing +x, its plate on the floor z = -0.1 m;
the left arm parked). A 300 g mug (inner radius 50 mm, 100 mm tall) stands on the worktop (top z = 0.75 m), filled with
coffee to 64 mm (milk already poured). As in the approved source film, the episode starts with the 35 g teaspoon (181.7
mm, 24 x 46 mm bowl) held upright, bowl down, in a thumb-index pinch of the right hand just above the rim (a physical
contact grasp made at reset, no weld; with Wuji, which has no start grasp yet, the spoon leans in the mug). The coffee
is a visual surface only: mixing is measured as stirring. **Success**, in order: (1) the spoon in the hand (thumb and
another finger touching it) with the bowl submerged (centre and both bowl ends below the surface, above the mug floor,
within 50 mm of the axis); (2) while submerged, at least 8 mm off the axis and in the hand, the bowl centre's unwrapped
angle about the mug axis accumulates six revolutions (the source's six turns; steps above 0.785 rad per control are
ignored, and the count restarts when the bowl leaves the coffee); (3) the spoon laid on the worktop as in the film's
end: released, touching the worktop and not the mug, bowl and handle end at least 0.10 m from the mug axis, within 15
degrees of horizontal, spoon and mug at rest (<= 0.02 m/s, <= 0.5 rad/s) for 50 controls (1 s). **Immediate failure**,
after every 2 ms substep: mug tilt above 10 degrees, slide above 20 mm or lift above 5 mm; the spoon on the floor, or on
the worktop before the six turns; touching neither hand, mug nor worktop while falling faster than 0.2 m/s; a spoon
point more than 3 mm below the worktop top; leaving the workspace box; a fingertip in the coffee; an arm link, the stand
or the parked hand touching the mug, spoon or worktop; unstable physics; 3,000 controls. Wave 3 restored the film's
start, its six turns and its end (the spoon laid down; the wave-2 task started with the spoon leaning in the mug,
stirred three turns and left it there). Not restored: picking the spoon up from the worktop (a 5.4 mm shaft lying flat
cannot be pinched by the 16-19 mm fingertip pads; the film itself starts with the spoon held). Oracle: 1,882 Sharpa rows
on the arm (success at 1,802); no Wuji solution.

### Jam jar lid (`jar_lid_open`, T14)

Wave 3: the right Tianji Marvin arm and hand (stand at base (-0.56, 0.08, 0) behind the worktop on the floor z = -0.1 m,
the left arm parked); layout change: the worktop is raised to a real table height (top z = 0.75 m; it was 0.30 m on the
wrist stage) and widened to |y| <= 0.58 m so that its legs clear the stand's base plate; the jar stands at (-0.22,
-0.08). Nothing holds the jar (550 g, it stands on its weight and friction). The red twist-off lid (32 g) is closed by a
contact-only lug thread: four inclined glass ramps hold four lid lugs; after a 1.049 rad counter-clockwise turn the lugs
sit in the ramp gaps and the lid lifts off. **Success**, in order: (1) while the lid is still seated (origin < 6 mm
above its closed height, within 4 mm of the jar axis) its unwrapped counter-clockwise turn relative to the jar reaches
1.049 rad; (2) the lowest point of the lid skirt rises more than 30 mm above the rim; (3) for 50 consecutive controls (1
s) the lid rests on the worktop touching neither hand nor jar, upright within 0.15 rad, at least 90 mm from the jar
axis, slower than 0.02 m/s and 0.3 rad/s, while the jar stands untouched, upright within 0.10 rad and slower than 0.02
m/s. **Immediate failure**, after every 2 ms substep: jar tilt above 15 degrees, slide above 30 mm or lift above 15 mm;
the lid touching the worktop before stage 2; the lid in the air (lowest point more than 10 mm above the worktop)
touching nothing while falling faster than 0.3 m/s, or falling faster than 1.0 m/s whatever it touches (a lid tipping
over on the worktop has not dropped); floor contact or leaving the worktop or workspace; the lid leaving the thread upward
outside the ramp gaps; unstable physics; 3,000 controls. The lid is lightly closed (no vacuum, seal adhesion or
preload); the jam is part of the jar's rigid mass. Not restored, with evidence in the family README: a second hand
holding the jar (on the 67 mm body just above the worktop the holding palm could not be placed: forearm and wrist
against the worktop, J6/J7 limits; in exploratory runs, whose numbers were not archived, the best grips held only about
0.06-1.02 N m) and a seal breakaway torque of about 1-2 N m (without a holding hand, one hand would turn the whole jar,
which stands on about 0.13 N m of friction). Oracle: 1,159 Sharpa rows on the arm (success at 1,009); Wuji:
`solution/wuji/` (1,242 rows, success at 1,097).

### Manual coffee grinder (`grinder_crank`, T15)

A HARIO-style hand mill (0.40 kg: body, crank and knob; 174 mm tall, 26 mm base radius) stands free on the counter (top
z = 0.70 m). Its crank turns on a passive hinge about the mill axis with grinding resistance (0.08 N m dry friction,
0.012 N m s/rad damping); the knob spins on a free bearing at 80 mm crank radius. The mill is light and narrow: it tips
over if the crank is driven without holding the body, so two hands hold it and crank it: wave 3 puts them on both Tianji
Marvin arms (arm rig above; 58 / 54 controls), the left hand holding the cup and the right one cranking. The stand faces
+x behind the counter at base (-0.085, 0, 0) on the source floor (z = -0.1 m), its base plate 1 cm clear of the
counter's front legs (exact check: no robot geom overlaps furniture at reset or over the oracle); the wave-2 counterhold
is turned 90 degrees about the cup axis so the left hand grips from the robot's side (the same grasp on the rotationally
symmetric cup). **Success**, in order: the unwrapped crank angle relative to the body reaches 720 degrees net clockwise
(seen from above); then, with that still true, no hand touches the mill, its base rests on the counter, its axis is
within 10 degrees of vertical and it is still (<= 0.02 m/s, <= 0.2 rad/s, crank <= 0.5 rad/s) for 50 consecutive
controls (1 s). **Immediate failure**, after every 2 ms substep: tilt above 10 degrees; the base moved more than 2 cm
horizontally or lifted more than 2 cm, or below the counter top; the body turned more than 45 degrees about its axis;
the crank more than 90 degrees net counter-clockwise; an arm, torso or stand link touching anything (`robot_collision`);
unstable physics; 3,000 controls. Grinding is summarised by the crank angle (no beans or grounds). Oracle: 1,096 Sharpa
rows on the arms (success at 996); no Wuji solution is packaged (Wuji
selectable, no success).

### Pancake serving (`pancake_serve`, T16)

Wave 3: the right Tianji Marvin arm and hand (stand at the world origin facing +x, the left arm parked); layout change:
the cabinet under the counter starts behind the stand's base plate. The OXO flexible turner (a three-strip passive
blade) starts resting on the counter in front of the plate, as in the source, and is picked up first (wave 2: pre-held
in a frozen grasp); a rigid 60 g pancake lies in a free 22 cm pan and a free ceramic plate stands beside it. Physics
step 1 ms, 20 per control. **Success**, in order: (1) the pancake on the blade only, lifted at least 15 mm, tilt at most
30 degrees, for 10 controls; (2) carried on the blade over the plate (centre within 58 mm); (3) resting on the plate
only, centre within 58 mm, tilt at most 20 degrees, still (0.02 m/s, 0.3 rad/s), the turner withdrawn (no contact, blade
at least 80 mm from the centre), for 50 controls (1 s). **Immediate failure**, after every 1 ms substep: the pancake on
the counter or floor, or in free fall faster than 0.35 m/s; a hand touching the pancake; the turner on the floor or
falling out of the hand; pan or plate moved more than 30 mm or tilted more than 15 degrees; a body below the counter top
or outside the workspace; unstable physics; 3,000 controls. Rigid pancake, declared pair frictions (pancake-pan 0.45,
blade 0.20, plate 0.60). Any robot part touching the pancake fails at once (hand contact means any hand, arm link or the
stand). Not restored: the other hand holding the pan (one attempt failed; the source's 8-degree tilt and 4 cm lift of
the pan were not attempted). Oracle: 1,167 Sharpa rows on the arm (success at 1,017); no Wuji solution is packaged (Wuji selectable, no success).

### Vacuum dust-bin reseat (`vacuum_bin_reseat`, T19)

A handheld vacuum (free body) stands on the counter with its transparent dust bin (free body) held by two lower tabs on
ledges and a top spring latch: the tooth on the red release button (a passive spring slide) stops the bin's top catch
from tilting out, and a fixed lip over the catch bridge stops a straight lift, so the top must tilt out from under the
lip, which the tooth allows only while the button is pressed. Physics step 1 ms, 20 per control. Wave 3: two hands, each
on its own six-DoF wrist stage (56 / 52 controls; the left one the right Wave's mirror), because in the source the
second hand holds the vacuum body: closing the latch at the source friction needs a firm push. **Success**, in order:
(1) the button pressed by at least 5.8 mm while the bin is still seated (origin within 5 mm), then the bin origin more
than 30 mm from its seat (vacuum-body frame); (2) reinstalled: within 3 mm and 0.05 rad of the seated pose with the
button back up (<= 1.5 mm) and the catch behind the tooth face; (3) no hand contact on bin, vacuum or button, bin and
vacuum at rest (<= 0.01 m/s, bin <= 0.1 rad/s), for 50 consecutive controls (1 s). **Immediate failure**, after every 1
ms substep: the vacuum moved more than 50 mm or tilted more than 0.35 rad; the bin falling faster than 0.99 m/s (0.55
m/s while nothing touches it), touching floor or a table leg, below the counter top or outside the workspace box; bin
and vacuum interpenetrating by more than 4 mm; unstable physics; 3,000 controls. Wave 3 restored the source latch
friction (0.55, was 0.15), the source button travel (6 mm, was 7.5 mm) and the second hand. Kept: a base skid,
visual-only filter frame and lower lips, and the fixed lip over the catch bridge (without it the latch does not retain
the bin). Not on the arm: the underhand nozzle grasp needs the palm below the counter overhang, out of the Marvin arm's
reach, and an overhand grasp let the bin slip 40-100 mm. Oracle: 1,331 Sharpa rows (success at 1,181); no Wuji solution.

### Folding sweater dryer (`drying_rack_unfold`, T20)

An OXO-style folding sweater dryer (two 0.33 x 0.65 m frame halves joined by a passive pole hinge, four passive offset
legs with 100-degree stops, woven net visual only) starts fully folded and stored underside up on the kitchen counter.
**Success**, in order: unfolded (fold angle <= 0.1 pi, every leg >= 90 degrees); standing (also upright within 10
degrees, all four feet on the counter and no other rack part); released (also no hand contact, rack slower than
0.02 m/s and 0.2 rad/s) for 50 consecutive controls (1 s). **Immediate failure**, after every 2 ms substep: a rack part
below the counter top, off the counter footprint or more than 0.9 m above it; the rack touching floor or cabinet;
dropped (no counter and no hand contact while its centre of mass falls faster than 0.2 m/s, no debounce); after
standing, tilt above 20 degrees or a hinge leaving its open range; unstable physics; 6,000 controls. There is no leg
latch (an open leg stays open past its over-centre under load, as in the source); the leg pivot damping is raised to
0.03 N m s/rad and the counter lengthened to 1.5 m so the open rack can be turned over about a side rim. Oracle:
2,415 Sharpa rows (success at 2,315); no Wuji solution.

### Picture hanging (`picture_hang`, T21)

A free 2.0 kg, 52 x 52 x 6 cm framed print stands upright on a console (top z = 0.72 m) in front of a wall (face x =
0.74 m) with two brass hooks (saddles at z = 1.38 m, y = +-0.255 m: 12 mm saddle, 10 mm upturned lip); two D-rings (18 x
20 mm loops of 2 mm wire) hinge passively behind the side rails. Wave 3: both Tianji Marvin arms (arm rig above) work, a
hand on each flange: with `sharpa` the genuine right Sharpa Wave and its declared mirror image on the left flange, with
`wuji` the manufacturer's left and right Wuji Hand 2.2. The stand faces the wall at base (0.18, 0, 0.20) on a 0.10 m
plinth exactly under its base plate (the stand's floor moved with it: from the floor the 1.38 m hooks are 19-25 mm out
of reach); layout change: the console (top, height and the frame's start unchanged) stands on its two rear legs, moved
from x = 0.60 to 0.615 m, because the source's front legs (x = 0.40 m) would pass through the base plate (exact check:
no robot geom overlaps furniture at reset or over the oracle). The palms squeeze the top 9 cm of the side rails (the
Marvin wrist link is 28 mm proud of the palm). **Success**, in order: lifted (origin 2 cm above the start, no console
contact); both rings threaded on their own hooks (saddle through the D loop between lip and wall) and touching them;
then released for 50 consecutive controls (1 s): both threaded, each hook carrying >= 20 % of the weight and both >= 85
%, no hand, console or floor contact, level within 3 degrees, tilt <= 0.10 rad, slower than 0.02 m/s and 0.15 rad/s.
**Immediate failure**, after every 2 ms substep: floor contact; the origin leaving x in [0.20, 0.76] m, y in [-0.45,
0.45] m, z in [0.60, 1.30] m; tilt above 0.6 rad; falling 1 cm below the start height after lift-off; a released frame
with an unthreaded ring after both rings engaged; a frame held by nothing while falling faster than 0.2 m/s; an arm,
torso or stand link touching anything (`robot_collision`); unstable physics; and, at the end of every control, a frame
held by nothing at all after lift-off (no drop-and-catch window); 3,000 controls. The D-ring hinge's lower stop (0 rad,
0.005 N m/rad return spring) stands in for the frame back (ring-frame contacts are filtered). Oracle: 869 Sharpa rows on
the arms (success at 669); no Wuji solution is packaged (Wuji selectable,
no success).

### USB plug into a hub port (`usb_plug_insert`, T24)

Wave 3 (the arm on the old scene): the right Tianji Marvin arm and hand (stand at base (0.93, -0.52, -0.10) on the floor
z = -0.20 m, yaw 135 degrees, the left arm parked); layout change: the floor is 0.10 m lower than in the source, so the
0.70 m desk top stands 0.90 m above it, and the desk's two front legs are set back under the top to clear the base
plate; an arm link, the stand, the torso or the parked hand touching anything fails at once (`robot_collision`). A free
four-port USB hub rests on the desk (top z = 0.70 m) with its ports facing the front edge; a USB-A plug with a 0.5 m
cable lies on its side. **Success**, in order: (1) grasped and lifted: the thumb and another finger touch the rigid
plug, the plug touches nothing else, its shell tip at z >= 0.73 m; (2) seated in port 4 (the rightmost): in the port
frame the shell tip at least 10.8 mm deep in the 12 mm cavity (90 %), within 0.6 mm of the axis sideways and 0.5 mm
vertically, plug axis within 5 degrees of the port axis and its top face within 20 degrees of the hub's top face
(polarity); (3) released: still seated in port 4, no hand contact on plug, cable or hub, plug slower than 0.01 m/s, for
50 consecutive controls (1 s). A plug in another port never counts. **Immediate failure**: the hub moved more than 20 mm
or tilted more than 20 degrees; the plug below z = 0.685 m; plug or hub outside the workspace box; the cable's far end
more than 5 cm below the desk top; after stage 1, a dropped plug (at the first control without hand contact on plug or
cable, not engaged 3 mm deep in a port, and falling faster than 0.2 m/s or lying on the desk or floor); unstable
physics; 3,000 controls. Ports are open cavities with generous clearance (0.25 mm per side across, 0.15 mm in height);
tongue and contacts are visual and there are no retention springs. Not restored: a bimanual held-hub version with the
source clearances, polarity tongue and retention springs aligned the plug to <= 0.09 mm, but every insertion dropped the
hub or the plug, so the shipped one-hand scene keeps the wave-2 simplifications. Oracle: 1,595 Sharpa rows on the arm
(success at 1,475; the standard verifier allows 1,800 s for the 12-minute trial); no Wuji solution.

### Desk-fan front guard (`fan_guard_install`, T26)

An unpowered desk fan (free body on rubber feet) stands on the worktop with its rear wire cage and four perimeter U
clips (passive hinges with an elastic over-centre detent). The detached front guard (0.369 m wire cage, 185 g, raised 22
mm hub cap) lies flat, dome up. All four clips start swung open (1.40 rad), as in the source, and the hand closes all
four; a closed lower clip forms an open-topped U channel that can carry the rim. **Success**, in order: (1) the guard
seated: centre within 5 mm of the fan axis, axial seat error within 2.5 mm, axis within 5 degrees; (2) still seated, all
four clip hinges at most 0.12 rad with the guard rim inside every clip's U channel, each upper clip locked at or after
the first seated control; (3) no hand contact on guard, clips or fan, guard slower than 0.02 m/s and 0.2 rad/s, for 50
consecutive controls (1 s). **Immediate failure**, after every 2 ms substep: the fan moved more than 3 cm or tilted more
than 0.10 rad; the guard back on the worktop, a leg or the floor after it was lifted 5 cm; the guard touching nothing
while falling faster than 0.2 m/s; the guard striking the fan base, stem, neck, motor housing, feet or buttons; its
centre of mass below the worktop or outside the workspace box; unstable physics; 6,000 controls. Rigid cages and clips;
the source's 45 mg snap leaf is the elastic detent; the lower clips keep a 1.3 mm deeper lip than the source's so that
the hung guard cannot tip forward. Wave 3: the pre-closed lower clips are gone (realism restored); kept are
the raised 22 mm hub cap in place of the source's 6 mm badge (a fingertip resting on the spokes reaches only the badge's
top corner: every tried lift needed the fingertip capsules 8 mm inside the 0.5 mm spokes) and the floating wrist stage
(with the fan 0.45 m behind the worktop edge, the Marvin arm reaches neither the clip pushes nor the upright-guard
poses, whose wrist angles exceed J6/J7). Oracle: 2,665 Sharpa rows (success at 2,485); no Wuji solution.

### Stool cross brace (`stool_brace_insert`, T27)

A pine stool dry frame: the lower side frame lies flat with its four bores up and three rails already seated in three of
them; the loose cross brace (0.26 m, an 8 mm dowel exposed 15 mm at each end) and the opposite side frame (upside down)
lie beside it. A dowel is seated when its tip is 12-19 mm past the bore entry, within 1.6 mm of the bore axis and within
0.105 rad of it. **Success**, in order: (1) brace lifted (clear of the table, centre raised 0.05 m, lowest corner 0.02 m
up); (2) one brace dowel seated in the empty lower bore; (3) the opposite frame lifted; (4) assembled: each of the eight
bores holds exactly one seated dowel and every rail has one dowel seated in each side frame; then no hand contact and
every part still (0.02 m/s, 0.2 rad/s) for 50 controls (1 s). **Immediate failure**, after every 2 ms substep: the lower
frame moved more than 0.03 m or tilted more than 10 degrees; a pre-seated rail pulled to less than 8 mm or tilted more
than 10 degrees; the brace back on the table or below 0.09 m after stage 1, tilted more than 20 degrees after stage 2;
the opposite frame on the table or tilted more than 20 degrees after stage 3; any part with no contact falling faster
than 0.2 m/s; floor contact, below the table top or outside the workspace box; unstable physics; 6,000 controls. All
parts are free rigid bodies; the bores keep the source size (4.1 mm radius for the 4 mm dowels: 0.1 mm radial clearance,
no entry chamfer; hollow contact geometry of 24 convex sectors; wave 3 restored them from the earlier 1 mm clearance and
4 mm chamfer); glue, screws and the seat are not modelled; the solver adds 5 noslip iterations so the 0.58 kg frame does
not creep in the grip. Still on the floating wrist stage: the brace pivot (fingers-down, palm toward the robot) stays
23-107 mm out of the Marvin arms' reach from every tried stand pose. Oracle: 3,006 Sharpa rows (success at 2,806); no
Wuji solution.

### RAM module installation (`ram_module_install`, T28)

A Kingston DDR4 module stands upright in a slotted anti-static foam holder on a service workbench; an ATX motherboard is
fixed in its tray with four DIMM sockets; the outer socket has one moving latch, open. **Success**, in order: (1)
picked: the module out of the holder (no holder contact, lower edge z >= 0.851 m), held by the thumb and another finger;
(2) seated: both lower module ends 1.5 to 2.6 mm above the socket base, lateral offset <= 0.5 mm, along-slot offset <=
1.0 mm, height axis within 3 degrees of vertical and length axis within 3 degrees of the keyed direction (a reversed
module never counts); (3) latched: while seated, latch hinge <= 0.08 rad; then 50 consecutive controls (1 s) seated and
latched with no hand contact on module or latch, module slower than 0.01 m/s and 0.2 rad/s. **Immediate failure**, after
every 2 ms substep: module contact with anything but the hand, the holder or the target socket; an unsupported module
falling faster than 0.2 m/s or a free fall above 5 cm; a lower corner below the bench top or a lower end less than 1.2
mm above the socket base; leaving the workspace box; unstable physics; 3,000 controls. Simplifications (target socket
only): copper contacts and side catches are visual; the throat keeps the source's 1.66 mm (module 1.27 mm; wave 3
restored it from 2.10 mm) with lead-in chamfers; the latch is a passive over-centre toggle spring that only the module's
lower edge closes; no electrical contact or retention force. Kept from wave 2: the slotted foam holder (the source
module lies flat; a flat 1.27 mm board cannot be picked up with these fingertips: its raised edge stays below the
fingertip spheres' centres) and the floating wrist stage (on the Marvin arm the module slipped or pivoted in the pinch
during the carry and alignment, and the 1.66 mm throat needs < 0.5 mm lateral error). Oracle: 1,529 Sharpa rows (success
at 1,379); no Wuji solution.

### Boot sole brushing (`boot_sole_brush`, T29)

Wave 3 (the arm on the old scene): the right Tianji Marvin arm and hand (stand at base (0.147, -0.591, 0.10) on the
floor z = 0 beside the counter's -y edge, facing +y; the left arm parked); any robot part other than the right hand
touching anything fails at once. A rubber boot (Poly Haven, CC0) stands sole-up on a fixed boot-rack peg in a collection
tray; six loose 1 g soil clods lie lodged in its tread (gravity and friction only; the source scene's cohesive bond is
not simulated); a shoe brush lies bristles-down on the counter. **Success**, in order: (1) the brush's bristle pad
touches the boot while the hand holds the brush off the counter, at least 10 controls in total; (2) every clod touched
by the bristle pad (not the wooden back) while near the sole, and every clod inside the tray walls; (3) for 50
consecutive controls (1 s) all clods in the tray at <= 0.05 m/s while the brush touches neither boot nor clods and is
withdrawn. **Immediate failure**, after every 2 ms substep: the boot moved more than 0.03 m or tilted more than 0.35
rad; a clod touching the counter or floor, below the counter top or outside the workspace box; any hand geometry
touching a clod; the brush touching floor, tray or rack, below the counter top, outside the box, or released in the air
(no contact but clods while falling faster than 0.2 m/s); unstable physics; 3,000 controls. The bristle field touches
the world through one compliant pad (fibres do not bend). Not restored (attempted, with evidence in the family README):
the left hand holding the boot at the source height, and the source clod positions with its 32 hinged tufts; in every
attempt the fingertip-pinched brush rolled about the thumb-finger axis under the stroke loads and was lost after 3-12
strokes. Oracle: 1,688 Sharpa rows on the arm (success at 1,538); no Wuji solution is packaged (Wuji
selectable, no success).

### Paper stapling (`paper_staple`, T36)

Wave 3: the right Tianji Marvin arm (arm rig above) and its hand do the task, the left arm parked; the stand is at base
(0.58, -0.66, 0.10) on the floor, yawed 135 degrees, its base plate between the desk legs (at least 20.6 mm clear; exact
check at reset and over the oracle). A desk (top z = 0.78 m), a free NOVUS B2-style stapler at the source pose (a
passive spring-returned head hinge with the source's press force, about 10 N to start the stroke and 25 N at the bottom
stop 8 cm in front of the hinge, a bottom stop at 0.1701 rad and a paper insertion stop behind the anvil) and three
rigid A5 sheets (0.5 mm, 2.5 g; the source's are 0.10 mm) that start as a misaligned staircase (4 and 8 mm toward +x)
with the bottom sheet's corner resting on the anvil mouth. **Success**, in order: (1) every corner of sheets 1 and 2
within 2.0 mm of sheet 0's, stacked and in contact; (2) the staple point inside every sheet 3-30 mm from both edges of a
corner and 0-6 mm below every sheet; (3) the head within 0.01 rad of its bottom stop with the driver blade on the top
sheet; (4) head back up (<= 0.02 rad), no hand contact with sheets or stapler, sheets slower than 0.02 m/s, for 50
consecutive controls (1 s). **Immediate failure**, after every 2 ms substep: a sheet centre below z = 0.77925 m or a
corner below 0.765 m; a sheet centre off the desk or outside the workspace box; a sheet or the stapler on the floor or a
desk leg; a contact-free sheet or stapler falling faster than 0.2 m/s; the stapler moved more than 3 cm or tilted more
than 0.26 rad; an arm link or the stand touching the desk, the stapler or a sheet; unstable physics; 6,000 controls.
Wave 3 restored the stapler's source pose and press spring. Not restored, with evidence in the family README: the
source's flat start (the 8 mm fingertip capsules meet a 0.5 mm sheet edge above the desk at a slant, press the sheets
down and ride over them, so the sheets start propped on the anvil mouth) and the paper stop (not part of the real B2,
but without a counter-face the misaligned stack cannot be squared). The sheets are rigid plates and no staple is formed.
Oracle: 942 Sharpa rows on the arm (success at 742); no Wuji solution is packaged (on the arm the Wuji
fingers fold under the 25 N press; Wuji selectable, no success).

### Ring binder page loading (`binder_page_load`, T37)

A free open-front ring binder lies on the desk with three 1-inch split rings on two toggle plates with an over-centre
spring (closed at 0 rad, open at 0.60 rad); a booster paddle at each end opens them when pressed down (the plates and
boosters are coupled by joint equalities inside the passive mechanism, never to the hand). Two rigid punched pages
(139.7 x 215.9 mm, 6 g, three 6.35 mm holes) lie loose and flat on the desk, printed face up, as in the source (wave 3
removed the earlier page stands): a hand drags a page until its far edge overhangs the desk edge and pinches the
overhang. **Success**, in order: (1) rings opened (both plates >= 0.50 rad); (2) pages placed: rings still open, each of
the six holes threaded by the right ring half of its own station (one crossing within 3.5 mm of the hole centre), no
hand contact on the pages, each page centre over the back cover; (3) rings closed (<= 0.05 rad), every hole linked
exactly once; (4) no hand contact on pages or binder, both pages resting on the binder and staying within 2 mm and 0.03
rad, for 50 consecutive controls (1 s). **Immediate failure**, after every 2 ms substep: a page touching the floor
(sliding on the desk and hanging over its edge are allowed); a page with no contact falling faster than 0.2 m/s with no
ring through its holes; a page origin more than 2 mm below the desk top or outside the workspace box; the binder moved
more than 0.03 m or tilted more than 0.35 rad; a ring wire more than 1.2 mm into a page or a hand part more than 3 mm
into a page; unstable physics; 6,000 controls. Pages are stiff cardstock plates (no bending). Not restored: the source's
two hands (one hand on the floating wrist stage: from any stand that reaches the binder, the flat pages and the desk
edges where a rigid page can be picked up are out of the Marvin arms' reach, and on the wrist stage one hand picks a
flat page by the edge pinch). Oracle: 3,095 Sharpa rows (success at 2,940); no Wuji solution.

### Letter into an envelope (`envelope_letter_insert`, T38)

A tri-folded A4 letter (a stiff 99 x 210 x 2 mm card, 5 g) lies flat on the desk; an empty DL wallet envelope (110 x 220
mm, 6 g) lies flat beside it with its open mouth along a long edge and the open flap on the desk. The envelope is a
rigid pocket: walls 4 mm apart, 3 mm side seams, a 4 mm bottom seam and a 30 mm elastic mouth lip (a passive spring
hinge that starts closed, flush with the front wall, as in the source). Both objects are free. Wave 3: the right Tianji
Marvin arm (stand at base (1.15, -0.25, 0.10) on the floor at the desk's +x edge, facing -x, its base plate 6 mm from
the nearest desk leg; the left arm parked). Stages, measured on the letter's corners in the envelope frame: (1) at the
mouth: both leading corners at least 10 mm past the mouth line, inside the seams and between the walls, the trailing
corners still outside; (2) inserted: at most 5 % of the letter's length outside, all four corners inside the seams, in
front of the bottom seam and between the walls; (3) released: stage 2 with no hand contact on letter or envelope and
both at rest, for 50 consecutive controls (1 s). **Immediate failure**, after every 2 ms substep: letter or envelope
below the desk top, on the floor, dropped (touching nothing while falling faster than 0.1 m/s) or off the desk; the
letter pressed through a wall, seam or the lip, or into the envelope by more than 0.7 mm; the envelope pushed more than
5 cm or tilted more than 0.35 rad; the robot's arm, stand or parked hand touching the letter or the envelope; unstable
physics; 6,000 controls. The folded letter is one rigid card (no paper bending); the flap is never sealed. Modelling
simplification: the walls are 4 mm apart for the 2 mm rigid card, so the letter enters the closed mouth without parting
the lip (the source's "part the mouth" step is not required). Oracle: 2,446 Sharpa rows on the arm (success at 2,346);
no Wuji solution is packaged (Wuji selectable, no success).

### Board-book page turn (`book_page_turn`, T39)

Wave 3: both Tianji Marvin arms (arm rig above; stand at the world origin facing +x on the floor z = -0.1 m), the left
hand steadying the book and the right one turning. A free 6 x 6 in board book lies open at pages 4 / 5 on the desk in
the T39 source pose (desk top z = 0.78 m, book centre (0.51, 0)): eight rigid 1.2 mm boards and two covers on passive
binding hinges (friction 0.002 N m, damping 0.006 N m s/rad) with a 200 N/m vertical binding compliance; every board
lies flat on its stack, 0.2 mm apart, so the hand separates the top board itself (wave 3 removed the earlier 4-degree
springback stop of leaf 2). Layout change: the desk's two front legs are set back from x = 0.29 to 0.43 m (top
unchanged) because they stood inside the stand's base plate. **Success**, in order: leaf 2 lifted (> 30 degrees), past
vertical (> 90 degrees), then laid: > 170 degrees, in contact with the left stack, hinge speed <= 0.2 rad/s, every other
board and cover within 5 degrees of its start, no hand contact with the book, for 50 consecutive controls (1 s).
**Immediate failure**, after every 2 ms substep: the spine moved more than 3 cm or rotated more than 10 degrees; another
leaf moved more than 30 degrees; a cover moved more than 30 degrees; a book part's centre of mass more than 2 mm below
the desk top; unstable physics; 3,000 controls. Boards are rigid; no paper bending, tearing or damage is modelled; the
turning fingertip lifts the leaf by friction on its 1.2 mm fore-edge face, pressing up to 4.5 mm into the soft fingertip
contact. Oracle: 553 Sharpa rows on the arms (success at 453); no Wuji solution is packaged (Wuji selectable, no success).

### Tray with two filled glasses (`tray_glass_carry`, T48)

Two hands, each on its own six-DoF wrist stage (56 / 52 controls), carry the original perforated serving tray
(0.39 x 0.52 m, 1.0 kg) with two loose 150 mL glasses (0.275 kg each) from the source counter, around a fixed bottle
and across a 30 mm counter gap, set it down on the receiving counter and let go; the fingertips hook under the rim bar
through the tray's open handle slots. Liquid is not simulated: a glass counts as spilled above 15 degrees of tilt.
**Success**, in order: lift-off (no counter contact, base at z >= 0.91 m, both glasses seated); placement (on the
receiving counter only, centre within 20 mm in x / 30 mm in y of (0.78, 0.00) m, tilt <= 5 degrees, yaw <= 10 degrees);
release (no hand contact, glasses within 6 degrees of vertical, everything at rest) for 50 controls (1 s).
**Immediate failure**, after every 2 ms substep: a glass tilted above 15 degrees, off the tray footprint or 20 mm off
its floor; the bottle touched by the tray, a glass or a hand; the tray back on the source counter after lift-off or
dragged on the receiving counter; a tray or glass falling faster than 0.6 m/s (0.2 m/s while unsupported); tray tilt
above 35 degrees; anything below z = 0.86 m or outside the workspace box (z <= 1.12 m: no lifting over the bottle).
Oracle: 1,072 Sharpa rows (success at 952); Wuji: `solution/wuji/` (1,148 rows, success at 1,028).

### Whisking batter (`batter_whisk`, T49)

Wave 3: both Tianji Marvin arms (arm rig above; stand at the world origin facing +x on the floor z = -0.1 m), the left
hand steadying the bowl during the pick-up, the right one picking up and whisking; layout change: the decorative cabinet
under the counter starts behind the stand's base plate (the counter top keeps its source height, 0.68 m, and position).
As in the source, the balloon whisk starts at rest in the free-standing steel bowl (released from the source's standing
pose it settles leaning on the rim, handle end on the counter); both hands start open. The batter is not simulated (its
mass is lumped into the bowl): whisking is measured on the whisk-head point (20 mm above the wire tip), which is in the
batter between 3 mm above the bowl origin and the batter surface (35.7 mm) and at least 4 mm inside the wall.
**Success**, in order: (1) picked up: a hand holds the whisk clear of the counter and the bowl, its lowest point at
least 30 mm above the counter, for 10 controls; (2) immersed; (3) five net revolutions of the head point about the bowl
axis while it stays in the batter (leaving resets the count; controls closer than 8 mm to the axis add nothing); (4)
drained: in hand, wire tip at least 10 mm above the rim over the opening, head-down within 30 degrees, for 25 controls;
(5) set down: the whisk lowered onto the counter while held, then released, and for 50 controls (1 s) it lies on the
counter within 30 degrees of horizontal, at least 120 mm from the bowl axis, touching neither robot nor bowl, still.
**Immediate failure**, checked after every control: bowl tilt above 10 degrees, slide above 30 mm or lift above 20 mm;
after the pick-up, the whisk touching nothing, more than 2 mm above the counter and falling faster than 0.2 m/s; after
the pick-up and before placement, the whisk on the counter or out of robot contact for more than 10 controls; after
placement, touching neither robot nor counter for more than 5 controls; floor contact, below the counter or outside the
workspace; unstable physics; 4,000 controls. Wave 3 restored the source's start (the whisk was pre-held in a frozen
grasp) and added the pick-up stage. Not restored: the second hand holding the bowl through the whisking (fingers hooked
over the 12 cm bowl's rim sit inside the balloon whisk's sweep and are struck by it in every tried variant). Oracle:
1,916 Sharpa rows on the arms (success at 1,816); no Wuji solution is packaged (Wuji selectable, no success).

### Portable bicycle pump (`bicycle_pump_stroke`, T50)

Wave 3: the right Tianji Marvin arm (arm rig above; stand at the world origin facing +x on the source floor z = -0.1 m,
the left arm parked) and its hand do the task; layout change: the bench's two back legs are moved 8 cm under the
unchanged top so that they clear the stand's base plate. A free-standing Topeak Mini Morph-type pump (T handle 0.45 m
above the bench, 0.20 m piston travel) stands on its folding foot next to a 406 wheel lying on the bench. As in the
source, the hose head (TRK-RP04 type) starts disconnected: 17.5 mm out from its seat on the valve stem's axis, thumb
lock open; the head is a passive slide along the stem (2 N friction, seat end stop) and the thumb lock a passive hinge
(0 to 1.65 rad). The piston slides on a passive joint whose linear air spring returns the handle (6 N at the top, 46 N
at the bottom; viscous damping, 1 N seal friction). A stroke counts only while the head is seated and locked, when the
handle reaches a depth of at least 0.18 m and then returns to at most 0.04 m; tire pressure is a checker quantity (200.0
kPa + 380 Pa per counted stroke, the source gas model's mean rise; air is not simulated). **Success**, in order: (1)
head connected (seated within 0.5 mm with the thumb lock within 0.15 rad of closed; latches); (2) 28 counted strokes;
(3) pressure at least 210.6 kPa (the source's value after its 28 strokes); (4) the head disconnected again, as at the
end of the source (lock opened to at most 0.5 rad and the head at least 12.5 mm off its seat; latches); (5) the handle
released at the top (depth <= 0.01 m, no robot contact with the pump or the head, pump tilt <= 0.0873 rad, pump and
handle speeds <= 0.02 m/s) for 50 consecutive controls (1 s). **Immediate failure**, after every 2 ms substep: pump tilt
above 0.2618 rad, base moved more than 0.03 m horizontally or lifted more than 0.02 m, the pump's centre of mass below
the bench top or a pump part on the floor, the connected head pulled back more than 2 mm or its lock opened below 1.2
rad before stage 3, the head pulled off with its lock still closed after stage 3, unstable physics; 5,000 controls. Wave
3 restored the source's disconnected start, its unlock-and-retract end and its 28-stroke pressure model (wave 2 had the
head locked on the valve throughout and six strokes from 207.8 kPa); the source's optional steadying second hand is not
used (one arm-mounted hand keeps the free pump upright through all strokes). Oracle: 4,299 Sharpa rows on the arm
(success at 4,149); the earlier Wuji solution is not packaged (Wuji selectable, no success).

## Modes and grading

**Privileged.** `from rcb_dexhand import Session` (the family's `runtime.py`, copied into `/opt/tools`): the full
MuJoCo model and state, exact resets, snapshots where the family offers them, renders and `replay`. The deliverable is
`/app/output/trajectory.npz` (above) and the script that made it, `/app/output/gen.py`. The separate verifier
(`[verifier] environment_mode = "separate"`) runs the shared `tests/grade.py`: two concurrent fresh-process runs of the
family's `replay.py`, reward 1 iff both succeed with identical final state hashes. `replay.py` reports an invalid
archive as `bad_trajectory` and exits 0; a crashed replay is an infrastructure error. `reward.json` is numeric
(`success, deterministic, infra_error, bad_trajectory, missing_trajectory, n_actions, sim_steps, stages_completed,
hand_wuji`); text diagnostics go to `/logs/verifier/details.json`. After `reward.json` is written, a third fresh
replay renders the replay video (`/logs/verifier/replay.mp4`, its record in `video.json`) in the verifier's remaining
time (`timeout_sec` minus 180 s, at most `video_timeout_s`, which is never below the replay timeout); it never changes the verdict. The essential families' `replay.py` films every 2nd step, at most 1500 frames
(`VIDEO_MAX_FRAMES`; a 640x480 OSMesa frame costs ~0.3 s on one core).
The twenty wave-2 families' own `replay.py` film at most 300 steps (`VIDEO_MAX_FRAMES = 300`; a longer episode at a
larger stride, recorded as `video_stride` and `recording.playback_speed`) and mark the record `"video": true`, which
`grade.py` requires. A frame of their scenes costs 0.35-3.6 s on the task's two cores (the Marvin-arm scenes are the
slow ones), measured on an archive that holds the first oracle row for the family's whole row limit; `video_sec`,
`verifier_privileged_sec` and `collect_sec` cover that longest archive with a 1.5x margin.

**Standard** (`eai-standard/2.2`, docs/protocol/standard_mode.md Part 2). The agent gets the shared client (`rcb_client`) and no
simulator code. The `sim` sidecar (each standard task's `environment/sim/server.py` on the unmodified shared layer
`embodied_first_exam/standard/`) serves calibrated RGB and depth, the robot's own joints, efforts and link poses and
robot-link forward kinematics; object poses, contact forces, checker stages and scene bodies are not served. The
reset budget is 20 (`budget.reset`, `RCB_RESET_BUDGET` in the compose file; see "Standard-mode resets" below); every
action, watch step and reset is journaled, and a crashed service resumes the same episode from its journal, resetting
where the committed resets did (resume class `exact`). The control rate is the family's (`spec()["control_hz"]`); the agent's clock
(`meta["time_left_s"]`) counts from its first request. The collect hook (`finalize.sh` / `finalize.py`) ends the
episode and seals `final.json` from the service's record of it (`episode.json`: the live success and end-state hash;
no replay), then renders an evidence video (`/data/replay.mp4`) from `/data/trajectory.npz` in one
fresh process in the collect hook's remaining time (its `timeout_sec` minus 60 s, at most `video_timeout_s`); the
separate verifier reads only `final.json` and needs the live success. Missing trusted evidence is an infrastructure
error; the video never decides a verdict.

**Oracles.** Every family uses the same oracle runners: privileged `solve.sh`
re-saves the family's rows to `/app/output/trajectory.npz`; standard `solve.sh` submits the same rows as float64
through the client's request path (`hold`, dt = 1 / control rate, chunks of at most 250 rows or 10 s) and resumes after
a service restart. Rows above the repository's 2 MB file limit are stored as `trajectory.json` + `trajectory.partNN.npz`
(`solution/solution_parts.py`) and concatenated and sha256-checked before use. A family with a per-hand
solution gets `solution/<hand>/`, which its `solve.sh` picks for the run's hand (Wuji reference solutions, above).

**Harbor results** (Harbor 0.23, `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0`, CPU only, `RCB_LIMITS_ENFORCE=0`):

| Family | privileged oracle / nop | standard oracle / nop | standard oracle wall | peak GiB: privileged verifier / standard sim | Wuji |
|---|---|---|---|---|---|
| `essential_cube_layer` | 1 / 0 | 1 / 0 | 4 min | 0.39 / 0.61 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |
| `essential_held_joystick` | 1 / 0 | 1 / 0 | 4 min | 0.51 / 0.70 | Wuji oracle 1 in both modes; standard nop 0 |
| `essential_pen_regrasp` | 1 / 0 | 1 / 0 | 4 min | 0.41 / 0.63 | Wuji oracle 1 in both modes; standard nop 0 |
| `essential_two_object` | 1 / 0 | 1 / 0 | 4 min | 0.45 / 0.67 | Wuji oracle 1 in both modes; nop 0 and 12 s hold 0, both modes (hold: deterministic) |
| `essential_rotary_gait` | 1 / 0 | 1 / 0 | 17 min | 0.49 / 0.70 | Wuji oracle 1 in both modes; standard nop 0 |
| `essential_cube_reorient` | 1 / 0 | 1 / 0 | 2 min | 0.39 / 0.61 | Wuji oracle 1 in both modes; standard nop 0 |
| `assemble_hamburger` | 1 / 0 | 1 / 0 | 9 min | 0.41 / 0.63 | Wuji oracle 1 in both modes; standard nop 0 |
| `paper_half_fold` | 1 / 0 | 1 / 0 | 5 min | 0.50 / 0.64 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |
| `sweep_dustpan` | 1 / 0 | 1 / 0 | 38 min | 3.68 / 2.31 | nop 0 and 12 s hold 0, both modes (hold: deterministic) |
| `pot_shelf_transfer` | 1 / 0 | 1 / 0 | 5 min | 3.42 / 2.17 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |
| `remote_battery_swap` | 1 / 0 | 1 / 0 | 9 min | 3.42 / 2.23 | no Wuji solution |
| `coffee_stir` | 1 / 0 | 1 / 0 | 9 min | 3.42 / 2.26 | no Wuji solution |
| `jar_lid_open` | 1 / 0 | 1 / 0 | 8 min | 3.40 / 2.38 | Wuji privileged oracle 1 (arm) |
| `grinder_crank` | 1 / 0 | 1 / 0 | 11 min | 3.47 / 2.40 | no Wuji solution |
| `pancake_serve` | 1 / 0 | 1 / 0 | 13 min | 3.41 / 2.40 | no Wuji solution |
| `vacuum_bin_reseat` | 1 / 0 | 1 / 0 | 10 min | 0.59 / 0.71 | no Wuji solution |
| `drying_rack_unfold` | 1 / 0 | 1 / 0 | 3 min | 0.40 / 0.59 | Wuji nop 0 (no Wuji solution) |
| `picture_hang` | 1 / 0 | 1 / 0 | 7 min | 3.40 / 2.13 | no Wuji solution |
| `usb_plug_insert` | 1 / 0 | 1 / 0 | 12 min | 3.44 / 2.65 | no Wuji solution |
| `fan_guard_install` | 1 / 0 | 1 / 0 | 6 min | 0.45 / 0.71 | no Wuji solution |
| `stool_brace_insert` | 1 / 0 | 1 / 0 | 17 min | 0.45 / 0.65 | no Wuji solution |
| `ram_module_install` | 1 / 0 | 1 / 0 | 3 min | 0.40 / 0.58 | no Wuji solution |
| `boot_sole_brush` | 1 / 0 | 1 / 0 | 6 min | 3.51 / 2.37 | no Wuji solution |
| `paper_staple` | 1 / 0 | 1 / 0 | 6 min | 3.40 / 2.48 | no Wuji solution |
| `binder_page_load` | 1 / 0 | 1 / 0 | 6 min | 0.44 / 0.67 | no Wuji solution |
| `envelope_letter_insert` | 1 / 0 | 1 / 0 | 19 min | 3.40 / 2.38 | no Wuji solution |
| `book_page_turn` | 1 / 0 | 1 / 0 | 5 min | 3.47 / 2.48 | no Wuji solution |
| `tray_glass_carry` | 1 / 0 | 1 / 0 | 3 min | 0.61 / 0.84 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |
| `batter_whisk` | 1 / 0 | 1 / 0 | 9 min | 3.41 / 2.26 | no Wuji solution |
| `bicycle_pump_stroke` | 1 / 0 | 1 / 0 | 10 min | 3.42 / 2.29 | no Wuji solution |

The standard wall time is the whole trial as measured with the collect hook's former grading replays (it is shorter now: the live episode and the evidence video). sweep_dustpan's live oracle episode took 11.7 min of the agent phase (530 calls of at most 250 rows at 2 kHz). Peaks are cgroup `memory.peak` of the verifier container (privileged; two concurrent replays) and of the `sim` sidecar over the whole trial (standard); the agent containers stayed below 0.25 GiB. Wuji oracle: the packaged Wuji solution with `DEXHAND_HAND=wuji` (privileged: Harbor's `--ae DEXHAND_HAND=wuji`; standard: the sim service's hand) scores 1 with `hand_wuji = 1`, deterministic (the Sharpa oracles and no-ops of these nine families were re-run with the per-hand `solve.sh`: 1 and 0). Wuji: `DEXHAND_HAND=wuji` trials (every family's standard no-op; for `essential_two_object` and `sweep_dustpan` also the privileged no-op and a 12 s hold of the Wuji start in both modes) all score 0 with no infrastructure error; the standard trials and the privileged holds report `hand_wuji = 1` (a privileged no-op hands in nothing: `missing_trajectory = 1`). Wave-2 rows: the oracle / nop and Wuji verdicts are the family authors' trials on the final task files (same image and settings); wall time and peaks are an integration smoke (one privileged and one standard Sharpa oracle per family, both 1).

### Standard-mode resets

`budget.reset = 20`, DexToolBench's value (PROTOCOL §2): an essential family starts with the object already in the
hand, every family ends an episode at the first failure (a dropped, slipped or knocked object, a bound exceeded), and
the agent has no simulator of its own in standard mode, so with one episode the first slip decided the trial. The
capability is the one of docs/protocol/standard_mode.md ("Optional reset capability"), implemented in the DexHand adapter
`environment/sim/server.py` the way the MyoSuite 2.2 service implements it (the shared 2.2 layer has
no reset): `POST /reset` (JSON or RCB1 `{cameras, video_fps, depth}`, no physics) calls the family's
`Session.reset()` and returns the new episode's first frames; 409 after a success, once the budget is spent and after
the agent's time; `/status` and every meta add `episode`, `resets_left` and `control_steps_total`. Only the last
episode is graded: `trajectory.npz` holds its rows, the service's verdict on that episode is the grade, and
`reward.json` adds `resets` and `reset_budget`. `Session.reset()` restores the frozen start exactly in all ten families
(checked for both hands where offered: after k rows and a reset, the state hash equals a fresh process's, and
the same rows then end in the same hash as in a fresh process). `RCB_RESET_BUDGET=0` still runs one episode.
Results with a different budget are reported separately.

### Standard-mode grading by the live episode

`success` in `final.json` is the sim service's verdict on the episode it ran (the last one after resets):
`Session.status()["success"]` after the last executed row, the family's full predicate (every ordered stage, the
terminal hold, the invariants at every physics substep), evaluated by `execute()` in
the task's `environment/sim/server.py` and written to `episode.json` by `end_episode()`. `Session.step` also refuses an out-of-range target or a moved locked
wrist (the service clips to the published ranges first), and a success ends the episode, so no settle or hold window is
added. The collect hook: `finalize.py` copies the record into `final.json` with `graded_by = "live"`, `replays = 0`, `live_success`, `live_sha`,
`video_pending`, then the family's `replay.py --video` films the trajectory once (`video.json`, `video.log`;
`video_source = "render"`); a failed or late video sets `video = false` and changes nothing else. `reward.json` carries
`graded_by_live`, `replays`, `gave_up`, `instance_mismatch` and `video_rendered`. When a fresh episode begins (not on a crash resume) the service compares the
sha256 of the frozen instance's files (`instance.json`, `catalog.json` and, where present, `task.json`,
`wuji_reset.json`, `offered_hands.json`) with the record in `grading.json` (`instance_sha256`); a
difference ends the trial before the agent is served (`instance_mismatch`, an infrastructure error). There is no
recorded reference hash of the built starting state (computing one needs a MuJoCo run): the start event logs the state
hash the service built and `episode.json` repeats it (`start_sha`), so trials of a task can be compared afterwards.
Infrastructure errors (`infra_error = 1`): no, unreadable or unfinished `final.json`, the service not ending and
dumping its episode within 300 s, a give-up after crashes not all inside the agent's calls (`sim_crashed`,
`resume_failed`), `instance_mismatch`, a hand the task does not offer. A crash inside the agent's calls
(`sim_crashed_on_call`), a simulator error from the agent's actions (`reason = "error"`, `sim_error = 1`), a timeout and
a failed predicate are the agent's 0. The collect hook runs one replay process (the video's); its `timeout_sec` is the
end wait plus the video's bound (`std_collect_s`).

### In-hand cameras of the essential families

Standard mode serves no object state, and the in-hand pose decides every essential predicate (joystick, layer, knob,
sphere and pen angles within 0.1-0.16 rad windows), while the object is 40-60 px wide in `overview` and `palm` (mounted
behind the wrist) sees the back of the hand. The essential scenes therefore add two cameras mounted on the locked hand
body like `palm`: `inhand_top` (from above the palm) and `inhand_side` (from the thumb side), both about 0.2 m from the
grasp region, `fovy` 45, 640 x 480. The standard service returns `overview` and `inhand_top` by default. Calibration:
the published `intrinsic_cv` / extrinsics project known world points to within the review's tolerance. The cameras do not change physics or state hashes, so the oracles are unchanged.

### Held-object rotation bound

`essential_held_joystick` and `essential_cube_layer` share the invariant "keep the held object steady",
`body_rotation <= 0.35` rad (20 degrees); the Sharpa reference solutions peak at 0.2396 rad (joystick) and 0.218 rad
(cube layer). Open-loop references are not robust controllers: under +-0.001 rad finger jitter they mostly fail for
reasons the bound does not decide (a missed checkpoint, a stalled stage, rows running out before the terminal hold;
`essential_cube_reorient`'s reference ends on the very control that completes its hold). With resets and closed-loop
observation an agent can retry, which is what the reset budget is for.

## Task files

The task directories are the deliverable; the tooling that built them is kept outside this repository. Every task
carries the same copies (`ci_checks/check-tooling-identity.sh`) of `rcb_dexhand.py`, `hands.py`, the privileged and
standard graders, the standard service, its collect hook and the `eai-standard/2.2` layer.

```bash
python3 images/dexhand/prepare_assets.py                       # the pinned hand and arm assets (image build only)
python3 scripts/task_conventions.py --check tasks/dexhand/*
bash ci_checks/run_all.sh tasks/dexhand/*
```

## Limits of the models

The wrist stage is a positioning mechanism, not an arm. The cube layer is a one-face hinge abstraction, the pen and
Joy-Con are size-adapted rigid meshes, the walnut scans use convex collision hulls without concavities, cheese and
lettuce are articulated strips, the paper is a reduced shell with uncalibrated material, and the debris pieces are
rigid. In the wave-2 families coffee, batter, air, the liquid in a glass are not simulated (checker quantities stand for them), threads, staples and latch springs are reduced to the contact geometry or passive joints their sections name, and static props stand in for parts the task does not move. The graders claim only the mechanical outcomes these models represent.

## Standard-mode service details

Serves `eai-standard/2.2`. Resume class `exact` (MuJoCo 3.4.0, CPU physics, one thread; a frozen scene rebuilt from its pinned model files; one control row is one or more fixed physics steps). Its service implements the optional reset capability (docs/protocol/standard_mode.md Part 1); the 2.2 client has no `reset()`, so the instructions call `POST /reset` through `Robot._post`.
