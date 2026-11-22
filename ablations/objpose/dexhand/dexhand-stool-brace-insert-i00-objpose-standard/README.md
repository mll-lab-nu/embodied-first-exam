# dexhand-stool-brace-insert-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-stool-brace-insert-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `stool_brace_insert` / seed 0 |
| Oracle | `full` — solution/trajectory.npz replays a Sharpa Wave authoring trajectory (3,006 controls; success after 2,806) in both modes: two fresh-process replays with identical state hashes, float32 rows succeed, Harbor oracle 1 in privileged and standard mode (standard: rows submitted through the public client, live hash = replay hash). |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Assemble the cross brace of a pine stool dry frame. The lower side frame lies flat on the table with its four bores facing up and three rails already standing seated in three of them. The loose cross brace (a 0.26 m pine rail with an 8 mm dowel exposed 15 mm at each end) lies on the table, and the opposite side frame lies upside down beside the lower frame. Pick up the brace, seat one of its dowels in the empty bore of the lower frame, then lift the opposite side frame and lower it onto all four upper dowels so that both brace dowels end up seated in their legs. Ordered stages: (1) brace lifted: no brace-table contact, brace centre raised at least 0.05 m and its lowest bounding-box corner at least 0.02 m above the table top; (2) one brace dowel seated in a lower-frame bore; (3) opposite side frame lifted (the same lift test); (4) assembled: each of the eight bores holds exactly one seated dowel and every rail, the brace included, has one dowel seated in each side frame. A dowel is seated in a bore when its tip is 12 mm to 19 mm past the bore entry along the bore axis (12 mm is 80% of the exposed dowel), its tip is within 1.6 mm of the bore axis and the dowel axis is within 0.105 rad of the bore axis. Success: after stage 4 the assembled condition holds with no hand contact on any frame or rail and every part's centre-of-mass speed at most 0.02 m/s and angular speed at most 0.2 rad/s for 50 consecutive controls (1 s); the episode then ends. A single seated brace dowel or any partial assembly never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the lower frame moves more than 0.03 m or tilts more than 10 degrees; a pre-seated rail is pulled to less than 8 mm in its bore or tilts more than 10 degrees; the brace touches the table after stage 1, or its centre drops below 0.09 m above the table top after stage 1; the brace tilts more than 20 degrees after stage 2; the opposite side frame touches the table after stage 3 or tilts more than 20 degrees from its upside-down carrying orientation after stage 3; any part with no contact at all (not held, not supported) has its centre of mass falling faster than 0.2 m/s (a drop); any part touches the floor, has its centre below the table top (z < 0.74 m) or leaves the workspace box x in [0.23, 1.23] m, y in [-0.73, 1.03] m, z in [0.70, 1.60] m; or the physics becomes unstable. Later actions cannot undo a failure. Only robot actuator targets are allowed: no object teleports, grasp welds, scripted object motion or direct object forces. All parts are free rigid pine bodies; the bores are hollow contact geometry of the source size (4.1 mm radius for the 4.0 mm dowels: 0.1 mm radial clearance, no entry chamfer); glue, screws, the seat and load capacity are not modelled. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
A single hand has to turn a loose 0.29 m brace upright, insert an 8 mm dowel into a hollow 8.2 mm bore (0.1 mm radial
clearance, no entry chamfer), let go without knocking it over, then carry a 0.58 kg side frame and lower it onto four dowels at once so
that the brace's second dowel enters the opposite leg. Grip slip, tilt during transport, a nudged pre-seated rail or a
dropped part end the episode at once; a single seated dowel or a partial frame never counts.

## Reference solution
`solution/` replays a Sharpa Wave authoring trajectory (3,006 controls; the replay ends at success after 2,806). In
privileged mode the oracle hands the rows in as `/app/output/trajectory.npz`; in standard mode `oracle_replay.py`
submits the same float64 rows through the public client in chunks. The
authoring controller (not copied into any task directory)
pinches the brace near one end, pivots it upright about its far dowel on the table, re-centres the hanging dowel tip
over the empty bore from the simulator state, lowers it, opens the pinch, then grips a crossrail of the opposite side
frame with thumb and three fingers, lifts and levels it, aligns its bores over the four dowel tips and lowers it. It
computes robot motor targets only; it never sets an object pose or applies an object force.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent (see the task text): a displaced lower frame, a knocked pre-seated rail, a dropped
or knocked-over brace, a dropped side frame, any free-falling part, floor contact, a part below the table top or out of
the workspace, unstable physics, or the 6,000-control budget. The thresholds come from the frozen task, never from an
agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as
provisional.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 10 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 5 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 10 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task, from scene T27
("Assemble a wooden stool cross brace", an ODDVAR-style pine dry frame authored for the scene-expansion set). The pine
grain texture is the scene's own procedural texture (`assets/`, sha256 manifest). The Sharpa Wave assets are pinned to
MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model
(`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702`
(MIT) and mounted on the same wrist stage. Modelling scope: the source geometry is kept (leg 0.43 x 0.03 x 0.03 m,
rails 0.26 m, 8 mm dowels exposed 15 mm, 16 mm blind bores of 4.1 mm radius, i.e. 0.1 mm radial clearance and no entry chamfer, built from 24 convex
sectors; the dowel ends are rounded capsules); parts are free rigid bodies with the source
masses; the frames touch the table through thin skids under each leg face; the solver uses 5 noslip iterations (no
frictional creep in held grasps); the seat and eight screws are static decor; glue, screws and the final upright turn
of the source film are not part of the task.
