# DexHand

DexHand is a benchmark of dexterous-hand manipulation in MuJoCo 3.4.0 (CPU physics, software rendering). It has ten
task families, each with one frozen scene, in privileged and standard mode (20 task directories,
`dexhand-<family>-i00-{privileged,standard}`, standard mode on `eai-standard/2.2`):

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

The default hand is a right (on the arms: a left and a right) **Sharpa Wave** with 22 actuated finger joints; all ten
families also run with the genuine **Wuji Hand 2.2** (20 finger joints) mounted in its place, selected per
episode (`essential_two_object` and `sweep_dustpan` with a Wuji-specific start, see Hands). There
is no assisted grasp: no welds, attachments, scripted object motion or forces on objects; objects move only through
contact and gravity. Every family's reference solution is a recorded physical Sharpa episode (`oracle = "full"`);
nine families (all but `sweep_dustpan`) also package a successful Wuji Hand 2.2 episode, which the oracle uses when a
run selects Wuji (see Hands).

`release_status = "provisional"`: a maintainer's solvability review and agent-trial calibration are pending
(PROTOCOL §2.7). The agent's time limit is each task's own `[agent] timeout_sec` (3600 s in both modes).

## Strict success and failure

Every family follows the same three rules, checked by the trusted runtime from simulator state:

1. **Fail-fast.** The first failure ends the episode and is permanent: a task object dropped, knocked off its support,
   below the table or support, outside its workspace, an invariant or guard violated, or unstable physics. Later rows
   are not executed, so nothing can recover a failure. The checks run at every physics substep, not only at control
   boundaries.
2. **No partial credit.** Success needs every ordered stage and the terminal (released or held) condition for its full
   window of consecutive samples; four of five layers, five of six debris pieces or a placed but still-held pot is a
   failure. Success ends the episode too.
3. **Replayed, never claimed.** The grader rebuilds the frozen scene with the recorded hand in fresh processes and
   replays only the motor targets: two privileged replays must succeed with identical final state hashes; in standard
   mode the service's live episode, two fresh replays of its journal and their hashes must agree. Success flags, object
   poses, configuration overrides or any other member of an agent's archive are never read.

## Hands

| id | model | finger actuators | source (pinned) | license | image path |
|---|---|---|---|---|---|
| `sharpa` (default) | Sharpa Wave | 22 | MuJoCo Menagerie `sharpa_wave` @ `0059d4335f8156206f63a35662313385f7ad6d74` (from Sharpa Robotics `6eea427eb24189519f32b9f21674cd534d3f973c`) | Apache-2.0 | `/opt/dexhand/hand` (`DEXHAND_ASSET_DIR`) |
| `wuji` | Wuji Hand 2.2 (`hand2/hand2_2`) | 20 | `wuji-technology/wuji-description` @ `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` | MIT | `/opt/dexhand/wuji_v2_2` (`WUJI_ASSET_DIR`) |

**Selection.** Privileged: `Session(task, hand="wuji")`, else the environment variable `DEXHAND_HAND`, else `sharpa`;
an unknown id is an error, never a silent fallback. Standard: `DEXHAND_HAND` on the `sim` service, read once at
start (the generated compose passes `DEXHAND_HAND: ${DEXHAND_HAND:-sharpa}`, so `DEXHAND_HAND=wuji harbor run ...`
selects Wuji for a trial); `spec()["hand"]` names it, the agent cannot switch it, and the episode records it.

**Composition.** `scripts/dexhand/shared/hands.py` (`replace_wave_hands`) replaces each Sharpa Wave root body by a
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

**Wuji acceptance.** In all ten families, the Wuji scene composes from the image's assets in both
modes, a no-op scores 0, and short hold or seeded replays are deterministic in fresh processes. Wuji trajectories are
graded exactly like Sharpa ones.

