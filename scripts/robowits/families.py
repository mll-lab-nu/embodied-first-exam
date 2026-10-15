"""RoboWits family table: everything per family that scripts/robowits/mk_tasks.py needs to render its two tasks
(privileged robowits-<family>-i00 and standard robowits-<family>-i00-standard). One RoboWits seed task = one family; the
instance is entry `eval_index` of RoboWits' eval_dataset_50/<NN>.json, frozen with `rcb_robowits.py make-instance`.

status
  "pr"       generated and committed (a full oracle, or a graded positive that the human review can check, PROTOCOL §2.7)
Every family here has tasks. Eleven further families without a valid positive are not in the repository
(docs/benchmarks/robowits.md, Families); one comes back as a new entry here once it has a positive and a written
`criterion` (`mk_tasks.py --instance <its instance.json> <family>`).
DROPPED lists the families that are not coming back, with the reason.

change_log (optional): {"priv": [...], "std": [...]}, README Change Log entries of this family alone, after those of every
family (mk_tasks.CHANGE_LOG).

host_cpu_vendor (optional): the family's frozen instance is rebuilt within tolerance only on CPUs of this vendor (the
`vendor_id` of /proc/cpuinfo; docs/benchmarks/robowits.md, Hosts). mk_tasks.py writes it to `[metadata].host_cpu_vendor`
of both tasks and to their READMEs, for a scheduler to read; on another vendor's host the trial ends as infra_error = 1.

criterion (required to render a family): the instruction's "Success criterion (as graded)" section, written from the
predicate (scripts/robowits/predicates/<NN>_<family>.py = RoboWits' `_check_success`, verbatim; `predicate_sha` pins the
text to it: mk_tasks.py refuses to render when the predicate changed). "priv" may give world coordinates (privileged
mode gives poses); "std" never says where things are (docs/benchmarks/robowits.md, D7). "unchecked" and "text_vs_code"
are a string or {"priv": ..., "std": ...}. Terms used: footprint, not held, table bounds (defined in mk_tasks.py).

Measured scene builds (`build_s`, standard-mode episode start minus the end of Harbor's environment setup, laptop
2.0 / 2.2 rounds) set RCB_STARTUP_TIMEOUT_S = max(900, 2 x the slowest build across hosts) (STANDARD_MODE.md §13.3);
the RoboWits CPU-backend builds measured 47-234 s across 94 trials on every host, so 900 s holds for every "pr" family."""

TABLE = "the table bounds"   # a term of the criterion texts, defined once per instruction (mk_tasks.CRITERION_TERMS)

