# DexHand

## Overview

Dexterous-hand manipulation in MuJoCo 3.4.0 (CPU physics, software rendering): thirty task families, each with one
frozen scene, in privileged and standard mode (60 task directories, `dexhand-<family>-i00-{privileged,standard}`).
Six essential families isolate finger control with the wrist locked; the other twenty-four are household and assembly
scenes for one or two hands on wrist stages or on a fixed dual-arm stand.

| | |
|---|---|
| upstream | none: an original suite of this repository (the default hand model is MuJoCo Menagerie's Sharpa Wave) |
| simulator | MuJoCo 3.4.0, CPU, one thread |
| robots | `sharpa-wave-floating`: one right hand on a six-DoF actuated wrist stage (no arm) · `sharpa-wave-floating-bimanual`: two hands, each on its own wrist stage · `marvin-bimanual-sharpa-wave`: the Tianji Marvin fixed stand with two 7-joint arms and a hand on each wrist (one-hand families keep the other arm parked) |
| hands | Sharpa Wave (22 finger actuators, the default) or Wuji Hand 2.2 (20), selected per run |
| tasks | 30 families × 2 modes; the family table is under Tasks |
| image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0` (`images/dexhand/`); no GPU needed |
| reference solutions | every family: a recorded physical Sharpa Wave episode (`oracle = "full"`); eleven families also carry a Wuji Hand 2.2 episode, which the oracle uses when the run selects Wuji |

There is no assisted grasp in any family: no welds, attachments, scripted object motion or applied forces. Objects move
only through contact and gravity, and only the robot's actuator targets act on the scene. The agent's time limit is
1 h in both modes.

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/dexhand -a <agent>
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | the family's full MuJoCo model and state (`rcb_dexhand.Session`) | unlimited | its `trajectory.npz`, replayed once in a fresh process |
| standard | calibrated RGB and depth, the robot's own joints, efforts and link poses, robot-link forward kinematics; no object poses, no contact forces, no success signal | 20 | the last episode, as it ran (live; nothing replayed) |

## Upstream and license

DexHand has no upstream benchmark: the scenes, checkers, graders and the standard service are original to this
repository (MIT License). Third-party models and assets, all pinned and checked by sha256 when the image is built
(`images/dexhand/prepare_assets.py` against `asset-manifest.json`, `wuji-asset-manifest.json` and
`tianji-asset-manifest.json`):

| component | source (pinned) | license | image path |
|---|---|---|---|
| Sharpa Wave hand (`sharpa`, default) | MuJoCo Menagerie `sharpa_wave` @ `0059d4335f8156206f63a35662313385f7ad6d74` (from Sharpa Robotics `6eea427eb24189519f32b9f21674cd534d3f973c`) | Apache-2.0 | `/opt/dexhand/hand` |
| Wuji Hand 2.2 (`wuji`, model `hand2/hand2_2`) | `wuji-technology/wuji-description` @ `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` | MIT | `/opt/dexhand/wuji_v2_2` |
| Tianji Marvin arms | meshes from DexForce `embodichain_data` (`TianjiMarvin.zip`), inertias from Genesis' `dual_arms_primitives.urdf`; rebuilt by `images/dexhand/tianji/tianji_model.py` (`images/dexhand/tianji/NOTICE.md`) | Apache-2.0 (meshes), MIT (inertias) | `/opt/dexhand/tianji` |

Object assets: the Joy-Con, pen, rotary-knob and walnut meshes are CC BY 4.0 (credits in each essential task's
`object_assets/*/CREDITS.txt`); the rubber boot (Poly Haven), the stockpot (Innerscene Harvest Pot) and Monet's *Water
Lilies* (1906, Art Institute of Chicago) are CC0 or public domain; page, cover and letter artwork is original (CC0,
`ORIGINAL_CONTENT_LICENSE.txt`); printed text uses the DejaVu fonts (Bitstream Vera license). All other geometry is
original. No non-commercial terms apply.

## Changes from upstream

There is no upstream to differ from. What the models leave out, so that the graders claim only the mechanical outcomes
they represent:

- The wrist stage is a positioning mechanism (three prismatic and three serial revolute joints, position-actuated under
  native force bounds), not a model of a commercial arm. The six essential families lock all six wrist joints with
  native equality constraints.
- The cube layer is a one-face hinge abstraction, not a six-face puzzle; the pen and the Joy-Con are size-adapted
  rigid meshes; the walnut scans collide as convex hulls; cheese and lettuce are hinged strips; the paper is a reduced
  elastic-plastic shell with uncalibrated material; debris pieces are rigid.
- Coffee, batter, air and the liquid in a glass are not simulated: checker quantities stand for them (whisk-head
  revolutions, a stroke count, glass tilt). Threads, staples and latch springs are reduced to contact geometry or
  passive joints, and static props stand in for parts a task does not move.
- The Wuji Hand 2.2 is mounted in the Sharpa Wave's place (`hands.replace_wave_hands`): the manufacturer's MJCF inside
  a fixed wrapper with the same name and pose, rotated so that fingers, palm normal and thumb side align. Everything
  above the mount (wrist stage or arms, objects, physics options) is unchanged. In the essential families the Wuji
  collision geoms are renamed to the predicate's finger and palm roles (meshes and contact parameters unchanged), so
  per-finger contact counts mean the same for both hands. Each family declares a Wuji start pose of the fingers (or
  neutral fingers); `essential_two_object` also places both walnuts in the Wuji grasp, and `sweep_dustpan` closes the
  Wuji fingers on the frozen tool shafts. Predicates and failure rules are the same for both hands.

## Interface

World frame in every family: metres, z up. Each instruction states the frozen static layout of its scene in world
coordinates (the locked wrist pose of the essential families, table heights and edges, supports, targets, work boxes)
and every threshold of its success and failure rules; never an object's state beyond what the frozen instance fixes.

**Rows.** One row holds one target per actuator, in `Session.actuator_names` order (privileged) or
`spec()["action_types"]["joint_position"]["layout"]` order (standard):
- wrist-stage families: `wrist_x, wrist_y, wrist_z` (m), `wrist_rx, wrist_ry, wrist_rz` (rad, serial XYZ joints), then
  the finger targets: Sharpa Wave 22 (`right_thumb_CMC_FE ... right_pinky_DIP`, 28 in all), Wuji Hand 2.2 20
  (`r_wuji_r_THJ0..3`, `FFJ0..3`, `MFJ0..3`, `RFJ0..3`, `LFJ0..3`, 26 in all); two wrist stages: 56 / 52;
- dual-arm families: the 14 arm joint targets (left J1-J7, right J1-J7), then the left and the right hand's finger
  targets: 58 (Sharpa Wave) or 54 (Wuji).
Finger targets are radians within `model.actuator_ctrlrange`. Most families step 50 Hz controls; `sweep_dustpan`
(one 0.5 ms physics step per row) and `pot_shelf_transfer` (one 2 ms step per row) take one row per physics step.

**Hand selection.** Privileged: `Session(task, hand="wuji")`, else the environment variable `DEXHAND_HAND`, else
`sharpa`; an unknown id is an error. Standard: `DEXHAND_HAND` on the `sim` service, read once at start (the compose file
passes `DEXHAND_HAND: ${DEXHAND_HAND:-sharpa}`); `spec()["hand"]` names it and the agent cannot switch it.

**Privileged.** `from rcb_dexhand import Session` (the family's `runtime.py`, in `/opt/tools`): the full MuJoCo model
and state, exact resets, snapshots where the family offers them, renders and `replay`. The deliverable is
`/app/output/trajectory.npz` (`actions` `(T, width)`, `hand`, optionally `task` and `actuator_names`, written by
`s.save_trajectory`; at most 64 MB, so it is saved compressed) and the script that made it, `/app/output/gen.py`.

**Standard** (`eai-standard/3.0`). The agent gets the shared client (`/opt/tools/rcb_client.py`) and the same service
as MCP tools, and no simulator code. The control rate is the family's (`spec()["control_hz"]`). DexHand's service adds
the optional reset capability: `POST /reset` (MCP tool `reset`; the client has no `reset()` call) starts a new episode
from the frozen start, up to 20 times (`RCB_RESET_BUDGET`). Twenty, because an essential family starts with the object
already in the hand and every family ends an episode at its first failure, so with one episode the first slip would
decide the trial. The essential scenes add two cameras mounted on the locked hand body, `inhand_top` and
`inhand_side` (about 0.2 m from the grasp, `fovy` 45, 640 × 480), because their predicates turn on in-hand angles that
the overview camera resolves poorly; the service returns `overview` and `inhand_top` by default. Cameras do not change
the physics.

## Grading

Every family's verdict comes from its own trusted runtime and checker, from simulator state only: ordered stages, a
final hold over consecutive samples, and failure rules that end the episode at once and permanently (a dropped,
knocked or slipped object, an object out of its work box, a bound exceeded, unstable physics). There is no partial
credit. Each task README's Success criteria give the exact conditions, thresholds and rates of its family.

**Privileged: one replay.** The separate verifier (no network) runs `tests/grade.py`: one fresh-process replay of the
archive through the family's `replay.py`, open-loop, with the hand the archive names; reward 1 iff it ends in success.
The replay stops at the first success or failure. A missing file is `missing_trajectory`; a file over 64 MB, a row
width that does not match the hand, an unknown hand label, a `task` or `actuator_names` mismatch, non-finite values,
too many rows, a target outside its actuator's range or, in the essential families, a row that changes the locked wrist
targets beyond float32 rounding is `bad_trajectory`; both score 0. Rows are never padded, truncated or converted between
hands. `tests/checked_replay.py` checks every scene the replay builds against the frozen start recorded in
`instance.json` (`start_state_sha`, per hand); a scene that starts elsewhere is `instance_mismatch`, an infrastructure
error, and no row is replayed.

**Standard: the live episode.** The `sim` service judges the episode it ran (the last one after resets) with the same
runtime and checker; nothing is replayed. A success is never shown and never ends the episode: the family runtime
latches it, and the service restores the verdict state so physics and the checks go on, and judges the state the
episode ends in. Earlier stages count as they happened. A failure ends the episode as a 0, also after a success. The
families with an episode budget (all but the six essential ones; the table below) end the episode there. Targets
are clipped to the published ranges. At the start of every fresh episode and after every `POST /reset` the service
checks the frozen instance's files against `grading.json` (`instance_sha256`) and the built state against
`start_state_sha`; a mismatch is an infrastructure error. In the essential families a request with a row that moves
the locked wrist is refused (HTTP 400) at that row.

## Tasks

Thirty families, one frozen instance each (`i00`), in both modes. Row widths are Sharpa Wave / Wuji Hand 2.2. The
budget is the episode budget in rows (control steps, or physics steps for the two one-row-per-step families); the
privileged archive may hold at most "row limit" rows.

| Family | Robot | Row width | Control | Budget | Row limit |
|---|---|---|---|---|---|
| `essential_cube_layer` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | none | 50,000 |
| `essential_held_joystick` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | none | 50,000 |
| `essential_pen_regrasp` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | none | 50,000 |
| `essential_two_object` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | none | 50,000 |
| `essential_rotary_gait` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | none | 50,000 |
| `essential_cube_reorient` | hand on a locked six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | none | 50,000 |
| `assemble_hamburger` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 7,500 (150 s) | 7,500 |
| `paper_half_fold` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 40 x 0.5 ms | 1,500 (30 s) | 1,500 |
| `sweep_dustpan` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 2000 Hz, one 0.5 ms step | 160,000 (80 s) | 160,000 |
| `pot_shelf_transfer` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 500 Hz, one 2 ms step | 30,000 (60 s) | 30,000 |
| `remote_battery_swap` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `coffee_stir` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `jar_lid_open` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `grinder_crank` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `pancake_serve` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 20 x 1 ms | 3,000 (60 s) | 3,000 |
| `vacuum_bin_reseat` | two hands, each on its own six-DoF wrist stage | 56 / 52 | 50 Hz, 20 x 1 ms | 3,000 (60 s) | 3,000 |
| `drying_rack_unfold` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `picture_hang` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `usb_plug_insert` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `fan_guard_install` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `stool_brace_insert` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `ram_module_install` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `boot_sole_brush` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `paper_staple` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `binder_page_load` | hand on a six-DoF wrist stage | 28 / 26 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `envelope_letter_insert` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 6,000 (120 s) | 6,000 |
| `book_page_turn` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `tray_glass_carry` | two hands, each on its own six-DoF wrist stage | 56 / 52 | 50 Hz, 10 x 2 ms | 3,000 (60 s) | 3,000 |
| `batter_whisk` | two Tianji Marvin 7-DoF arms, a hand on each | 58 / 54 | 50 Hz, 10 x 2 ms | 4,000 (80 s) | 4,000 |
| `bicycle_pump_stroke` | one Tianji Marvin 7-DoF arm and hand (the other arm parked) | 58 / 54 | 50 Hz, 10 x 2 ms | 5,000 (100 s) | 5,000 |

Families with a Wuji Hand 2.2 reference solution (`solution/wuji/`, picked by `solve.sh` when the run selects Wuji):
the six essential families, `assemble_hamburger`, `paper_half_fold`, `pot_shelf_transfer`, `jar_lid_open` and
`tray_glass_carry`. The other families' oracles hand in the Sharpa Wave rows.

The task directories are the deliverable; the tooling that built them is kept outside this repository. Every task
carries the same copies (`ci_checks/check-tooling-identity.sh`) of `rcb_dexhand.py`, `hands.py`, the graders and the
standard service. Each family's scene, checker, frozen `instance.json` / `task.json` / `catalog.json` and assets are
in its own task directories.

```bash
python3 images/dexhand/prepare_assets.py                       # the pinned hand and arm assets (image build only)
python3 scripts/task_conventions.py --check tasks/dexhand/*
```