**Wuji reference solutions.** A family may add a successful trajectory for a hand other than the default one by
dropping it next to its Sharpa solution as `solution/<hand>/trajectory.npz` (or `trajectory.json` with parts below
2 MB). The generator checks it (the archive's `hand` is that hand, rows of that hand's width, the family's task and
row limit) and packages it as `solution/<hand>/` of both task directories, next to unchanged copies of the shared
oracle runner and `solution_parts.py`; that pair's `solve.sh` then picks the folder of the selected hand
(privileged: `DEXHAND_HAND` in the oracle's environment, default `sharpa`; standard: the sim service's
`spec()["hand"]`). Other hands, and every family without such a folder, keep the Sharpa oracle unchanged (the
single-hand `solve.sh`, byte for byte): with Wuji selected, its privileged oracle still hands in the Sharpa rows
(graded as a Sharpa episode) and its standard oracle stops at the hand check (reward 0). Nine families package a
Wuji success, each made from motor targets only by an authoring script in the family folder's `tools/` (never
copied into a task) that rewrites the identical rows; float64 replays are bit-deterministic, so rows after the
success are never needed (the six essential ones end exactly at success; float32-rounded rows succeed at the same
control except for `essential_two_object` and `essential_pen_regrasp`, which need the float64 rows the oracles send):

| Family | Wuji rows | success at | authoring script |
|---|---|---|---|
| `essential_cube_layer` | 940 x 26 | control 940 | `task_library/essential_cube_layer/tools/wuji_gen.py` (thumb pad drags the layer about its axis, lifting and landing again; `run_turn.py`, `thumb_turn.py`) |
| `essential_held_joystick` | 146 x 26 | control 146 | `task_library/essential_held_joystick/tools/wuji_gen.py` (thumb on the stick cap, then thumb targets from short physics rollouts) |
| `essential_pen_regrasp` | 1,571 x 26 | control 1,571 | `task_library/essential_pen_regrasp/tools/wuji_gen.py` (five beam searches over finger-target segments, `beam.py`); thin margins: stage-2 pen angle 0.913 rad (window up to 0.92), hold speed 0.057 (limit 0.06); float32 rows do not complete the hold |
| `essential_two_object` | 266 x 26 | control 266 | `task_library/essential_two_object/tools/wuji_gen.py` (physics-shooting MPC rotates and returns walnut A, then a two-via-point release while ring and pinky keep B); thinnest margin: `b_finger_contacts` at its minimum 1 for a few substeps; float32 rows do not complete the release |
| `essential_rotary_gait` | 1,498 x 26 | control 1,498 | `task_library/essential_rotary_gait/tools/wuji_gen.py` (index and middle fingers on antiphase joint-space orbits); thin margin: final angle 0.080 rad above the terminal window's lower bound |
| `essential_cube_reorient` | 165 x 26 | control 165 | `task_library/essential_cube_reorient/tools/wuji_gen.py` (cross-entropy search over finger targets on model copies); thin margins: peak object speed 10.5 (limit 12), displacement 0.0615 m (limit 0.07 m) |
| `assemble_hamburger` | 5,847 x 26 | control 5,847 | `families/assemble_hamburger/tools/wuji_gen.py` (pinch IK over wrist, thumb and index; per-layer parameters from `tools/wuji_layers.py`) |
| `paper_half_fold` | 620 x 26 | control 554 | `families/paper_half_fold/tools/wuji_gen.py` (fingertip pads under the overhang, rigid rotation about the fold line, press, lift) |
| `pot_shelf_transfer` | 8,266 x 54 | step 8,266 | `families/pot_shelf_transfer/tools/wuji_gen.py` (the Sharpa authoring controller's phases with a Wuji power-grip posture) |

**Wuji start states that differ from the Sharpa start.** Two families need a Wuji-specific start because the Sharpa
start cannot be held by the Wuji geometry; only hand joints (and, where physically necessary, the held objects' start
poses) differ, found by closing the Wuji fingers in physics; the task, predicate and fail-fast rules are unchanged:
- `essential_two_object`: `task_library/essential_two_object/wuji_reset.json` declares the Wuji finger targets and
  both walnuts' start poses in the Wuji grasp (`initial_objects`; formed by releasing the walnuts above the open hand
  while the fingers close). Walnut B's (and A's) reference pose is its pose after the reset settle, as for Sharpa. The
  start holds both walnuts for 60 s of hold actions; a searched open-loop finger controller completes stage 1.
