# vacuum_bin_reseat (authoring notes)

Scene T19 "Remove and reinstall a vacuum dust bin" of the scene-expansion delivery, turned into a physical DexHand
task: two dexterous hands (Sharpa Wave default, Wuji Hand 2.2 selectable), each on its own six-axis wrist stage. The
left hand holds the free-standing handheld vacuum by its handle; the right hand presses the spring release button, takes
the free dust bin off, puts it back tabs-first and closes it until the latch tooth snaps behind the bin's catch; both
let go and the reinstalled state must hold for 1 s. Wave 3 (2026-10-15): the source latch friction 0.55 and button
travel 6 mm are restored, which needs the second hand (see "Wave-3 changes").

## Files

| file | role |
|---|---|
| `scene.py` | builds the MJCF: Sharpa `right_hand.xml` on the right wrist stage, its mirror (`arm_rig.mirrored_left_wave`) on the left wrist stage (+ `hands.replace_wave_hands` for Wuji) and the native T19 scene from `assets/vacuum_scene.xml`; a Marvin-arm code path (`"rig": "marvin"`) is kept but unused |
| `checker.py` | ordered stages, terminal hold, fail-fast, all from simulator state |
| `runtime.py` | `Session` (FAMILY_PLUGIN section 4, plus `snapshot` / `restore`) |
| `replay.py` | fresh-process replay CLI (FAMILY_PLUGIN section 5), optional `--video` |
| `task.json` | frozen instance: physics, wrist stage, reset, checker thresholds, documented geometry adaptations |
| `assets/` | `vacuum_scene.xml` and `initial_state.npz` copied verbatim from the T19 source, `manifest.json` (sha256 + size, checked at every build) |
| `author.py` | authoring-only closed-loop controller that records the oracle rows (not shipped) |
| `solution/trajectory.npz` | two-hand Sharpa oracle rows (1,331 rows; success at control 1,181); the standard oracle submits the same rows |
| `tools/check_oracle.py` | oracle audit (stage timeline, peak unsupported fall, vacuum displacement, penetration) + negative variants replayed in fresh processes |
| `tests/test_vacuum_bin_reseat.py` | authoring tests: model/actuation, settled reset, text-independent state hash, oracle in fresh processes and float32, nop/partial/no-press, drop-and-catch and knock fail-fast, forged members, malformed rows, Wuji |
| `tools/film_export.py`, `tools/studio_renderer.py` | authoring-only PR film: MuJoCo replay to a pose bundle, rendered with the accepted T19 studio renderer (Blender 4.5.3) |

## Provenance

`assets/vacuum_scene.xml` = `robot_coding_bench/scripts/scene_expansion/tasks/vacuum_dustbin/meta_delivery_trajectory_r1/assets/model.xml`
(sha256 `834dbc8f49c71679ac885a3b0c43e4eed8999b73ff0102c4ca995a4a8453c012`; identical to the T19 scene-r5 export and,
up to a trailing newline, to `scripts/hand_support/tasks/T19/model.xml`). Reduced Bosch UniversalVac18 geometry
authored for the scene-expansion delivery (no manufacturer CAD): motor housing, open handle, tapered smoke-transparent
bin, accessory port, rectangular filter, lower seat ledges and lips, top release button (passive slide, native spring
600 N/m with 1 mm preload) carrying the ramped latch tooth. Native masses: vacuum body 0.752 kg (battery removed), bin
0.18 kg, button 5 g.

## Physics and modelling choices (all deliberate, all in `task.json`)

- Physics: MuJoCo 3.4.0, implicitfast, elliptic cones, impratio 10, dt 1 ms (the native scene used 0.1 ms; the bin
  shell pieces are 1-3 mm thick), 20 substeps per 50 Hz control. Native contact parameters are kept.
- Reset: the native assembled pose settled for 3 s under gravity with the hand away (`initial_object_qpos`); the seated
  bin pose in the vacuum-body frame (`checker.seat_pos/seat_rot`) is that settled pose.
- Button-guide contact pairs: the native direct-stiffness `solref -12000000 -6928` is unstable at 1 ms; replaced by
  `solref 0.002 1` (`guide_pair`).
