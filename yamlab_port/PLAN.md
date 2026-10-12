# Port plan: old RoboTangle tasks -> YAMLab

Date 2026-10-12. Read `YAMLAB_NOTES.md` first. Old sources: STL package `../tmp/2026-10-11_robotangle_v1_stl/`, old task code `ref/topogym_2dafa5f/topogym/{tasks,assets/geometry,planning}/<family>/`.

## Ground rules for every family

- **Robot untouched.** `configs/robot/yam.yaml`, `robot/yam/*`, the YAM USD, gains, gripper, cameras, base poses, action layout, 30 Hz control: unchanged. Only task files are added (`configs/tasks/<task>.yaml`, `envs/tasks/<task>_manager(_cfg).py`, assets, registration lines in `envs/tasks/__init__.py` and `envs/robot_registry.py`). Task-level knobs that YAMLab itself exposes per task (object friction, sim device per mode, episode length, `grasp_detect`) are fair game; physics dt stays 1/120 unless a task genuinely needs finer steps (then say so).
- **Geometry 1:1, layout re-placed.** Parts keep their old millimetre geometry. The old layouts were built around ALOHA (arms facing each other) or a single Panda; YAMLab has two YAM arms side by side facing +X on a 70 x 110 cm table (top z 0.7517 m). Each family re-places its fixtures in the YAM workspace (translation + yaw of the whole scene, keeping the parts' relative poses), chosen by measured reachability. If a scene does not fit (fiber_bundling spans 77 cm), rotate it; shorten only passive slack (cable lead) and document it.
- **No grasp welds.** The old release had a `contact_weld_v1` grasp assist for the wand and the cable trunk. YAMLab has none and the robot must not change, so grasps are friction grasps with YAMLab's own grasp clamp (`enable_gripper_grasp_clamp`). If a grasp cannot hold, report it as a finding; do not add a weld silently.
- **Goal check = the old success predicate**, re-implemented on YAMLab state (rigid-body/link poses, velocities, contact sensors), with the same thresholds unless a threshold depends on the old physics (then document the change). Implemented as the task's success term (latched, N consecutive steps where the old one had `stable_duration_s`).
- **Oracle** = a scripted, privileged-state controller: Cartesian waypoints for the gripper -> differential IK on the YAM arm Jacobian (Isaac Lab `DifferentialIKController` or `utils/jparse_ik.py`) -> 14-D joint targets at 30 Hz. Deterministic from a fixed seed; it records its action sequence so the run can be replayed open-loop from the same reset (report whether the open-loop replay also succeeds, and whether two runs are bit-identical; CPU physics is the deterministic candidate).
- **Negative checks:** a nop run (hold the start joint targets) must fail; a naive run (e.g. the oracle with one essential step removed, or a straight-line shortcut) must fail for the intended reason.
- **Evidence:** a short headless video or frame strip (`--enable_cameras`, top + one wrist camera) of the oracle run; JSON metrics per run.

## Re-layout log (YAM arms side by side facing +X)

Every family re-lays its fixtures for the YAM workspace and keeps the task's topology and difficulty: the same parts, clearances, wire/rope/cable geometry, crossing order and threading order. Each re-layout is recorded here (the transform old table frame -> YAMLab world, and why):

| family | tier | transform (old table mm -> YAM world m) | notes |
|---|---|---|---|
| buzz_wire_3d | very_easy (stopped) | `p_world = p_old/1000 + (0.5144, 0.270, 0.7517)`, no rotation (supersedes the provisional Rz(-90) layout) | wire span along +x in the plane y -0.035, start post x 0.395, finish post x 0.745; the earlier long-side layout made the arms' open fingers hit the deck unless the wire was >= 0.65 m away, out of top-down reach. Approved start deviation A: wand start yaw about the start post 11.3 -> 60 deg (`tasks/buzz_wire_3d/start_old_vs_new.png`); goal unchanged | wire plane x 0.665, start post left (y +0.175), finish post right (y -0.175); deck front edge x 0.516 clears the arms' initial open fingers. The tool must be regrasped mid-task (face-up at start, face-down at finish; only a sideways pen grasp fits under the 157 mm span): right arm picks, left arm finishes. Approved by the coordinator (matches the old family's grip changes). |
| knot_untying | very_easy, easier (final) | `xy_w = R(-90 deg) xy_old/1000 + (0.659, 0.1357)`, `z_w = 0.7517 + z_old/1000` | tails toward the robots, loop away, rope centred between the arms (crossing at (0.532, 0.0)); measured reach x 0.32..0.72 per arm, across the midline to abs(y) ~0.18 |
| fiber_bundling | very_easy, easier (final) | `p_world = Rz(+90 deg) p_old/1000 + (0.25, -0.01, 0.7517)` | old scene spans 916 mm along the cable (> 70 cm table depth): cable now runs along +y, terminal box in front of the right arm, ring at (0.500, 0.376, 0.992) in front of the left arm; no part moved relative to another, the full 830 mm lead kept; axis height unchanged |
| cast_keyhole | very_easy (final) | `p_world = p_old/1000 + (0.52, -0.10, 0.7500)`, no rotation (0.7500 = actual table collider top) | gold's free band faces the left arm, silver's free edge the right arm; goal square X 0.392..0.648, Y 0.015..0.271; yaw 90/180 rejected for reach |
| rope_threading | easy (final) | `xy_w = Rz(+90 deg) xy_old/1000 + (0.58, 0.0)`, `z_w = 0.7500 + z_old/1000` | rings toward the arms (R2 plane x 0.46, R1 x 0.60), rope U bulging away; all four threading strokes reachable (numpy IK); ALOHA risers dropped (old robot) |

## Families

### buzz_wire_3d — feasibility HIGH (all rigid). Start: very_easy, then easier, easy.

- Scene: wooden deck (`wire_base`), two wire end blocks, bent wire rail (2.94 mm, centreline CSV), the wand (loop inner radius 14.14 mm, 2.52 mm tube, stem, wooden handle 78.5 x 33.3 x 7 mm overall). Radial clearance loop vs wire 12.67 mm: generous.
- Isaac build: deck and blocks static boxes/meshes; rail = one static body made of capsules along the centreline (exact radius, no mesh tunnelling); wand = one dynamic rigid body with a compound collider (loop as a ring of ~32 capsules, stem capsule, handle box). Wire and loop contact via a `ContactSensor` on the wand filtered to the rail, plus a geometric loop-to-rail distance check every physics step as backup.
- Goal (old `terminal_v4_traversal_then_deck_release`): never touch the wire (any wand-metal / wire contact fails, latched); the loop's aperture crossing must be tracked continuously from the start (within 10 mm of arc 0) to the end of the rail (route progress tolerance 3 mm); finally the wand rests on the finish support within 5 mm and 10 deg (half-turn symmetry about the handle axis allowed), supported, released (no robot contact), quiet (<= 1 mm/s, <= 0.02 rad/s) for 1.0 s.
- Oracle: grasp the handle with the right (or better-placed) arm; drive the loop centre along the rail centreline with the loop normal along the rail tangent (handle pose follows); slow on elbows; then place on the finish support and release; retreat. very_easy is a planar wire (y const, 350 mm span, 153-300 mm above the deck).
- Risks: in-hand slip/rotation of a 7 mm-thick handle under a 95 mm parallel gripper (check finger friction, clamp); YAM reach/orientation limits along a 350 mm path at 15-30 cm height; wrist singularities.

### knot_untying — feasibility MEDIUM for very_easy/easier (overlap loops), LOW for medium/hard (true overhand knots). Start: very_easy.

- Old model: FEM IPC rope, 8 mm, 0.99-1.36 m, very soft (E 50 kPa), mu 0.3. YAMLab/Isaac Lab has no rope; PhysX FEM soft bodies are GPU-only and fragile for an 8 mm x 1 m rope. Port as a **capsule chain**: ~100 capsules (r 4 mm, ~10 mm long) joined by spherical/D6 joints with small bend stiffness and damping; preferably one articulation (reduced coordinates, stable; check PhysX's link count limit) with self-collision on (adjacent links filtered), else maximal-coordinate bodies + D6 joints. Mass from rho 650 kg/m3.
- Start: link poses from the old start centreline (re-placed on the YAM table), then a short settle; verify the crossing over/under order matches `knot` in `start_state.md` (very_easy: 1 crossing, open single overlap loop; easier: 2 crossings, alternating; easy: two overlap loop; medium: open overhand 3 crossings).
- Goal (old `evaluate_state`): `planar_clearance` of the centreline (top-view projection, non-local segment pairs separated by >= the rope diameter 8 mm, local pairs within 2 diameters of arc excused), whole rope on the table (z between table - 1 mm and table + 2r + 3 mm), quiet (max point speed <= 1 mm/s), rope intact (no joint separation), for 0.5 s.
- Oracle: privileged crossing analysis on link positions -> pick the over-strand nearer a free end, grasp it, lift 3-5 cm, carry the end across so the crossing disappears, lay it down straight, release, settle; repeat per crossing; final spread so all non-local gaps >= 8 mm.
- Risks: chain stability under a high-PD parallel gripper pinching an 8 mm capsule (ejection; use clamp, friction); a floppy chain may need more solver iterations than YAMLab's 16; the knotted start must settle without links passing through each other; medium/hard need over/under manipulation that a chain may not hold.

### fiber_bundling — feasibility MEDIUM for very_easy (2 strands), lower for more strands. Start: very_easy.

- Old model: an articulated rigid cable with gravity compensation 1.0 (weightless), fixed root at the terminal box gland; slack lead 830 mm, trunk 240 mm (6 x 40 mm, r 12 mm), N strands of 80 mm (10 x 8 mm, r 1.2 mm); fixed copper ring (torus, 64 capsule segments, tube r 4 mm, inner r 13.5 mm: aperture 13.48 mm vs jacket 12 mm, 1.48 mm radial clearance); U cradle; ring mount. In the start layout the trunk lies in the cradle already aimed at the ring (same y and z).
- Isaac build: the cable as one fixed-base articulation (same segment counts, gravity disabled on cable links to match the old model), ring as static capsules, cradle/box/mount static. Contact offsets on ring and jacket must be small (<= 0.5 mm) or the 1.48 mm clearance closes.
- Goal (old `terminal_v4_fiber_ring_plane`): every strand passes through the ring plane inside the aperture, in material order (tip first), and its passed stations clear the tube on the exit side; the front sheath face has passed and is clear by the tube radius; max bend between consecutive strand segments <= 60 deg; any gripper contact with a strand fails (latched).
- Oracle: grasp the trunk near its back (old grasp target trunk_04), align the trunk axis with the ring axis, push straight through by (ring x - strand tip x + strand length + margin), release; never touch strands.
- Risks: tight clearance + PhysX contact offsets -> jamming or tunnelling; scene spans 77 cm along x (> 70 cm table depth): rotate the scene so the cable runs along y, or shorten the passive lead; friction grasp of a 24 mm jacket pushing through a tight ring.

### cast_keyhole — feasibility MEDIUM-HIGH (rigid backup). Start: very_easy. Agent added later.

- Two 9 mm keyhole plates interlocked through each other's slots; remove the silver one and place it in the goal square. Needs convex decomposition that keeps the slot clearances (4.8 mm min gap at very_easy). Oracle: hold gold with one arm, slide silver out along the slot path with the other, place in the goal square.

### rope_threading — feasibility MEDIUM-LOW. Start: easy (lowest released tier). Agent added later.

- Stiffer rope (E 5 MPa, 8 mm, 1.1 m) through 2 rings (138 mm aperture) on stands 230-330 mm high, in order and direction. Same capsule-chain rope as knot_untying (stiffer joints). Long-horizon bimanual relay; depends on knot_untying's rope model working.

## Order and compute

1. Three agents in parallel now: buzz_wire_3d, knot_untying, fiber_bundling (very_easy each).
2. cast_keyhole when one of the first three is on track (or at once if one proves infeasible); rope_threading after the knot rope model is validated.
3. Compute: vast (`/workspace/yamlab_port/`, shared venv, nice 19). Budget: at most 2 concurrent Isaac processes per agent (6 total, cap 8 for the whole port). ws/ws2/ws3 only if vast is unavailable, after checking load. Quest: CPU nodes for offline geometry; gengpu A100/H100 (no RT cores) for physics-only runs, and a render attempt only if ws/ws3 fail.

## Closed: cast_keyhole easier (2026-10-12)

Decision (user, via the coordinator): cast_keyhole ships with very_easy only, with no rest fixture. easier is closed as **not feasible for the YAM with the original puzzle**: the easier channel's silver legs sweep the whole gold edge band, and every remaining gold grasp is too short for the YAM's 60 mm blades, unreachable, or needs ~20 N against the YAM's 9-14 N grip (evidence below). Evidence: `tasks/cast_keyhole/STATUS.md` ("easier work log and blocker evidence"), `tasks/cast_keyhole/runs_meta/{swept_easier_+1.png,ea_t14.png,ea_t15.png}`, `tools/plan_search2.py`.

- **What is built for easier:** task `CastKeyhole-Easier-v0`, assets (gold 52 exact slab prisms, 0.6085 kg; silver unchanged), geometry matching the STLs to 1e-5 mm, start gap 4.807 mm, route clearance 1.125 mm; nop fails.
- **Why the very_easy plan does not transfer:** the easier channel shifts the silver bar 10.7 mm sideways while it travels gold y -9..-60 mm, so the silver legs reach gold x 38.7 mm and sweep the whole +x edge band that very_easy's gold grasp used. The only regions the silver never touches are (a) the band beside the fork end, gold y -105..-65 mm (40 mm, shorter than the 60 mm finger blades), and (b) the cap top. The 21-25 mm thick blades cannot fit under the legs.
- **Tried: 16 Isaac trials (ea_t1..t15) and 6 IK searches, all friction grasps on the unchanged YAM:**
  1. Fork-end grasp from the open end: no IK solution for either arm, in the very_easy orientation or with the scene yawed -90 deg.
  2. Fork-end band grasp from the start: reachable by the left arm only with the scene moved out (X0 >= ~0.56), which puts the silver at the right arm's reach limit. Held 95 mm from its centre of mass, the gold pivots in the grip during the stand (14 mm, 8 deg); with a compliant left hand it sags 20 mm onto the silver. The silver then slips ~25 mm in its grip on the way to the work pose (1-5 cm right-arm IK error). Same failure across several work poses, a -20 deg yawed scene, slower motion and other silver grasp points.
  3. Regrasp after the stand and at the work pose: released, the gold drops until its fork end rests on the table with the band only 5-10 mm up, but a side clamp needs ~25 mm (the blade reaches 25 mm below the grip line); the fingers close on nothing.
  4. Cap-top grasp (analysed, not run): the centre of mass is 70-100 mm beyond the only other support (the silver bar), so holding the gold level needs ~20 N of grip, against the YAM's 9-14 N.
- **Smallest changes that would likely work (all outside the current rules):**
  1. A fixed rest under the gold's fork end (a scene fixture). Declined by the user (it alters the original puzzle).
  2. A stronger or longer-padded gripper (robot change: not allowed).
  3. The old weld grasp assist (not allowed).

## buzz_wire_3d very_easy: stopped, then resumed with a taller handle (2026-10-12)

Also accepted by the user: wand metal friction 0.3 -> 1.0 and wand solver velocity iterations 1 -> 4 (object-side knobs; the ring grip had slipped 25 deg under the heavier handle).

Decision (coordinator, per the user's rule "robot unchanged, only the task changes"; the wand is part of the task): use a taller and longer wooden handle (~15 mm tall, >= 40 mm long, sized to the YAM tips' contact patch), for very_easy and easier. The wire, loop, clearances, traversal and goal stay exactly as old, so the difficulty is kept. Re-run end to end (pick test, oracle, replays, negatives, video); if it still cannot lift, record C.

Evidence for the stop:

Evidence: `tasks/buzz_wire_3d/STATUS.md` ("Why very_easy stops here"); runs on vast `/workspace/yamlab_port/runs/buzz_wire_3d/results/`.

- **Done:** task, assets (old collision model 1:1), goal check (old terminal_v4, every physics substep), re-layout, and a kinematically complete oracle plan (dry run PLAN_OK for the whole sequence: start pinch, ring-grip handover, full-rail carry with worst clearances 10.2 mm to the wire and 4.4 mm to the deck, finish handover, release).
- **Blocker (gripper mechanics, not planning):** the YAM finger collision hulls give contact only on the last 14 mm of the tips (+-9 mm wide; a V-shaped fork). The 7 mm wand handle lying on the deck can only be pinched by tips tilted 15-30 deg, which must stay 3-5 mm above the deck, so the patch covers at most the top 2-4 mm of the handle. Isaac pick-and-lift tests (lt1-lt4, oracle5, oracle6, grip friction up to 2.0): never lifted (zero or transient 2-5 N contact). The finish has the mirror problem (release drop of 34-38 mm).
- **Options (none is task-file-only):**
  - C: accept very_easy as infeasible for the unchanged YAM (agent's recommendation).
  - A thicker/longer wooden handle (e.g. >= 15 mm tall, >= 40 mm long): changes the tool geometry, not the wire or the difficulty of the traversal; the existing pipeline can then be re-run end to end.
  - A deck-level start/finish support raising the handle end ~10 mm: changes the fixtures.
  - A different gripper/pads or a grasp weld: not allowed.

## rope_threading medium (not attempted, 2026-10-12)

With the easy layout, R3 lands at world (0.205, 0.09), on the robots' base block behind the tabletop edge (x 0.3025). Medium needs its own re-layout and reach study; its assets are not built yet.