- `sweep_dustpan`: `assets/reset_wuji.npz` keeps every arm, tool, debris and bristle coordinate and every arm target of
  the frozen start and declares only the 40 Wuji finger joints and targets (closed onto the frozen shafts); holding
  them keeps both tools for the full 80 s horizon.

A family may still offer fewer hands (`task.toml` `hands`, `offered_hands.json` written by the generator); none of the
ten release families does. The generator writes the offered hands into the task's runtime (`offered_hands.json` beside `hands.py`). Such a task's
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

The image `ghcr.io/mll-lab-nu/eai-dexhand` (`images/dexhand/`, tag from `images/dexhand/VERSION`) contains MuJoCo 3.4.0,
numpy, scipy, imageio and OSMesa (`images/dexhand/requirements.txt`) and bakes the three asset sets: Sharpa Wave at
`/opt/dexhand/hand`, the Wuji physics subset at `/opt/dexhand/wuji_v2_2` and the Tianji meshes at `/opt/dexhand/tianji`
(`TIANJI_ASSET_DIR`). `python3 images/dexhand/prepare_assets.py` fetches all three from their pinned public sources
into the ignored `images/dexhand/assets/` and checks every file against `asset-manifest.json`,
`wuji-asset-manifest.json` and `tianji-asset-manifest.json` (the Tianji meshes are rebuilt by the pinned conversion
`images/dexhand/tianji/tianji_model.py` and must match byte for byte). Task code is not in the image: each task
directory carries its own runtime copy. No asset, policy or demonstration is downloaded at run time, and the image
holds no reference trajectory.

## World-frame facts in instructions (D7)

DexHand instructions state the frozen static layout of each scene in world coordinates (metres, z up): the locked
wrist pose of the essential families, table-top height and edge, support, shelf and target positions, an object's
initial extent, fold lines, workspace boxes and every threshold of the success and failure predicates. They never
state an object's state after reset beyond what the frozen instance fixes, nor any planned motion. The same rule
holds in both modes; in standard mode the agent measures everything else through cameras, depth, its own joints and
forward kinematics.

## Essential dexterity families

