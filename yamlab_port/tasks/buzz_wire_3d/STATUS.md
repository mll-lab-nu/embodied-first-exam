# buzz_wire_3d: status

Updated 2026-10-12 ~18:00 (agent: buzz_wire_3d task agent). FINAL hand-over state. No processes are left on vast.

## State

- **very_easy: DONE** (with the lead-approved start-yaw and tool deviations below). In Isaac (vast, CPU, 1 env,
  mode=evaluation, stop at the first terminated step):
  - oracle `oracle9`: success at step 5660 (188.7 s sim). No touch. Minimum metal-to-wire gap 8.46 mm.
    Traversal complete (route cursor 606.6 of 609.6 mm). Final: 0.17 mm from the finish, 0.0 deg, supported,
    released, quiet (4e-6 m/s, 9e-4 rad/s).
  - open-loop replays `replay1` and `replay2`: both succeed at the same step with the same state hash
    `37cb6060104217bf67604d94806a8e63f9973b7222a694e70599bd93807dd0d8`, which is also the oracle's hash.
    Replay is bit-identical.
  - nop: fails by time-out (no traversal, no touch). naive `naive_skip_traverse`: fails by wire touch, as
    intended (see "Negatives" below).
- easier: NOT DONE. It uses the same deck, wand, handle, posts, layout and start yaw (60 deg); only the rail
  differs.
  - In Isaac, pick, ring handover and the full carry work, with no touch and an 8.1 mm minimum metal-to-wire gap.
  - Blocked at the finish placement; no Isaac run succeeds yet. See "easier" below.
- Run directories on vast are `/workspace/yamlab_port/runs/buzz_wire_3d/results/<run>/`:
  - very_easy: `oracle9`, `replay1`, `replay2`, `nop`, `naive_skip_traverse`;
  - easier: `easier_oracle1`, `easier_oracle2`, `easier_oracle3`.
  - Small copies (metrics JSON, logs, action files) are in `results/<run>/` here.
  - Video (rendered by the lead): `video/very_easy/` (`wire_far.mp4` is the clear view).

Evidence on vast is in `/workspace/yamlab_port/runs/buzz_wire_3d/results/<run>/`, with small copies in
`results/<run>/` here. Video source for the lead: `results/oracle9/oracle_actions.npy`, rendered with
`tools/replay.py --enable_cameras` (see README).

## Re-layout (for PLAN.md)

- `p_world = Rz(0 deg) * p_old[mm]/1000 + (0.5144, 0.270, 0.7517)`, the same for very_easy and easier.
  - The wire span runs along world +x in the plane y = -0.035.
  - Start post at x 0.395 (near the arms), finish post at x 0.745.
  - Deck covers x 0.31-0.83, y -0.185..0.185.
- Reason: with the deck's long side facing the robot, the arms' initial open fingers penetrate the deck by
  4.7 mm unless the wire plane is at least 0.65 m away, and from there no YAM top-down pinch reaches. This
  layout keeps at least 50 mm of clearance.

## Deviations from the old task (all approved by the lead)

### 1. Tool: taller, longer wooden handle (figure `tool_old_vs_new.png`)

| | old | port |
|---|---|---|
| grip box (length x width x height) | 30.52 x 9.8 x 7 mm | 45 x 9.8 x 16 mm |
| wand mass (old densities, old mass model) | 9.68 g | 12.91 g |
| COM offset from the loop centre along the handle | 8.15 mm | 20.34 mm |
| rest pitch on the deck (old endpoint_pose formula) | 2.74 deg | 8.19 deg |

- Unchanged: the ring (R 15.4 mm, tube r 1.26 mm), the stem, the wire (r 1.47 mm), the 12.67 mm aperture,
  the traversal predicate, the thresholds and the finish/goal formula. The start and finish rest poses come
  from the old formula, so their pitch follows the new grip (8.19 deg).
