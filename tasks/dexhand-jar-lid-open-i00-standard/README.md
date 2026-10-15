# dexhand-jar-lid-open-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-jar-lid-open-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `jar_lid_open` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave witness (825 controls, success after 675); it passes two fresh-process replays with identical state hashes, float32 rounding, and the Harbor oracle in both modes (standard: the same rows submitted through the public client). solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (905 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Open the jam jar with one dexterous hand and set its lid aside on the worktop. Scene (world frame, metres, z up): the worktop top is at z = 0.30 and spans |x| <= 0.45, |y| <= 0.40. A filled 297 ml glass jam jar (550 g, 67 mm body diameter, 110 mm tall, rim at z = 0.41) stands upright on the worktop centred at x = 0, y = 0. Nothing holds the jar: it stands on its own weight and glass-on-worktop friction, which resists only about 0.13 N m of twisting torque, so the hand must turn the lid without turning, sliding or tipping the jar. Its red 64.8 mm twist-off steel lid (32 g) is closed. Jar and lid are free rigid bodies. The closure is a lug thread made of contact geometry only: four inclined glass ramps on the jar neck hold four inward lugs of the lid, so the closed lid cannot be pulled off. Turning the lid counter-clockwise seen from above (positive rotation about +z relative to the jar) slides the lugs up the ramps; at 1.049 rad they pass the ramp ends, and while they sit in the gaps between the ramps (turn between 1.049 and about 1.26 rad) the lid lifts off freely; turned further without lifting, the lugs run into the next ramps' leads, and turning clockwise from the closed position tightens and jams. The lid is lightly closed: no vacuum, seal adhesion or tightening torque is modelled, and the jam is part of the jar's rigid mass, not a fluid. Complete three stages in this order. (1) Unscrew: while the lid is still seated on the thread (lid origin less than 6 mm above its closed height and within 4 mm of the jar axis, in the jar frame), its counter-clockwise turn relative to the jar, unwrapped after every physics substep, reaches at least 1.049 rad. (2) Lift clear: afterwards, the lowest point of the lid skirt rises more than 30 mm above the jar rim. (3) Set aside: afterwards, for 50 consecutive controls (1 s), the lid touches the worktop and touches neither the hand nor the jar, is upright (tilt at most 0.15 rad), has its centre at least 90 mm horizontally from the jar axis, moves at most 0.02 m/s and turns at most 0.3 rad/s, while the jar touches the worktop, is not touched by the hand, is upright within 0.10 rad and moves at most 0.02 m/s. The episode ends with success at that moment; a partial sequence never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when: the jar tilts more than 15 degrees (jar_tipped), slides more than 30 mm horizontally from its start (jar_slid) or is lifted more than 15 mm (jar_lifted); the lid touches the worktop before stage 2 (lid_knocked_off); the lid drops: at any substep it touches nothing (no hand, jar or worktop contact) while its centre of mass moves downward faster than 0.3 m/s (about a 5 mm free fall; there is no window to catch it again), or its centre of mass moves downward faster than 1.0 m/s whatever it touches (lid_dropped); the jar or the lid touches the floor, its origin falls more than 5 mm below the worktop top or leaves the worktop footprint (lid_off_table, jar_off_table) or the workspace box x in [-0.45, 0.45] m, y in [-0.40, 0.40] m, z in [0.28, 0.80] m (object_left_workspace); the lid leaves the thread upward while its lugs are not in the gaps between the ramps, i.e. its turn modulo pi/2 is outside [1.019, 1.291] rad (lid_forced_through_thread); or the physics becomes unstable (unstable_physics). Later actions cannot undo a failure. Only robot actuator targets are allowed: one hand on its wrist stage, no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
A single hand does everything and nothing holds the jar: the lid only comes off through its passive lug thread, so the
hand must grip the steel skirt firmly enough to turn it at least 1.049 rad counter-clockwise without turning, sliding or
tipping the free 550 g jar (it stands on its own weight and friction, about 0.13 N m of twist resistance), lift the
freed lid straight off while its lugs are in the ramp gaps, carry it aside and set it down upright without dropping it.
Fingertip pads pressed too low touch the wider glass body and drag the jar along; a lid lifted before the lugs clear the
ramps pulls the whole jar up. The predicate checks the ordered unscrew, lift and set-aside stages and a released
1 s hold; any tipped, slid or lifted jar, a knocked-off or dropped lid, or an object leaving the worktop ends the
episode as a failure at once.

## Reference solution
`solution/trajectory.npz` holds the validated Sharpa Wave witness (825 controls; a replay ends at success after 675):
a palm-down fingertip grasp of the lid skirt (thumb opposite index, middle and ring), a counter-clockwise wrist turn
about the lid axis until the lid has turned 1.18 rad, a 70 mm lift, a carry to 174 mm from the jar axis, a tilted
lowering so the lid meets the worktop first, release and withdrawal. Privileged `solve.sh` hands these rows in as the
trajectory; standard `solve.sh` submits the same rows as float64 through the public client (`hold`, 20 ms per row,
chunks of at most 250 rows). The authoring controller (`scripts/dexhand/families/jar_lid_open/demo.py`) computes
robot kinematics and motor targets only; it never drives an object pose or applies an object force, and it is never
copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (905 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final state hashes (integration state, verdict
state and physics parameters); in standard mode the replay hash must also equal the live final hash. A replay ends at the first
success or the first failure. Failures are fail-fast and permanent (jar tipped, slid or lifted, lid knocked off or
dropped, an object off the worktop or out of the workspace, the lid forced through the thread, unstable physics, or
the 3,000-control budget). A no-op fails. Human review and full agent-trial calibration remain pending; report this
task as provisional.

## Compute resources
Minimum allocation for one trial (docs/PROTOCOL.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/PROTOCOL.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 0.96 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/jar_lid_open/`, generated by `scripts/dexhand/generate.py`. Scene: the approved
T14 "Open a jam jar" scene-expansion film (real-size 297 ml jam jar, 67 mm body, 110 mm tall, 550 g filled; red
64.8 mm twist-off steel lid, 32 g); its continuous-glass and printed-label visual meshes are copied byte for byte
(`assets/manifest.json`, sha256-checked at build). Physics: MuJoCo 3.4.0, 2 ms implicitfast steps, elliptic friction
cones. Jar and lid are free bodies; the TO-style lug closure is contact geometry only (four inclined glass ramps of
box segments, 3 mm rise over a 1.0 rad run plus a 0.2 rad tightening lead, and four steel lugs with 0.8 mm radial
play to the glass finish), with no joint, weld, actuator or scripted release. The ramps collide only with the lid lugs because the steel skirt encloses them.
The lid is lightly closed: no vacuum, seal adhesion or preload; the jam is part of the jar's rigid mass and is not
simulated. The Sharpa Wave assets are pinned to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74`
(Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same wrist stage with its vendor joints,
actuators and contact geometry unchanged. This is lid-opening feasibility on a floating wrist stage, not a full-arm,
bimanual or zero-shot claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