Six fixed-wrist scenes isolate finger control. Each family owns its folder `scripts/dexhand/task_library/<family>/`
(`task.json`, `scene.py`, `assets/` with `manifest.json` and credits, `render.json`, `README.md`, the oracle under
`solution/`, `wuji_reset.json` where declared); `task_library/index.json` registers them, `library.py` validates the
registration and asset inventory, and `sync_essential_catalog.py` freezes them into `essential_catalog.json`, the
specification the generator renders (its full entry is each task's `instance.json` and `catalog.json`).

All six wrist targets are locked; the runtime rejects any row that changes them (float32 wire rounding is accepted
and normalized). Finger targets keep the manufacturer's joint and force limits; Sharpa velocity feedback is
dissipative with its coefficient frozen in the instance. Objects have no motors, welds, attachments, compensating
forces or scripted motion. Features are computed from MuJoCo state, contact pairs and contact forces by
`shared/checker.py`: ordered stages with consecutive holds, guards while a stage is active, global invariants and a
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

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 20`, `0 <= palm_drift <= 0.006`, `0 <= wrist_rotation <= 0.035`, `support == 0`, `0 <= body_drift <= 0.02`, `0 <= body_rotation <= 0.35` (0.24 before 2026-10-14, see below). Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

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

Invariants at every 2 ms substep (fail-fast): `0 <= force <= 80`, `0 <= speed <= 20`, `0 <= palm_drift <= 0.006`, `0 <= wrist_rotation <= 0.035`, `support == 0`, `0 <= body_drift <= 0.02`, `0 <= body_rotation <= 0.35` (0.24 before 2026-10-14, see below). Locked wrist targets: `[-0.08, 0, 0.29, 0, 0, 0]`.

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
`scripts/dexhand/verify_oracles.py` binds it to the recorded evidence (archive hash, Sharpa model hash, two fresh
replays ending in the validated final state hash, and success of the float32-rounded rows). All six also carry a
Wuji oracle, `solution/wuji/trajectory.npz` (see
Wuji reference solutions), with its authoring script under the family folder's `tools/`.
`scripts/dexhand/tests/test_essential_strict.py` covers the oracle (and each Wuji oracle: two fresh replays ending
in its recorded final hash), the no-op, a truncated oracle, a dropped object
(fail-fast and permanent), forged archive members, wrong widths and hand labels, task and actuator-name mismatches
and NaN, empty and object arrays, for both hands. The Wuji resets are declared in
`wuji_reset.json` (pen, knob, walnuts: finger targets, for the walnuts also their start poses) or neutral (cube,
Joy-Con, sphere rest on the neutral Wuji hand).

## Hamburger assembly (`assemble_hamburger`)

`scripts/dexhand/families/assemble_hamburger/` (plugin family). The bottom bun starts on the plate; patty, cheese,
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
same wrist stage (26-wide rows, fingers at 0). Authoring tests: `test_task.py` (order, missing layer, drop, below
table, workspace, bend limit, actuator-only knock-off, forged members, widths, hand labels, Wuji determinism).

## Paper half-fold (`paper_half_fold`)

`scripts/dexhand/families/paper_half_fold/` (plugin family; the accepted T06 scene). A 160 x 100 mm, 1.28 g sheet lies
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

`scripts/dexhand/families/sweep_dustpan/` (plugin family; the accepted T13 scene). A fixed Tianji Marvin base with two
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

`scripts/dexhand/families/pot_shelf_transfer/` (plugin family; the accepted T17 scene). Two Tianji Marvin seven-joint
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
time (`timeout_sec` minus 180 s, at most `video_timeout_s`, which is never below the replay timeout); it never changes the verdict (board 0136, 2026-10-16: before, the privileged
verifier rendered no video at all). The essential families' `replay.py` films every 2nd step, at most 1500 frames
(`VIDEO_MAX_FRAMES`; a 640x480 OSMesa frame costs ~0.3 s on one core, so a 28k-step episode took over an hour before).

**Standard** (`eai-standard/2.2`, docs/STANDARD_MODE.md Part 2). The agent gets the shared client (`rcb_client`) and no
simulator code. The `sim` sidecar (`scripts/dexhand/shared/standard/server.py` on the unmodified shared layer
`scripts/eai_standard/`) serves calibrated RGB and depth, the robot's own joints, efforts and link poses and
robot-link forward kinematics; object poses, contact forces, checker stages and scene bodies are not served. The
reset budget is 20 (`budget.reset`, `RCB_RESET_BUDGET` in the compose file; see "Standard-mode resets" below); every
action, watch step and reset is journaled, and a crashed service resumes the same episode from its journal, resetting
where the committed resets did (resume class `exact`). The control rate is the family's (`spec()["control_hz"]`); the agent's clock
(`meta["time_left_s"]`) counts from its first request. The collect hook (`finalize.sh` / `finalize.py`) ends the
episode, replays `/data/trajectory.npz` twice in fresh processes with the recorded hand, seals `final.json` and then
renders an evidence video (`/data/replay.mp4`) in the collect hook's remaining time (its `timeout_sec` minus 60 s, at most `video_timeout_s` >= the replay timeout;
before 2026-10-16 a fixed 300 s, which cut episodes of more than ~10k steps); the separate verifier reads only `final.json` and needs live success, both replay successes,
identical replay hashes and replay hash = live hash. Missing trusted evidence is an infrastructure error; the video
never decides a verdict.

**Oracles.** The generator owns the oracle runners (`scripts/dexhand/shared/solution/`): privileged `solve.sh`
re-saves the family's rows to `/app/output/trajectory.npz`; standard `solve.sh` submits the same rows as float64
through the client's request path (`hold`, dt = 1 / control rate, chunks of at most 250 rows or 10 s) and resumes after
a service restart. Rows above the repository's 2 MB file limit are stored as `trajectory.json` + `trajectory.partNN.npz`
(`shared/solution/solution_parts.py`) and concatenated and sha256-checked before use. A family with a per-hand
solution gets `solution/<hand>/` and the `*_by_hand.sh` runner (Wuji reference solutions, above).

**Harbor results** (Harbor 0.23, `eai-dexhand:0.2.0` built from this branch, CPU only, `RCB_LIMITS_ENFORCE=0`,
2026-10-14; the pull request lists every trial):

| Family | privileged oracle / nop | standard oracle / nop | standard oracle wall | peak GiB: privileged verifier / standard sim | Wuji |
|---|---|---|---|---|---|
| `essential_cube_layer` | 1 / 0 | 1 / 0 | 4 min | 0.39 / 0.61 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |
| `essential_held_joystick` | 1 / 0 | 1 / 0 | 4 min | 0.51 / 0.70 | Wuji oracle 1 in both modes; standard nop 0 |
| `essential_pen_regrasp` | 1 / 0 | 1 / 0 | 4 min | 0.41 / 0.63 | Wuji oracle 1 in both modes; standard nop 0 |
| `essential_two_object` | 1 / 0 | 1 / 0 | 4 min | 0.45 / 0.67 | Wuji oracle 1 in both modes; nop 0 and 12 s hold 0, both modes (hold: deterministic, live = replay) |
| `essential_rotary_gait` | 1 / 0 | 1 / 0 | 17 min | 0.49 / 0.70 | Wuji oracle 1 in both modes; standard nop 0 |
| `essential_cube_reorient` | 1 / 0 | 1 / 0 | 2 min | 0.39 / 0.61 | Wuji oracle 1 in both modes; standard nop 0 |
| `assemble_hamburger` | 1 / 0 | 1 / 0 | 9 min | 0.41 / 0.63 | Wuji oracle 1 in both modes; standard nop 0 |
| `paper_half_fold` | 1 / 0 | 1 / 0 | 5 min | 0.50 / 0.64 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |
| `sweep_dustpan` | 1 / 0 | 1 / 0 | 38 min | 3.68 / 2.31 | nop 0 and 12 s hold 0, both modes (hold: deterministic, live = replay) |
| `pot_shelf_transfer` | 1 / 0 | 1 / 0 | 5 min | 3.42 / 2.17 | Wuji oracle 1 in both modes; privileged nop 0; standard nop 0 |

The standard wall time is the whole trial: the live episode, then the collect hook's two fresh-process replays and the evidence video. sweep_dustpan's live oracle episode took 11.7 min of the agent phase (530 calls of at most 250 rows at 2 kHz). Peaks are cgroup `memory.peak` of the verifier container (privileged; two concurrent replays) and of the `sim` sidecar over the whole trial (standard); the agent containers stayed below 0.25 GiB. Wuji oracle: the packaged Wuji solution with `DEXHAND_HAND=wuji` (privileged: Harbor's `--ae DEXHAND_HAND=wuji`; standard: the sim service's hand) scores 1 with `hand_wuji = 1`, deterministic, and in standard mode live = replay (the Sharpa oracles and no-ops of these nine families were re-run with the per-hand `solve.sh`: 1 and 0). Wuji: `DEXHAND_HAND=wuji` trials (every family's standard no-op; for `essential_two_object` and `sweep_dustpan` also the privileged no-op and a 12 s hold of the Wuji start in both modes) all score 0 with no infrastructure error; the standard trials and the privileged holds report `hand_wuji = 1` (a privileged no-op hands in nothing: `missing_trajectory = 1`).

### Standard-mode resets (owner, 2026-10-14, board 0109)

`budget.reset = 20`, DexToolBench's value (PROTOCOL §4.5): an essential family starts with the object already in the
hand, every family ends an episode at the first failure (a dropped, slipped or knocked object, a bound exceeded), and
the agent has no simulator of its own in standard mode, so with one episode the first slip decided the trial. The
capability is the one of docs/STANDARD_MODE.md ("Optional reset capability"), implemented in the DexHand adapter
`scripts/dexhand/shared/standard/server.py` the way the MyoSuite 2.2 service implements it (the shared 2.2 layer has
no reset): `POST /reset` (JSON or RCB1 `{cameras, video_fps, depth}`, no physics) calls the family's
`Session.reset()` and returns the new episode's first frames; 409 after a success, once the budget is spent and after
the agent's time; `/status` and every meta add `episode`, `resets_left` and `control_steps_total`. Only the last
episode is graded: `trajectory.npz` holds its rows, the collect hook replays them from the frozen start as before, and
`reward.json` adds `resets` and `reset_budget`. `Session.reset()` restores the frozen start exactly in all ten families
(checked 2026-10-14 for both hands where offered: after k rows and a reset, the state hash equals a fresh process's, and
the same rows then end in the same hash as in a fresh process). `RCB_RESET_BUDGET=0` still runs one episode.
Results with a different budget are reported separately.

### In-hand cameras of the essential families (2026-10-14, board 0109)

Standard mode serves no object state, and the in-hand pose decides every essential predicate (joystick, layer, knob,
sphere and pen angles within 0.1-0.16 rad windows). The object was 40-60 px wide in `overview`, and `palm` (mounted
behind the wrist) sees the back of the hand. The essential scenes therefore add two cameras mounted on the locked hand
body like `palm`: `inhand_top` (from above the palm) and `inhand_side` (from the thumb side), both about 0.2 m from the
grasp region, `fovy` 45, 640 x 480. The standard service returns `overview` and `inhand_top` by default. Calibration:
the published `intrinsic_cv` / extrinsics project known world points to within the review's tolerance (see the board
0109 report). The cameras do not change physics or state hashes, so the oracles are unchanged.

### Held-object rotation bound (2026-10-14, board 0109)

`essential_held_joystick` and `essential_cube_layer` share the invariant "keep the held object steady",
`body_rotation <= 0.24` rad. The Sharpa reference solutions peak at 0.2396 rad (joystick) and 0.218 rad (cube layer),
so the bound was the joystick reference's own peak (0.0004 rad of margin). The bound is now 0.35 rad (20 degrees) in
both families; the task's intent is unchanged. Perturbation checks of the references (finger targets +-0.001 rad
uniform jitter, six seeds; the bound relaxed to measure its peak): the joystick reference's peak rotation within its
own 415 rows is 0.27-0.29 rad (below 0.35), but the open-loop rows then miss the first checkpoint, so it still fails
under jitter for reasons the bound does not decide; the Wuji joystick reference succeeds 4/6 (peak 0.07 rad); the cube
layer reference 1/6 (peak 0.21-0.25 rad; the other five stall at the second or third stage, also with 100 extra held
controls). `essential_cube_reorient` (the review's "6/6 fail at 0.001
rad"): its reference ends on the very control that completes the terminal hold, so a perturbed copy runs out of rows
one to nine controls short; with the last row held for 100 more controls all six jittered copies succeed (no bound is
approached: contacts >= 1, displacement <= 0.021 m, speed <= 11.7 of 12). Its Wuji reference is fragile at the start
(four of six jittered copies drop the sphere within 31 controls, the other two never complete the first stage). Open-loop references are not robust controllers;
with resets and closed-loop observation an agent can retry, which is what the reset budget is for.

## Generator

`scripts/dexhand/generate.py` renders both modes of every registered family and ends with
`scripts/task_conventions.py` `normalize` (resources, limits, monitor, `## External material`, `## Time limit`, seeds,
README layout, test.sh). Never edit a generated task file: edit the family's sources and regenerate.