- Gripper-mechanics evidence that the old handle cannot be lifted:
  - The YAM finger collision hulls in yam.usd form a V-shaped fork. The inner contact surface exists only at
    the last 14 mm of the tips (link_6 z 131-145 mm, |y| <= 9 mm) and along two diagonal bars, with a hole
    in between (`tools/finger_surface.py`).
  - So a horizontal pen grip cannot pinch a handle lying on the deck. Isaac run `oracle4`: the gripper
    closed around the handle with zero finger-wand force, and the wand did not move.
  - The only start grasps the arm can reach are tip pinches tilted 15-30 deg about the closing axis
    (`optA_lift_check.py`, `optA_map.py`). With that tilt the tip edge dips 2-4.5 mm, so the tips must stay
    3-5 mm above the deck. The patch then covers at most the top 2-4 mm of a 7 mm handle.
  - Pick-and-lift tests with the old handle (`lt1`-`lt4`, `oracle5`, `oracle6`; grip friction up to 2.0):
    the wand was never lifted (z unchanged at 0.8962). At best it was turned 9.7 deg and shifted 4 mm.
- With the 16 mm handle, the pick-and-lift tests (`tl20` and `tl30`, tilt 20 and 30 deg) both lift the wand
  by 54.8 mm. In-hand error: 0.71 mm / 0.45 deg at 20 deg tilt, and 3.38 mm / 0.82 deg at 30 deg. The oracle
  uses 20 deg.
- The handle is sized as small as the tip patch allows: 16 mm tall so the patch overlaps it with the tips
  clear of the deck, and 45 mm long so the patch (18 mm along the handle) fits with margin at the grasp
  offsets the planner needs.

### 2. Start pose: wand start yaw about the start post, 11.3 -> 60 deg (figure `start_old_vs_new.png`)

- In the old start pose no tilted tip pinch reaches the handle without the arm hitting the start post or the
  wire. The feasible island on the start post is handle yaw 30-60 deg (`optA_map.py`).
- Only the yaw about the start post changes. The loop still encloses the wire at arc 0, and the traversal
  starts within 10 mm of arc 0, as the predicate requires. Finish and goal are unchanged.

### 3. Ring grip for the carry (lead flag)

- The planner found no handle grip that carries the wand along the whole span: the arm hooks the wire or the
  other arm. So the right arm carries the wand by its metal ring tube, clamping it on the far side of the loop.
- This is legal under the old predicate: only wand metal against the wire counts as a touch, and the old
  task never restricted the grip.
- Robot-to-wire minimum distances per phase in oracle9 (mm; fingers / any link of that arm):

  | phase | left | right |
  |---|---|---|
  | 1 left pick (start) | 36.0 / 8.5 | 198.6 / 198.6 |
  | 2 left lift + tilt | 40.1 / 9.3 | - |
  | 3 ring handover | 38.0 / 21.3 | 11.6 / 11.6 |
  | 3b left release | 28.6 / 24.1 | 10.5 / 10.5 |
  | 4 right carry (ring grip) | 269.4 | **10.4 / 10.4** |
  | 5 left pen-grip handover at the finish | 37.1 / 37.1 | 10.5 / 10.5 |
  | 5b right release | 35.0 / 35.0 | 13.9 / 13.9 |
  | 6 left yaw + lower | 33.8 / 5.1 | - |
  | 6b left release (drop) | 40.1 / 6.2 | - |

  Any-link minima of 5-9 mm in phases 1, 2 and 6 come from the wrist links near the start and finish posts,
  not from the fingers. No robot link touches the wire in any phase.

### 4. Physics knobs (task-file only)

- Wand-metal friction is 1.0 (it was 0.3). Wand-grip friction stays 0.8 and deck friction 0.5.
- Wand solver velocity iterations are 4 (the env override `BUZZ_WAND_VEL_ITERS` defaults to "4").
- Reason: with the heavier handle the ring grip slipped 25 deg in the entry elbow (`oracle7`; contact jitter
  showed an apparent angular velocity of about 9 rad/s). Runs `jd1`, `jv4`, `jv8` and `jv16` compared the
  settings. These parameters touch only the wand-finger contact, not the wand-wire touch rule.

### 5. Finish release from a height

- The final pen grip must stay at least 34 mm above the deck (the finger bars reach 25-33 mm below the
  handle axis) and at most 38 mm (beyond that the wrist camera meets the span). So the oracle releases the
  wand from 32-40 mm and lets it drop onto the finish support. In oracle9 it released from 32 mm, and the
  wand settled 0.17 mm from the finish.

## Oracle sequence (`tools/stages_a.py`)

1. Left arm: tilted (20 deg) top-down tip pinch on the handle at the start post. Lift and tilt to the
   handover pose. The lift is re-planned with the measured in-hand pose.
