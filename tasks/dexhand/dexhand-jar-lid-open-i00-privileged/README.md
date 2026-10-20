# dexhand-jar-lid-open-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-jar-lid-open-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `jar_lid_open` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave episode on the Marvin right arm (1,159 controls, success after 1,009); it passes two fresh-process replays with identical state hashes, float32 rounding, and the Harbor oracle in both modes (standard: the same rows submitted through the public client). solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (1,242 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Open the jam jar with the robot's right hand and set its lid aside on the worktop. Scene (world frame, metres, z up, +x forward from the robot): the worktop top is at z = 0.75 and spans |x| <= 0.45, |y| <= 0.58. A filled 297 ml glass jam jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.86) stands upright on the worktop centred at x = -0.22, y = -0.08. Nothing holds the jar: it stands on its own weight and glass-on-worktop friction, which resists only about 0.13 N m of twisting torque, so the hand must turn the lid without turning, sliding or tipping the jar. Its red 64.8 mm twist-off steel lid (32 g) is closed. Jar and lid are free rigid bodies. The closure is a lug thread made of contact geometry only: four inclined glass ramps on the jar neck hold four inward lugs of the lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive rotation about +z relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the gaps between the ramps (turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without lifting, the lugs run into the next ramps' leads, and turning clockwise from the closed position tightens and jams. The lid is lightly closed: no vacuum, seal adhesion or tightening torque is modelled, and the jam is part of the jar's rigid mass, not a fluid. Complete three stages in this order. (1) Unscrew: while the lid is still seated on the thread (lid origin less than 6 mm above its closed height and within 4 mm of the jar axis, in the jar frame), its counter-clockwise turn relative to the jar, unwrapped after every physics substep, reaches at least 1.049 rad. (2) Lift clear: afterwards, the lowest point of the lid skirt rises more than 30 mm above the jar rim. (3) Set aside: afterwards, for 50 consecutive controls (1 s), the lid touches the worktop and touches neither the hand nor the jar, is upright (tilt at most 0.15 rad), has its centre at least 90 mm horizontally from the jar axis, moves at most 0.02 m/s and turns at most 0.3 rad/s, while the jar touches the worktop, is not touched by the hand, is upright within 0.10 rad and moves at most 0.02 m/s. The episode ends with success at that moment; a partial sequence never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when: the jar tilts more than 15 degrees (jar_tipped), slides more than 30 mm horizontally from its start (jar_slid) or is lifted more than 15 mm (jar_lifted); the lid touches the worktop before stage 2 (lid_knocked_off); the lid drops: at any substep it touches nothing (no hand, jar or worktop contact) while its centre of mass moves downward faster than 0.3 m/s (about a 5 mm free fall; there is no window to catch it again), or its centre of mass moves downward faster than 1.0 m/s whatever it touches (lid_dropped); the jar or the lid touches the floor, its origin falls more than 5 mm below the worktop top or leaves the worktop footprint (lid_off_table, jar_off_table) or the workspace box x in [-0.45, 0.45] m, y in [-0.40, 0.40] m, z in [0.73, 1.25] m (object_left_workspace); the lid leaves the thread upward while its lugs are not in the gaps between the ramps, i.e. its turn modulo pi/2 is outside [1.019, 1.291] rad (lid_forced_through_thread); the parked left arm or the left hand touches the jar or the lid (left_arm_contact; moving the left arm is not blocked, but the task is done by the right arm and hand); or the physics becomes unstable (unstable_physics). Later actions cannot undo a failure. Only robot actuator targets are allowed: the joints of the Marvin right arm and its hand (the left arm stays parked with its hand open), no object teleports, grasp welds, scripted object motion or direct object forces. Any robot part touching the jar or the lid counts as the hand touching it. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
One dexterous hand on the right arm of a Tianji Marvin robot does everything and nothing holds the jar: the lid only
comes off through its passive lug thread, so the hand must grip the steel skirt firmly enough to turn it at least
1.049 rad counter-clockwise without turning, sliding or tipping the free 550 g jar (it stands on its own weight and
friction, about 0.13 N m of twist resistance), lift the freed lid straight off while its lugs are in the ramp gaps,
carry it aside and set it down upright without dropping it. The arm's 7 joints are position servos without gravity
compensation and with limited wrist ranges, so the turn about the lid axis has to come from the whole arm. Fingertip
pads pressed too low touch the wider glass body and drag the jar along; a lid lifted before the lugs clear the ramps
pulls the whole jar up. The predicate checks the ordered unscrew, lift and set-aside stages and a released 1 s hold;
any tipped, slid or lifted jar, a knocked-off or dropped lid, or an object leaving the worktop ends the episode as a
failure at once.