- `scripts/dexhand/release.json` lists the ten families; `--release` renders or checks only them.
- The six essential families come from `task_library/` (above). A plugin family is a folder
  `scripts/dexhand/families/<family>/` with a `family.json` (directory scan, no central list): its runtime files and
  asset folders, hands and per-hand widths, robot name, row limit, control rate, instruction and README texts
  (`{{HANDS}}`, `{{MAX_ROWS}}`, `{{CONTROL_HZ}}`, ... placeholders), oracle files, metadata and grader timeouts
  (`replay_sec`, `video_sec` (raised to `replay_sec` if lower: the video replays the episode again), verifier and collect limits). The agent's time limit is not a family setting.
- Shared sources, copied unchanged into every task (`ci_checks/check-tooling-identity.sh`): `rcb_dexhand.py`,
  `hands.py`, the privileged and standard graders, the standard service, its collect hook and the `eai-standard/2.2`
  layer.

```bash
python3 images/dexhand/prepare_assets.py                       # the pinned hand and arm assets (image build only)
python3 scripts/dexhand/generate.py --release                  # write the 20 task directories
python3 scripts/dexhand/generate.py --check --release          # compare tasks/ with a clean render (CI)
python3 scripts/dexhand/generate.py --list                     # families, sources, release membership
cd tasks && harbor add --scan . && cd ..                       # refresh tasks/dataset.toml
python3 scripts/task_conventions.py --check tasks/dexhand-*
bash ci_checks/run_all.sh tasks/dexhand-*
python3 scripts/dexhand/tests/test_grading.py                  # graders on stub replays (standard library only)
# with images/dexhand/requirements.txt and pytest installed, and DEXHAND_ASSET_DIR / WUJI_ASSET_DIR / TIANJI_ASSET_DIR
# pointing at the prepared images/dexhand/assets/{hand,wuji_v2_2,tianji}; one process per suite:
python3 -m pytest scripts/dexhand/tests
python3 -m pytest scripts/dexhand/families/assemble_hamburger/test_task.py
for f in paper_half_fold pot_shelf_transfer sweep_dustpan; do python3 -m pytest scripts/dexhand/families/$f/tests; done
```

`scripts/dexhand/verify_oracles.py` re-binds the essential oracles to their recorded evidence; it needs the authors'
evidence directory, which is not in the repository. The plugin families keep the same kind of tool in their own
`tools/` folders, with the same caveat.

## Limits of the models

The wrist stage is a positioning mechanism, not an arm. The cube layer is a one-face hinge abstraction, the pen and
Joy-Con are size-adapted rigid meshes, the walnut scans use convex collision hulls without concavities, cheese and
lettuce are articulated strips, the paper is a reduced shell with uncalibrated material, and the debris pieces are
rigid. The graders claim only the mechanical outcomes these models represent.

## Standard-mode service details (moved from STANDARD_MODE.md, 2026-10-14)

Serves `eai-standard/2.2`. Resume class `exact` (MuJoCo 3.4.0, CPU physics, one thread; a frozen scene rebuilt from its pinned model files; one control row is one or more fixed physics steps). Its service implements the optional reset capability (STANDARD_MODE Part 1); the 2.2 client has no `reset()`, so the instructions call `POST /reset` through `Robot._post`.