2. Right arm: ring grip (handover 1). Handover pose candidates are searched around (30, -30, 55 mm); oracle9
   used (30, -25, 55 mm). Then the left arm releases.
3. Right arm carries the wand along the whole rail. Worst clearances: arm to wire 10.2 mm, deck 4.5 mm,
   stops 39.2 mm.
4. Left arm: pen grip on the handle at the finish post (handover 2). Then the right arm releases.
5. Left arm descends, yaws to the finish yaw low, and releases from 32 mm. The wand settles on the finish
   support.

## easier: state, what was tried, next idea

The easier span bends toward +y (the left arm), reaching y = 0 at x 0.47-0.58, and dips to z 1.019 near x 0.6.
Pick, ring handover and carry are unchanged from very_easy and work in Isaac: in `easier_oracle1` and
`easier_oracle2` the traversal reaches the finish post with no touch (gap at least 8.1 mm), and the worst
arm-to-wire clearance in the carry is 4.4 mm. Only the finish placement fails.

1. The very_easy finish (left pen grip on the handle, turned under the span to the finish yaw, released from
   32-40 mm) fails in the offline planner. The left forearm (link_4) meets the bend and the wrist camera meets
   the dip; see `tools/diag_wire_hits.py` and `results/dry_easier_60.log`.
2. Variants of that grip, all failing in the offline planner:
   - grip rolled 20-90 deg about the handle (`results/dry_easier_roll*.log`), plus approach yaws of 15-45 deg
     (`results/gd_grid/`);
   - release heights up to 60 mm (`results/gd_hi/`);
   - scene shifted by 20-60 mm (`results/lay_grid/`);
   - top-down clamp on the ring tube: the arm cannot reach it;
   - the whole sequence mirrored, so the right arm places: the camera meets the dip
     (`results/mir/`, `mir2/`, `mir3/`; `BUZZ_MIRROR=1`).
3. "Relay" finish (`BUZZ_FINISH=relay`, `stages_a.finish_relay`): it plans and runs in Isaac to the release
   but fails at the drop.
   - Sequence: the left pen grip turns the handle to 140 deg; then the right arm takes a side pinch (closing
     vertical, across the 16 mm handle height) and turns the handle to the finish yaw. Feasibility map in
     `results/fgm/`.
   - The side pinch's lower finger bars need a loop height of at least 54 mm, so release is from 56-62 mm.
   - On opening, the wand rests on the lower pad. The COM is 20 mm from the loop centre, but the pad starts
     at 31 mm, so the wand pivots loop-down off the pad.
   - `easier_oracle1` (pads opened 3 mm): the tilted handle wedges in the jaws and the retreat drags the loop
     into the finish post (touch at step 6539).
   - `easier_oracle2` (pads opened 7.5 mm, wait 40 steps): traversal COMPLETE (cursor 637.8 mm). Then the wand
     pivots to 40 deg pitch and the loop touches the post at step 6546 (rail force 0.11 N).
4. Tuned left pen grip (current default for easier; `GD_TIER`, `GD_TILT_TIER`, `HZ_FINISH_TIER` in
   `stages_a.py`).
   - The grip: tips on the outer handle end (62 mm), rolled 10 deg, tilted -8 deg.
   - `tools/finish_grip_map.py` (`results/fgm2/`) shows it clears the span at the finish yaw from 40 mm,
     with 6.5 mm to the wire and 9 mm at 150-160 deg. This keeps the clean vertical-jaw drop of very_easy.
   - The offline plan is OK with handover 2 at 90 mm (`results/dry_easier_gd_r10_z0.090.log`).
   - In Isaac (`easier_oracle3`) the measured carry-end pose differs slightly. The grasp at the 90 mm handover
     is rejected (fingers 1.6 mm into the deck at the start of the follow path), and the run stops with a
     plan error at step 3176. There is no touch.

Best next idea: keep idea 4 (it keeps the clean drop) and make the handover robust.
- Re-plan the left grasp at the measured pose with a small search: handover height 0.09-0.12 m; roll 5-15 deg;
  tilt -12..-4 deg.
- Or descend first with the carrier's ring grip to about 60 mm before handover. The ring grip is fine there.
- Then run the usual pipeline: oracle, 2 replays, nop, naive.
- Fallback: on top of idea 3, have the left arm (still holding) support the loop side while the right side
  pinch opens.

## Reproduce (vast; see README for install)