FAMILIES = {
    # ------------------------------------------------------------------ in this PR (15)
    "align_blocks": dict(
        status="pr", rid="01-align-blocks", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["first target cube", "second target cube", "third target cube", "long rigid ruler"],
        std_objects="Objects here: first target cube, second target cube, third target cube, long rigid ruler.",
        difficulty="Align 3 cubes in a straight line using a ruler. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-align-blocks-i00-limite__bbbgbmS (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[48.6, 54.3], predicate_sha="702886c2c9052410",
        criterion=dict(
            priv=["Every object in the scene except the table and the robot (the ruler included) has its position inside x 0.18-1.03 m, |y| <= 0.72 m (the table bounds grown by 3 cm).",
                  "Each of the three cubes rests on the table: the bottom of its bounding box within 2.5 cm of the table top (z = 0.76 m).",
                  "Seen from above (x, y), the two cube centres farthest apart are at least 3 cm apart, and the third cube's centre lies within 1.0 cm of the straight line through those two."],
            std=["Every object in the scene (the ruler included) has its centre over the table, within the table bounds grown by 3 cm.",
                 "Each of the three cubes rests on the table: the bottom of its bounding box within 2.5 cm of the table top.",
                 "Seen from above, the two cube centres farthest apart are at least 3 cm apart, and the third cube's centre lies within 1.0 cm of the straight line through those two."],
            unchecked="the cubes' orientation, whether they touch, their speed, whether a gripper still holds one, and how the ruler is used",
            text_vs_code="\"Perfectly in a straight line\" means within 1.0 cm of the line through the two outermost cubes, seen from above. The grader also requires what the text does not say: the cubes resting on the table, at least 3 cm between the outermost two, and every object over the table."),
    ),
    "ball_into_bottle": dict(
        status="pr", rid="12-ball-into-bottle", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["red bottle", "funnel", "ball container", "small ball"],
        std_objects="Objects here: red bottle, funnel, ball container, small ball.",
        difficulty="Transfer a ball from a container into a bottle using a funnel. The funnel provides a wide capture entrance. Gravity guides the ball through the spout into the bottle. The ball container is graspable and can be poured into the funnel opening. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-ball-into-bottle-i00__aUXXC4E (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[55.2, 56.4], predicate_sha="ddb48a99659957e7",
        criterion=dict(
            priv=["The ball's centre (x, y) lies inside the red bottle's footprint.",
                  "The ball is deep in the bottle: its top (centre z + r, r = half the smallest extent of its bounding box: 5 mm for this 1 cm ball) is more than 11 cm below the top of the bottle's bounding box. In this scene the bottle's box spans z 0.767-0.994 m, so the ball's top must be below z = 0.884 m.",
                  "The ball's bottom (centre z - r) is more than 2 mm above the table top (z = 0.762 m) and more than 2 mm above the bottom of the bottle's bounding box (z = 0.769 m here).",
                  "Neither the ball nor the bottle has fallen: the bottom of each bounding box is no lower than 5 cm below the table top (z >= 0.71 m)."],
            std=["The ball's centre, seen from above, lies inside the red bottle's footprint.",
                 "The ball is deep in the bottle: its top is more than 11 cm below the top of the bottle's bounding box (the bottle is about 23 cm tall and the ball 1 cm across).",
                 "The ball's bottom is more than 2 mm above the table top and more than 2 mm above the bottom of the bottle's bounding box.",
                 "Neither the ball nor the bottle has fallen more than 5 cm below the table top."],
            unchecked="how the ball got there (the blue container and the funnel are not referenced), whether a gripper holds anything, and any speed",
            text_vs_code="\"Into the red bottle\" means deep inside it: seen from above inside the bottle's outline, with the ball's top more than 11 cm below the bottle's top and the ball off the bottle's base. \"From the blue container\" is not checked."),
        priv_note="The red bottle's base is thin in the simulator (its collision shape is about 3.5 mm thick, and the bottle is fixed to the table): a ball that falls fast down the bottle can pass through the base onto the table, which fails the task. In one measured case about half of the pours did (16 replays of one pouring trajectory with tiny noise, 9 balls through the base): let the ball in slowly.",
        std_note="The red bottle's base is thin in the simulator (its collision shape is about 3.5 mm thick, and the bottle is fixed to the table): a ball that falls fast down the bottle can pass through the base onto the table, which fails the task. In one measured case about half of the pours did (16 replays of one pouring trajectory with tiny noise, 9 balls through the base): let the ball in slowly.",
        change_log={"priv": ["2026-10-14 (board 0113, from board 0086): the instruction says that the bottle's base is thin in the simulator and a fast-falling ball can pass through it (board 0086: a privileged trial measured 9 of 16 slightly perturbed replays of one pour losing the ball through the base; every standard run failed). Text only: the scene, the frozen instance, the tooling, the predicate and the verifier are unchanged, so the task keeps its name. A thicker base would change the frozen scene (not done)."], "std": ["2026-10-14 (board 0113, from board 0086): the instruction says that the bottle's base is thin in the simulator and a fast-falling ball can pass through it (board 0086: a privileged trial measured 9 of 16 slightly perturbed replays of one pour losing the ball through the base; every standard run failed). Text only: the scene, the frozen instance, the tooling, the predicate and the verifier are unchanged, so the task keeps its name. A thicker base would change the frozen scene (not done)."]},
    ),
    "ball_onto_tower": dict(
        status="pr", rid="17-ball-onto-tower", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["tower base", "large ring", "medium ring", "small ring", "ball"],
        std_objects="Objects here: tower base, large ring, medium ring, small ring, ball.",
        difficulty="Place the ball stably on top of the tower. The tower pole alone cannot support the ball as it would roll off. The base can only fit 2.5 rings inside its height, so stacking all three rings causes the top ring to protrude above the pole, creating a hollow cup-like surface where the ball can rest stably in the center. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-ball-onto-tower-i00-lim__LQbxymJ (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[49.7, 52.9], predicate_sha="3e17d49703c62e1e",
        criterion=dict(
            priv=["The footprints of the tower base and of the ball lie inside the table bounds (1 mm tolerance).",
                  "The ball is still: its speed is below 0.05 m/s and its vertical speed below 0.03 m/s.",
                  "The ball's centre is more than 5 mm above the top of the tower base's bounding box (the base's box ends at z = 0.868 m in this scene, so the centre must be above z = 0.873 m), and its (x, y) lies inside the tower base's footprint.",
                  "The ball is not held."],
            std=["The footprints of the tower base and of the ball lie inside the table bounds (1 mm tolerance).",
                 "The ball is still: its speed is below 5 cm/s and its vertical speed below 3 cm/s.",
                 "The ball's centre is more than 5 mm above the top of the tower base's bounding box (the ball is 3 cm across), and seen from above it lies inside the tower base's footprint.",
                 "The ball is not held."],
            unchecked="the rings (where they are, whether they are on the tower) and how long the ball stays",
            text_vs_code="\"The tower\" is the tower base alone: the rings are not referenced. \"Stably\" is one speed sample at the end."),
    ),
    "collect_screws": dict(
        status="pr", rid="10-collect-screws", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["container", "dustpan", "screw"],
        std_objects="Objects here: container, dustpan, screw.",
        difficulty="Collect a screw into a container using a dustpan. The screw is too small to be easily grasped directly. The robot must use the dustpan to collect the screw first and then put it into the container. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-collect-screws-i00-limi__xxcMFF8 (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[51.0, 57.8], predicate_sha="529b52ab11ae00a0",
        criterion=dict(
            priv=["Only one point is tested: the screw's position (the origin of its pose).",
                  "That point is over the table: x 0.19-1.02 m and |y| <= 0.71 m (the table bounds grown by 2 cm), and not below z = 0.71 m (5 cm under the table top).",
                  "That point lies inside the container's axis-aligned bounding box grown by 1 mm in x and y, and in z between 2 cm below the box's bottom and 2 cm above its top (the container's box spans x 0.529-0.631 m, |y| <= 0.051 m, z 0.760-0.878 m in this scene, so z <= 0.898 m)."],
            std=["Only one point is tested: the screw's reference point (the origin of its mesh, near its centre).",
                 "That point is over the table, within the table bounds grown by 2 cm, and no lower than 5 cm under the table top.",
                 "That point lies inside the container's bounding box, grown by 1 mm sideways and by 2 cm at the bottom and at the top (the container is about 10 cm across and 12 cm tall)."],
            unchecked="the rest of the screw, whether a gripper (or the dustpan) still holds it, the dustpan, and any speed",
            text_vs_code="\"Into the container\" is a single point inside the container's box, with 2 cm allowed above the rim and no release check: a screw lying on the rim, or held just above the opening, also counts."),
    ),
    "cover_with_lid": dict(
        status="pr", rid="13-cover-with-lid", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["pot without lid", "small lid", "lid medium", "lid large"],
        std_objects="Objects here: pot without lid, small lid, lid medium, lid large.",
        difficulty="Cover a pot precisely using the correct sized lid. This requires reasoning about cross-sectional fit. Only the correctly sized circular lid will cover the opening with minimal excess. The circular geometry and ring reference enable precise centering. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-cover-with-lid-i00__Jb7Zzve (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[50.0, 54.1], predicate_sha="b097bc5f5fafb814",
        criterion=dict(
            priv=["The pot's footprint lies inside the table bounds (1 mm tolerance).",
                  "Exactly one lid qualifies. A lid qualifies when its footprint lies inside the table bounds (1 mm tolerance), its position's z is more than 1 cm above the pot's position's z (the origins of their poses: the pot's is at its mid-height, z = 0.829 m here; a lid's about 1 cm above its lowest point), its footprint area is 0.85-1.40 times the pot's, and at least 80 % of its footprint area lies over the pot's footprint.",
                  "In this scene only `lid large` is inside the size window (area about 1.23 times the pot's; `lid medium` about 0.60, `small lid` about 0.25). Its overlap can reach only about 0.81 (the pot's area over the lid's), so it must sit within about 1.4 cm of concentric with the pot."],
            std=["The pot's footprint lies inside the table bounds (1 mm tolerance).",
                 "Exactly one lid qualifies. A lid qualifies when its footprint lies inside the table bounds (1 mm tolerance), its reference point (the origin of its mesh, about 1 cm above its lowest point) is more than 1 cm above the pot's (at the pot's mid-height), its footprint area is 0.85-1.40 times the pot's, and at least 80 % of its footprint area lies over the pot's footprint.",
                 "Here only the large lid is inside the size window (area about 1.23 times the pot's; the medium lid about 0.60, the small one about 0.25). Its overlap can reach only about 0.81, so it must sit within about 1.4 cm of concentric with the pot."],
            unchecked="contact (whether the lid rests on the pot), any height beyond the one above, whether a gripper holds it, and where the other two lids are (they never qualify)",
            text_vs_code="\"Using one lid\" means exactly one qualifying lid: the wrong-size lids never qualify, so putting them on the pot as well costs nothing. \"Cover\" does not require the lid to rest on the pot: the large lid held concentrically above it counts."),
    ),
    "dominos": dict(
        status="pr", rid="06-dominos", eval_index=0, blenderkit=False, backend="cpu", oracle="partial",
        objects=["white block 1", "white block 2", "white block 3", "white block 4", "red block", "target area"],
        std_goal="Push the red block onto the green target area. White blocks 3, 2 and 1 and the red block stand upright in a row, a domino chain that ends just short of the green target area; white block 4 stands on its own, closer to the robot.",
        std_objects="Objects here: five blocks (four white, one red) standing upright, and the flat green target area on the table. The red\nblock and white blocks 1-3 are out of the arms' reach.",
        difficulty="Physical reasoning rather than pick-and-place: the red block ends on the target only through a chain of collisions. White block 3 has to be toppled along the chain direction (about 26 deg off the table's x axis in this scene) hard enough to carry through blocks 2 and 1, and gently enough that the red block falls onto the 6 x 10 cm patch instead of past it. Nothing can be undone within one attempt, but the agent may reset and rehearse as often as it likes before committing a trajectory.",
        reference="`solution/oracle_dominos.py` (RoboWits ships no expert; written for this instance): it pushes white block 3 near its top along the chain direction with the closed right gripper, then retreats and lets the chain fall. `solution/solve.sh` records it into a trajectory.",
        oracle_evidence={
            "priv": "Reference solution solution/oracle_dominos.py (written for this instance; RoboWits ships no expert). It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-dominos-i00-oracle-thin-0925-000706, trial robowits-dominos-i00__qL9Rvsb, 2026-09-25 (laptop, Intel; success=1, deterministic=1, instance_exact=1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 4f933a76ce2ce34b) and the oracle script (byte-identical to that run's /app/output/gen.py). Changed since then, so the label is partial: the grader tests/grade.py (dev/qineng 82d76c61 added the GPU-backend exception; this PR writes the verdict before the video) and the tooling rcb_robowits.py (dev/qineng 5aa848bd, bddfc520, adce3fef, 8f0ebd55, 82d76c61, 6c0b439e, fe5fb9e6, 1515ea4e). Not re-run on this version (static validation only, 2026-10-01).",
            "std": "Reference solution solution/oracle_replay.py, which streams the privileged oracle's recorded joint rows (solution/oracle_qpos.npy) through the client. It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-dominos-i00-limited-oracle-v2b-0924-2125, trial robowits-dominos-i00-limited__pnfVz4w, 2026-09-25 (laptop, Intel; the protocol's 2.0 service, then named rcb-limited; success=1, live 1, replay 1, deterministic 1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 4f933a76ce2ce34b) and the joint rows (equal to that run's recorded trajectory). Changed since then, so the label is partial: the grader (dev/qineng 82d76c61; this PR: the crash-recovery fields and infra_error), the sim adapter server.py (dev/qineng 6c0b439e: protocol 2.2; this PR: crash recovery), the shared layer rcb_limited.py / rcb_client.py (dev/qineng 42813008; this PR: the eai-standard/2.2 layer with crash recovery), the tooling rcb_robowits.py (as in the privileged twin), the collect hook, the client image and pins, and the oracle player (this PR: it recovers from a crash). Not re-run on this version (static validation only, 2026-10-01)."},
        build_s=[60.1, 66.1], predicate_sha="b304057e5b679f0e",
        criterion=dict(
            priv=["At least 50 % of the red block's footprint area lies over the target area's footprint (overlap area / the red block's footprint area >= 0.5)."],
            std=["At least half of the red block's footprint area lies over the green target area's footprint."],
            unchecked="anything else: the red block's height, orientation, whether it rests on the table or is held, the white blocks, and the table bounds",
            text_vs_code="Only where the red block is, seen from above, is checked: how it got there is not (the red block lifted or held over the target also counts). RoboWits' docstring says 30 %; the code requires 50 %."),
    ),
    "gap_retrieve": dict(
        status="pr", rid="03-gap-retrieve", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["left boundary block", "right boundary block", "target area", "lemon"],
        std_objects="Objects here: left boundary block, right boundary block, target area, lemon.",
        difficulty="Retrieve a lemon from a narrow gap and place it on a target area. The lemon is located in a narrow channel formed by two boundary blocks. The gap is too narrow for the gripper to enter directly. The robot must first move one boundary block to widen the gap, then retrieve the lemon. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-gap-retrieve-i00-limite__hTYhCVz (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[48.7, 55.7], predicate_sha="f7a661f813c84700",
        criterion=dict(
            priv=["The lemon rests on the table: the bottom of its bounding box within 2 cm of the table top (z = 0.76 m).",
                  "The footprints of the lemon and of the target area lie inside the table bounds.",
                  "At least 80 % of the lemon's footprint area lies over the target area.",
                  "The lemon is not held."],
            std=["The lemon rests on the table: the bottom of its bounding box within 2 cm of the table top.",
                 "The footprints of the lemon and of the target area lie inside the table bounds.",
                 "At least 80 % of the lemon's footprint area lies over the target area.",
                 "The lemon is not held."],
            unchecked="the boundary blocks (where they end up) and any speed",
            text_vs_code="The text and the grader agree; the grader adds the thresholds above (the lemon on the table, 80 % over the target, released)."),
    ),
    "hold_cup": dict(
        status="pr", rid="09-hold-cup", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["cup", "slope", "coaster", "target area"],
        std_objects="Objects here: cup, slope, coaster, target area.",
        difficulty="Put a cup on a sloped target area without it sliding down. The cup and slope lack sufficient friction to remain stationary. The robot must utilize the surface friction of the coaster to stabilize the cup. The coaster acts as a high-friction interface. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-hold-cup-i00-limited__BiMATyh (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[54.5, 55.9], predicate_sha="a11368a9ea9bb0d9",
        criterion=dict(
            priv=["At least 50 % of the cup's footprint area lies over the target area.",
                  "The cup is still: its speed is at most 5 mm/s.",
                  "The cup is upright: its roll and its pitch (the x and y of its XYZ Euler angles) are each within 20 degrees of level.",
                  "The cup's footprint lies inside the table bounds.",
                  "The cup is not held."],
            std=["At least 50 % of the cup's footprint area lies over the target area.",
                 "The cup is still: its speed is at most 5 mm/s.",
                 "The cup is upright: tilted by at most 20 degrees about each of the two horizontal axes.",
                 "The cup's footprint lies inside the table bounds.",
                 "The cup is not held."],
            unchecked="the coaster (where it is, whether the cup stands on it) and how long the cup stays",
            text_vs_code="\"Without sliding down\" is one speed sample at the end (at most 5 mm/s), not a time window."),
    ),
    "move_cube": dict(
        status="pr", rid="28-move-cube", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["cube 1", "cube 2", "cube 3", "goal line", "smooth slope", "rough slope"],
        std_objects="Objects here: cube 1, cube 2, cube 3, goal line, smooth slope, rough slope.",
        difficulty="Move a cube past the goal line using slopes with different friction. This task requires the robot to understand and exploit the friction properties of different surfaces. The smooth slope has very low friction, while the rough slope has very high friction. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-move-cube-i00-limited__9Vd2dpc (robowits-lunaxh-limited-0929, standard) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[54.2, 57.9], predicate_sha="298cfe0cd7d8fc02",
        criterion=dict(
            priv=["At least one of the three cubes has its position at x > 0.9 m. The goal line is the strip at x = 0.9 m (x points away from the robot), so the cube's centre must be past it, on its far side from the robot."],
            std=["At least one of the three cubes has its centre past the goal line, on the line's far side from the robot."],
            unchecked="anything else: whether the cube is on the table or still on a slope, its height, orientation, whether a gripper holds it (a cube held past the line counts, and so does one pushed off the far edge of the table)",
            text_vs_code="\"To the left of the goal line\" means beyond it, farther from the robot than the line, not to the left as the robot sees it."),
    ),
    "raise_platform": dict(
        status="pr", rid="24-raise-platform", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["heavy book", "cup support 1", "cup support 2", "support cube 1", "support cube 2"],
        std_objects="Objects here: heavy book, cup support 1, cup support 2, support cube 1, support cube 2.",
        difficulty="Place the heavy book on top of the cup supports. The goal requires supporting a load above the table. Assembling two equal-height supports and a rigid deck creates a stable platform that can hold the book without touching the table. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-raise-platform-i00__uqturjE (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[51.7, 54.7], predicate_sha="91aebcabbec20c06",
        criterion=dict(
            priv=["None of the book and the two cup supports has the bottom of its bounding box more than 5 cm below the table top (z < 0.71 m fails).",
                  "The book is raised: the bottom of its bounding box is more than 5 mm above the table top (z > 0.765 m).",
                  "Each cup support's position (x, y) lies inside the book's footprint or within 5 cm of its outline.",
                  "The bottom of the book's bounding box is within 3.5 cm of the top of each cup support's bounding box (the cup supports are fixed and their boxes end at z = 0.856 m, so the book's bottom must be at z 0.821-0.891 m).",
                  "The book is not held."],
            std=["None of the book and the two cup supports has fallen more than 5 cm below the table top.",
                 "The book is raised: the bottom of its bounding box is more than 5 mm above the table top.",
                 "Each cup support's centre, seen from above, lies inside the book's footprint or within 5 cm of its outline.",
                 "The bottom of the book's bounding box is within 3.5 cm of the top of each cup support's bounding box (the cup supports are about 10 cm tall).",
                 "The book is not held."],
            unchecked="the support cubes, contact or load (the book may rest on anything at the right height), any speed, and the table bounds",
            text_vs_code="\"On the cup supports\" means the book's bottom within 3.5 cm of both cups' tops, with both cups under (or within 5 cm of) its outline; the cups need not carry it."),
    ),
    "retrieve_cube": dict(
        status="pr", rid="02-retrieve-cube", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["deep narrow container", "cube", "target area"],
        std_objects="Objects here: deep narrow container, cube, target area.",
        difficulty="Retrieve a cube from a deep narrow container and place it on a target area. The cube is initially inside a deep narrow container that the robot gripper cannot directly reach. The robot must tilt or manipulate the container to pour the cube out, then move it to the target area. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-retrieve-cube-i00__eRfLscE (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[50.1, 66.0], predicate_sha="00ca6c2bce970329",
        criterion=dict(
            priv=["The cube is at table height: the bottom of its bounding box between 1 cm below and 3 cm above the table top (z 0.75-0.79 m).",
                  "The footprints of the cube and of the target area lie inside the table bounds grown by 1 cm.",
                  "Less than 50 % of the cube's footprint area lies over the container's footprint.",
                  "At least 50 % of the cube's footprint area lies over the target area."],
            std=["The cube is at table height: the bottom of its bounding box between 1 cm below and 3 cm above the table top.",
                 "The footprints of the cube and of the target area lie inside the table bounds grown by 1 cm.",
                 "Less than 50 % of the cube's footprint area lies over the container's footprint.",
                 "At least 50 % of the cube's footprint area lies over the target area (the cube is 1.5 cm, the target area 12 cm square)."],
            unchecked="whether a gripper still holds the cube, any speed, and where the container ends up",
            text_vs_code="The text and the grader agree; the grader makes \"out of the container\" and \"on the target\" precise (half of the cube's footprint) and requires the cube at table height."),
    ),
    "stack_bowls": dict(
        status="pr", rid="19-stack-bowls", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        objects=["large bowl", "medium bowl"],
        std_objects="Objects here: large bowl, medium bowl.",
        difficulty="Nest the smaller bowl concentrically inside the larger one. Concentric alignment leverages circular geometry; matching rims provide a strong geometric signal for proper nesting. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-stack-bowls-i00__6pB7rjT (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[53.1], predicate_sha="ea9a7867baeecfb3",
        criterion=dict(
            priv=["Both bowls' footprints lie inside the table bounds grown by 1 cm.",
                  "The centre of the medium bowl's footprint (the mean of its outline's vertices) is within 1.1 cm, in (x, y), of the large bowl's."],
            std=["Both bowls' footprints lie inside the table bounds grown by 1 cm.",
                 "Seen from above, the centre of the medium bowl's footprint is within 1.1 cm of the large bowl's."],
            unchecked="heights and nesting order (the medium bowl need not be inside the large one: held above it, or the large bowl set concentrically on top of it, also pass), whether a gripper holds a bowl, and any speed",
            text_vs_code="\"Nest inside\" is not checked: only that the two bowls are concentric seen from above, within 1.1 cm."),
    ),
    "stack_cubes": dict(
        status="pr", rid="14-stack-cubes", eval_index=0, blenderkit=False, backend="cpu", oracle="partial",
        objects=["base cube 1", "base cube 2", "apex cube", "apex target"],
        std_objects="Objects here: three 5 cm cubes (two grey, one red) and a green dot on the table.",
        priv_gripper_note=("- Cubes are 5 cm, grippers open to 10 cm. The gripper tip frame's +z axis is the approach direction and +x the\n"
                           "  finger-closing direction; `p[\"top_down_quat\"](yaw)` builds a vertical-approach orientation whose fingers close along\n"
                           "  `yaw`. `check_being_held` counts a gripper tip inside the apex cube's bounding box (+3 cm): retreat after releasing.\n"),
        difficulty="Tabletop bimanual manipulation with a 16-DoF joint-target action space: three 5 cm cubes must be rearranged into a two-layer stack whose apex sits within 2.5 cm of a marker, and the two base cubes must end up touching. The tooling gives only thin primitives (IK moves on RoboWits' own pink/pinocchio IK, joint moves, gripper, hold): grasping and placing are the agent's to build. The wrist joints have ±60° limits (a vertical approach is only reachable for finger-closing directions within roughly ±60° of world y), the placement tolerances are tight, and the assembled stack must survive the release and retreat of the gripper. The physics runs at ~700 control steps/s, so iteration is cheap.",
        reference="`solution/oracle_stack_cubes.py`: with the left arm, grasp base cube 1 and place it axis-aligned on the marker, grasp base cube 2 and place it flush against it, grasp the apex cube and place it centred over the marker, then retreat. Its grasp / place skills live in `solution/ref_primitives.py` (never in the agent image). `solution/solve.sh` records it into a trajectory.",
        oracle_evidence={
            "priv": "Reference solution solution/oracle_stack_cubes.py with its skills in solution/ref_primitives.py (written for this instance; RoboWits ships no expert). It scored 1 under Harbor -a oracle on an earlier version of this task: job robowits-stack-cubes-i00-oracle-thin-0925-000706, trial robowits-stack-cubes-i00__2rVdsVe, 2026-09-25 (laptop, Intel; success=1, deterministic=1, instance_exact=1; an uncommitted tree just before dev/qineng f15dbdb7). Same since then: the frozen instance (state hash 41c4d7e7d7193b0d) and the oracle script (byte-identical to that run's /app/output/gen.py; ref_primitives.py unchanged since f15dbdb7). Changed since then, so the label is partial: the grader tests/grade.py (dev/qineng 82d76c61 added the GPU-backend exception; this PR writes the verdict before the video) and the tooling rcb_robowits.py (dev/qineng 5aa848bd, bddfc520, adce3fef, 8f0ebd55, 82d76c61, 6c0b439e, fe5fb9e6, 1515ea4e). Not re-run on this version (static validation only, 2026-10-01).",
            "std": "Reference solution solution/oracle_replay.py, which streams the privileged oracle's recorded joint rows (solution/oracle_qpos.npy) through the client. It scored 1 under Harbor -a oracle on the dev/qineng 9eb18edf version of this task (protocol 2.2, then named rcb-limited): job v22-laptop-oracle-stack-cubes-0413, trial robowits-stack-cubes-i00-limited__Yw2oaio, 2026-09-29 (laptop, Intel; success=1, live 1, replay 1, deterministic 1). Same since then: the frozen instance (state hash 41c4d7e7d7193b0d), the joint rows (equal to that run's recorded trajectory) and the tooling rcb_robowits.py. Changed since then, so the label is partial: the grader (this PR: the crash-recovery fields and infra_error), the sim adapter server.py and the shared layer rcb_limited.py / rcb_client.py (this PR: crash recovery), the collect hook, the client image and pins, and the oracle player (this PR: it recovers from a crash). Not re-run on this version (static validation only, 2026-10-01)."},
        build_s=[57.9, 70.9], predicate_sha="cfabaa984c41a033",
        criterion=dict(
            priv=["Both base cubes rest on the table: the bottom of each bounding box within 1.5 cm of the table top (z = 0.76 m).",
                  "The two base cubes touch: their bounding boxes are at most 1 cm apart along each of the three axes.",
                  "The bottom of the apex cube's bounding box is no lower than 1 cm below the top of `base cube 1`'s bounding box.",
                  "The apex cube's centre (x, y) is within 2.5 cm of the apex target's (the green dot's) centre.",
                  "The apex cube is not held."],
            std=["Both grey base cubes rest on the table: the bottom of each bounding box within 1.5 cm of the table top.",
                 "The two base cubes touch: their bounding boxes are at most 1 cm apart along each of the three axes.",
                 "The red cube is up on the base: the bottom of its bounding box is no lower than 1 cm below the top of one grey cube's bounding box (RoboWits' `base cube 1`; with both grey cubes standing on the table, their tops are about 5 cm above it).",
                 "Seen from above, the red cube's centre is within 2.5 cm of the green dot's centre.",
                 "The red cube is not held."],
            unchecked={"priv": "whether the apex cube rests on both base cubes (only its height against base cube 1 is tested), any speed, and where the base cubes are relative to the dot",
                       "std": "whether the red cube rests on both grey cubes (only its height against one of them is tested), any speed, and where the grey cubes are relative to the dot"},
            text_vs_code={"priv": "\"A stable two-layer stack\" is one final-state check of the conditions above, without a speed check: the apex must be high enough relative to base cube 1 and over the dot, nothing more.",
                          "std": "\"A stable two-layer stack\" is one check of the conditions above, without a speed check: the red cube must be high enough and over the dot, nothing more."}),
    ),
    "stand_bulb": dict(
        status="pr", rid="16-stand-bulb", eval_index=0, blenderkit=True, backend="cpu", oracle="none",
        host_cpu_vendor="GenuineIntel",   # the instance was frozen on Intel; on AMD the rebuilt scene is out of tolerance
        objects=["target patch", "stabilizing ring", "tall object with curved bottom"],
        std_objects="Objects here: target patch, stabilizing ring, tall object with curved bottom.",
        difficulty="Stand a tall object with curved bottom stably within a target area. A tall object with curved bottom is prone to tipping due to a curved base. A surrounding ring provides lateral support and increases the effective base, using geometry for stability. The tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-stand-bulb-i00__BrTmH6k (robowits-lunaxh-0925-2042, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[55.3, 59.1], predicate_sha="85bb7682b5e1e276",
        criterion=dict(
            priv=["The footprints of the tall object and of the target patch lie inside the table bounds (1 mm tolerance).",
                  "The tall object is \"upright\": its axis-aligned bounding box is taller than it is wide (its z extent exceeds both its x and its y extent).",
                  "The tall object is still: its speed is at most 0.05 m/s.",
                  "At least 80 % of the tall object's footprint area lies over the target patch.",
                  "The tall object is not held."],
            std=["The footprints of the tall object and of the target patch lie inside the table bounds (1 mm tolerance).",
                 "The tall object is \"upright\": its bounding box is taller than it is wide.",
                 "The tall object is still: its speed is at most 5 cm/s.",
                 "At least 80 % of the tall object's footprint area lies over the target patch.",
                 "The tall object is not held."],
            unchecked="the stabilizing ring, any tilt the bounding-box test lets through (for this 21.6 x 12 cm object, tilts up to roughly 45 degrees can pass), and how long it stands",
            text_vs_code="\"Stand ... stably\" means the bounding-box test above and one speed sample at the end (at most 5 cm/s)."),
    ),
    "stand_pages": dict(
        status="pr", rid="07-stand-pages", eval_index=0, blenderkit=False, backend="cpu", oracle="none",
        objects=["page A with eyelets", "page B with eyelets", "stabilizing bar"],
        std_goal="Stand the two pages up on the table, using the stabilizing bar as a hinge pin: the bar goes through the eyelets of both pages so that they brace each other.",
        std_objects="Objects here: two thin grey pages with a row of eyelets along one edge and a grey bar (20 cm long, 1.5 cm square\nsection), all lying flat on the table in front of the robot.",
        difficulty="Physical reasoning with a mechanical constraint: two thin, light pages (meshes with eyelets along one edge) and a 20 cm bar lie flat on the table. A page cannot stand on its own; the bar has to go through the eyelets of both pages so that they brace each other, and at the end both pages must stand upright (Euler x and y within 15° of 0° or 180°), rest on the table, lie inside the table bounds and not be held. It takes bimanual coordination and an insertion through small holes with thin objects, and the tooling's primitives are thin (IK moves, joint moves, gripper, hold).",
        oracle_evidence="No reference solution: RoboWits ships no expert or planner for its seed tasks. Solvable: model trial robowits-stand-pages-i00__npAKeQv (calib-high-1944, privileged) graded success=1, deterministic=1 by the separate verifier; nop scored 0. These records are from earlier versions of the task (before protocol v1.0, on the same frozen instance and predicate); not re-run on this version (static validation only, 2026-10-01). Human review per family (protocol §2.7).",
        build_s=[51.7, 55.1], predicate_sha="74545fcf0c97cd76",
        criterion=dict(
            priv=["For each of the two pages:",
                  "  its roll and its pitch (the x and y of its XYZ Euler angles) are each within 15 degrees of 0 or of 180 degrees (the page meshes stand upright at roll = pitch = 0; any yaw);",
                  "  its footprint lies inside the table bounds (no tolerance);",
                  "  the bottom of its bounding box is within 3 cm of the table top (z = 0.76 m);",
                  "  it is not held."],
            std=["For each of the two pages:",
                 "  it stands upright: within 15 degrees of vertical about both horizontal axes (either face forward, any heading);",
                 "  its footprint lies inside the table bounds (no tolerance);",
                 "  the bottom of its bounding box is within 3 cm of the table top;",
                 "  it is not held."],
            unchecked="the stabilizing bar and any connection between the pages (the hinge), and any speed",
            text_vs_code="The hinge is not checked: two pages standing upright on the table and released at the end pass, with or without the bar through their eyelets."),
    ),
}

# Not coming back (user decision 2026-10-01; docs/benchmarks/robowits.md, Families).
DROPPED = {
    "roll_up_ball": "unsolvable in the frozen scene: the 10 cm box must fit inside the high basket's bounding box shrunk by 1 cm, "
                    "but the basket is only 9.2 cm tall, so the height test can never pass",
    "cylinder_through_hole": "unsolvable in the frozen scene: the peg must reach half its 9.1 cm length below the fixed hole plate's "
                             "bounding box, whose bottom is already under the table top, i.e. about 5 cm into the table",
    "separate_marbles_and_sand": "broken frozen instance: the five marbles lie on the table under the fixed jar, below its bounding box, "
                                 "while the sand is still inside, so 'keep the marbles in the jar' means putting all five back in",
    "align_chopsticks": "its frozen scene hits NaN constraint forces in Genesis within a few steps (excluded before protocol v1.0)",
}