- `base_skids`: a 4 mm black rubber skid under the housing (friction 1.2). The native rounded convex housing hull rocks
  and creeps on the counter; with the skid the vacuum stands still and level as in the film.
- Button travel: the source's 6 mm (wave 2 used 7.5 mm and moved the lower guide stop); a 5.9 mm press releases the
  seated bin (the checker needs >= 5.8 mm).
- `visual_only_prefixes`: the filter frame, pleats and cartridge and the lower-seat lips are kept visible but do not
  collide. In the native geometry the filter frame protrudes into the bin mouth and, together with the lower lips and
  the ledges inside the mouth, leaves no collision-free removal path (the source itself reports 3.66 mm of buried
  lip/shell interference along its prescribed path). With these changes the bin is retained by the ledge clamp at the
  bottom (tabs on the ledges, shell under them) and the latch at the top, tips forward onto the counter edge when the
  button is pressed, and comes off by sliding the tabs off the ledges.
- Latch friction: the source's 0.55 on tooth, catch and bridge (wave 2 used 0.15). With 0.55 the closing push needed to
  ride the catch over the ramp drags an unheld vacuum 50 mm (wave-3 probe: the wave-2 one-hand controller fails with
  `vacuum_body_disturbed` at the closing push), so a second hand holds the vacuum by its handle (hook grip: a ramped
  probe force of 30 N along the vacuum axis moves the held vacuum < 1 mm).
- Second hand: the right Wave mirrored in y on a second six-axis wrist stage (`left_wrist_stage`, same joints, gains and
  ranges as the right one, hand mounted without rotation).
- `latch_lips`: a 2 mm fixed lip on the housing 0.7 mm above the bin's latch bridge (review VR-1: the authored tooth
  only resisted the tilt, and a 2.3-2.6 N straight pull lifted the bin out with the button up). With the lip, ramped
  probe pulls of up to 25 N on the seated bin with the button up (up, out, out+up at the COM; up and out at the nozzle)
  never separate it by 30 mm: the 0.93 kg vacuum is dragged or lifted 50 mm first (4-6 N), which fails the episode;
  with the button pressed the bin comes free at 0.17 N. The checker still requires the >= 5.8 mm press while the bin
  is seated before the removal counts. The lip does not touch the bin at rest or along the oracle path; the oracle
  rows were re-recorded with the lip (author.py reproduces them bit for bit) and succeed at control 869.
- Soft fingertip contact (review VR-2): during the oracle's press the vendor's soft Sharpa fingertip (solref 0.06)
  sits up to 9 mm into the button cap and 5 mm into the housing hull under the ~19 N press; renders may show the
  fingertip sunk into the cap.
- Supported-drop notion (review VR-3): a bin sliding down a hand while still touching a finger is "supported"; only
  falls faster than 0.6 m/s without any contact, or faster than 0.99 m/s with contact, fail.
- Drop detection has no debounce window: an unsupported bin (no active contact) falling faster than 0.55 m/s fails at
  that substep; any bin falling faster than 0.99 m/s (free fall from 5 cm) fails as well. The designed release tip of
  the bin onto the counter edge peaks at 0.47 m/s with no contact (per substep; 0.41 m/s at control rate).
- `state_sha` hashes the integration state, the predicate state, the hand and the physics/predicate parameters of
  `task.json` only (prose keys excluded), so text edits never change evidence hashes.

## Predicate (checker.py, thresholds in `task.json` `checker`)

1. released + removed: button travel >= 5.8 mm while the bin origin is within 5 mm of its seated pose, then the bin
   origin > 30 mm from the seated pose (vacuum-body frame).
2. reinstalled (after 1): bin origin within 3 mm and orientation within 0.05 rad of the seated pose, button travel
   <= 1.5 mm (tooth up), catch inner face at most 0.5 mm in front of the tooth face.
3. terminal hold: condition 2 with no hand contact on bin / vacuum / button, bin and vacuum speed <= 0.01 m/s, bin
   angular speed <= 0.1 rad/s, 50 consecutive controls. Success ends the episode; losing the seat drops back to 1.