## Reference solution
`solution/trajectory.npz` holds the validated Sharpa Wave episode on the arm (1,159 controls; a replay ends at
success after 1,009): the right hand descends palm-down over the lid, grips the skirt with its fingertips (thumb
opposite index, middle and ring), the arm turns the grip counter-clockwise about the lid axis until the lid has passed
1.049 rad, lifts the lid 70 mm, carries it about 170 mm aside, lowers it tilted so the lid meets the worktop first,
releases and withdraws. The rows are arm-joint and finger targets recorded from a closed-loop authoring controller
(inverse kinematics of the arm toward the hand poses of the earlier floating-stage witness, re-timed for the arm);
privileged `solve.sh` hands these rows in as the trajectory; standard `solve.sh` submits the same rows as float64
through the public client (`hold`, 20 ms per row, chunks of at most 250 rows). With `wuji`, `solution/wuji/` holds a
1,242-row Wuji Hand 2.2 episode (success after 1,097). The authoring tools compute robot kinematics and motor targets
only; they never drive an object pose or apply an object force, and they are never copied into the agent's
environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (1,242 rows of motor targets, physical contact only). With `DEXHAND_HAND=wuji` set for the oracle, `solve.sh` hands it in instead of the Sharpa Wave rows; the verifier replays it with the Wuji Hand 2.2.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final state hashes (integration state, verdict
state and physics parameters); in standard mode the replay hash must also equal the live final hash. A replay ends at the first
success or the first failure. Failures are fail-fast and permanent (jar tipped, slid or lifted, lid knocked off or
dropped, an object off the worktop or out of the workspace, the lid forced through the thread, the parked left arm or left hand touching the jar or the lid, unstable physics, or
the 3,000-control budget). A no-op fails. Human review and full agent-trial calibration remain pending; report this
task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 5 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-3 integration smoke of the Marvin-arm families (Harbor 0.23, efe:dexhand-0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier 3.40-3.51 GiB with two concurrent replays, standard sim sidecar 2.13-2.65 GiB, agent containers < 0.05 GiB; one fresh replay process 1.75-1.81 GiB max RSS (os.wait4); x1.2 rounded up to a GB, the values of pot_shelf_transfer (the same robot); two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run three or four 1.8 GiB Marvin simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: the DexHand family of this task. Scene: the approved
T14 "Open a jam jar" scene-expansion film (real-size 297 ml jam jar, 67 mm body, 110 mm tall, 550 g filled; red
64.8 mm twist-off steel lid, 32 g); its continuous-glass and printed-label visual meshes are copied byte for byte
(`assets/manifest.json`, sha256-checked at build). Physics: MuJoCo 3.4.0, 2 ms implicitfast steps, elliptic friction
cones. Jar and lid are free bodies; the TO-style lug closure is contact geometry only (four inclined glass ramps of
box segments, 3 mm rise over a 1.0 rad run plus a 0.2 rad tightening lead, and four steel lugs with 0.8 mm radial
play to the glass finish), with no joint, weld, actuator or scripted release. The ramps collide only with the lid lugs because the steel skirt encloses them.
The lid is lightly closed: no vacuum, seal adhesion or preload; the jam is part of the jar's rigid mass and is not
simulated. The Sharpa Wave assets are pinned to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74`
(Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same arm flanges with its vendor joints,
actuators and contact geometry unchanged. The robot is the Tianji Marvin stand with two 7-DoF arms (the
pot_shelf_transfer rig: position servos kp 700, kv 48, no gravity compensation) carrying a hand on each flange; the
left arm stays parked. The scene keeps the T14 objects and their relation; the worktop stands at a table height for
the robot (top at z = 0.75 m) with the jar 0.34 m in front of the robot's shoulders. This is single-arm lid-opening
feasibility, not a bimanual or zero-shot claim.

### Change Log
- 2026-10-16 (video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