```bash
. /workspace/yamlab_port/env.sh; R=/workspace/yamlab_port/runs/buzz_wire_3d
export PYTHONPATH=$R/yamlab BUZZ_NO_CAMERAS=1
python $R/src/tools/oracle_r.py --headless --tier very_easy --mode oracle --out OUT                    # oracle9
python $R/src/tools/replay.py --headless --tier very_easy --actions OUT/oracle_actions.npy --out OUT2  # replay1/2
python $R/src/tools/oracle_r.py --headless --tier very_easy --mode nop --nop_steps 9100 --out OUT3     # nop
python $R/src/tools/oracle_r.py --headless --tier very_easy --mode naive_skip_traverse --out OUT4      # naive
python $R/src/tools/dry_run_a.py 60 easier                                                              # offline plan
```

All runs on vast used `OMP_NUM_THREADS=4 nice -n 19`, CPU, 1 env, mode=evaluation.

## Negatives (from the new start, evaluation mode)

- nop `nop` (hold the start pose): fails by time-out at step 9001 (300 s). It never touches the wire (gap
  13.3 mm) and makes no traversal progress (route cursor 0). The wand stays 350 mm and 108.7 deg from the
  finish.
- naive `naive_skip_traverse`: the same pick and ring handover, then a straight-line carry from the start
  post to the finish post instead of following the wire. It fails by wire touch at step 2625, about 25 steps
  into the straight move. The metal-to-wire gap reaches 0 and the rail contact force is 1.47 N, with the
  route cursor at 45.5 mm. This is the intended reason: the shortcut drives the loop through the wire.
  - The naive carry skips the planner's arm-to-wire and arm-to-deck checks; with those checks the planner
    refused the shortcut (`naive_planfail_1`).
- Logging note: Isaac Lab auto-resets on termination. So the last logged wand pose of a terminated run is the
  post-reset pose, while the last diagnostics row (gap, force) is from the terminating step.

## Built (reusable)

- USD assets (`assets/<tier>/{wand,rail,stops,deck}.usda`, `geometry.json`) from `tools/make_assets.py`.
  The collision model is the old one 1:1 except the grip box:
  - ring = 64 capsules (r 1.26 mm) on R 15.4 mm, plus a stem capsule;
  - rail = capsules (r 1.47 mm) between the 219 centreline points;
  - 8 x 8 x 12 mm end blocks;
  - deck = top plate + rim + 4 feet boxes from `wire_base.stl`.
- YAMLab task (`yamlab_task/`):
  - `configs/tasks/buzz_wire_3d.yaml` and `envs/tasks/buzz_wire_3d_manager{,_cfg}.py`;
  - registration in `envs/tasks/__init__.py` and `envs/robot_registry.py`;
  - gym ids `BuzzWire3D-VeryEasy-v0` and `BuzzWire3D-Easier-v0`;
  - evaluation mode = CPU, 1 env, 300 s; terminations time_out / task_success / wire_touched /
    wand_below_table.
- Goal check = the old `terminal_v4_traversal_then_deck_release`, with thresholds unchanged:
  - touch: the wand ContactSensor force against the rail, and a geometric ring/stem-to-wire gap, checked
    every physics substep and latched;
  - traversal: aperture crossings tracked every physics substep (start within 10 mm of arc 0, progress
    tolerance 3 mm, completion kept);
  - finish: within 5 mm / 10 deg (half-turn symmetry), supported by the deck, released (no robot contact),
    and quiet (1 mm/s, 0.02 rad/s) for 30 control steps (1.0 s).
- Tools:
  - numpy YAM kinematics from yam.usd (`yam_kin.py`; 0.00 mm / 1e-4 deg vs Isaac) and batched DLS IK
    (`ik.py`);
  - dense hull-surface collision samples, workstation colliders and the other arm (`grasps.py`,
    `plan_r.py`), RRT-Connect, branch-aware grasp planning;
  - Isaac runner, logging and metrics (`bw_runner.py`);
  - the oracle (`oracle_r.py` with `stages_a.py`), replay with `--enable_cameras` (`replay.py`), and offline
    dry runs (`dry_run_a.py`).

## Measurements

- Scene smoke test (vast, CPU, no cameras): the scene loads and the wand settles (0.05 mm drift, deck force =
  weight). Speed is about 65 control steps/s for the bare scene, and about 8.7 steps/s for the oracle
  including planning (654 s wall for 5661 steps).