Fail-fast (every 1 ms substep): vacuum displaced > 50 mm or tilted > 0.35 rad; bin downward speed > 0.99 m/s (free
fall from 5 cm), bin touching floor or table leg, bin origin below the counter top (0.65 m) or outside the workspace
box; bin/vacuum penetration > 4 mm; unstable physics; 3000-control budget.

## Film (presentation only)

`tools/film_export.py` replays the oracle in MuJoCo and samples every second control (25 fps, 1x); the bundle is
rendered by `tools/studio_renderer.py` (the accepted T19 film renderer: materials, lights and Blender settings; caption
names the hand and says "physics replay, 1x"). Presentation-only changes, recorded in the bundle's
`presentation_notes`: the visual-only filter frame, pleats and cartridge are drawn 4.5 mm deeper into the housing (so the
bin mouth never appears to pass through them), the visual-only lower-seat lips are not drawn (the tabs slide through
their footprint), and the final simulated frame is held on screen for 1.5 s. Delivered film: Cycles, 24 samples,
1280 x 720, 25 fps, 1x, 474 frames (the complete 869-control episode plus the final hold).

```bash
python tools/film_export.py --traj solution/trajectory.npz --out <bundle>
DEXHAND_BLENDER=<blender-4.5.3> python tools/studio_renderer.py --export <bundle> --output film.mp4 \
    --width 1280 --height 720 --samples 24 --engine cycles --fps 25
```

## Evidence commands

```bash
cd scripts/dexhand/families/vacuum_bin_reseat
export DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand
python replay.py --task vacuum_bin_reseat --traj solution/trajectory.npz --out r1.json   # twice: same state_sha
python replay.py --task vacuum_bin_reseat --traj solution/trajectory.npz --out r.json --video r.mp4
python -m pytest -q tests
```

## Oracle (author.py)

Closed-loop controller reading privileged state, recorded as open-loop rows (Sharpa Wave; `author.py` also carries Wuji
postures, but no Wuji oracle was found: the Wuji grasp slips when the catch rides the latch ramp): index finger pokes the button (the freed
bin tips onto the counter edge), underhand power grasp around the nozzle approached from in front of the nozzle tip,
bin pose servo on the lower-tab midpoint (hand command = desired bin pose composed with the measured hand-to-bin
transform, bounded integral terms): slide the tabs off the ledges, carry the bin 8 cm away (stage 1), hover it in front
of the ledges with a 0.14 rad tilt, slide the tabs in, rotate it closed about the tabs (the catch rides the ramp and the
tooth snaps up), open the hand, drop it below the nozzle, pull it out, hold. Reproduce:

```bash
cd scripts/dexhand/families/vacuum_bin_reseat
DEXHAND_ASSET_DIR=<repo>/images/dexhand/assets/hand python author.py --out solution/trajectory.npz
```

## Wave-3 changes (2026-10-15)

| item | wave 2 | wave 3 |
|---|---|---|
| latch tooth / catch / bridge friction | 0.15 | 0.55 (source) |
| release-button travel | 7.5 mm, lower guide stop moved 1.5 mm | 6 mm (source) |
| hands | one, on a floating wrist stage (28 / 26 controls) | two, each on its own floating wrist stage (56 / 52): the left holds the vacuum by its handle |
| unsupported-fall bound | 0.6 m/s | 0.55 m/s (oracle peak 0.47 m/s) |
| VR-1 lip, visual-only filter frame and lower lips, base skid | kept | kept |
| robot | floating stage | floating stages: a Marvin-arm port was attempted (wave-3 authoring records `arm_attempt/`, outside the repository) but the arm cannot take the underhand nozzle grasp from below the counter overhang and an overhand grasp let the bin slip 40-100 mm in the hand, so the reinstall never aligned (see status.json) |

Oracle (author.py, deterministic): left hook grip on the handle (vacuum displaced <= 11 mm overall), right index presses
the button 5.9 mm (forward-down, clear of the left thumb), Euler-branch-safe transit to the underhand grasp, removal to
stage 1 at control 721, tabs-first reinstall and a closing rotation with a 10 mm-bounded push (latched, stage 2 at 950),
right hand away, left hand unhooks, success at 1,181; 150 hold rows. Zero hand-hand contacts over all substeps.
