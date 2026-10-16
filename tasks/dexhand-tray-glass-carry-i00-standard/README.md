# dexhand-tray-glass-carry-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-tray-glass-carry-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating-bimanual` |
| Family / instance | `tray_glass_carry` |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave authoring trajectory (1,072 controls; the episode ends with success after 952, 120 hold rows of slack) in both modes; it passes two fresh-process replays with identical state hashes and still succeeds with rows rounded to float32. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (1,148 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Carry the serving tray with the two filled glasses from the source counter (centre x = 0.35 m) to the receiving counter (centre x = 0.78 m). Two dexterous hands, each on its own six-axis wrist stage, start above the two ends of the tray's long axis; the tray rim has open handle slots under the rim bar at both of those ends. Carry the tray around the steel bottle standing on the source counter at (0.52, 0.22) m and across the 30 mm gap between the counters, set it down on the receiving counter and let go. The liquid is not simulated: a glass counts as spilled when its axis tilts more than 15 degrees from vertical. Glass positions are measured in the tray frame, whose origin is the bottom centre of the tray floor (the floor's top surface is at height +2 mm in that frame). A glass is seated when its base centre lies inside the tray footprint ellipse (semi-axes 0.165 m x 0.23 m) and at a height between -3 mm and +8 mm in the tray frame. Success requires, in this order: (1) lift-off: the tray touches neither counter, its base is at least 30 mm above the counter top (z >= 0.91 m) and both glasses are seated; (2) placement: the tray rests on the receiving counter only, its centre within 20 mm in x and 30 mm in y of (0.78, 0.00) m, tray tilt at most 5 degrees, tray yaw within 10 degrees of its start orientation (long axis along y), both glasses seated; (3) release: the placement conditions plus no hand touching the tray or a glass, both glasses within 6 degrees of vertical, tray and glasses at rest (every linear speed at most 0.02 m/s and every angular speed at most 0.2 rad/s), held for 50 consecutive controls (1 s). The episode ends with success at that moment; a partial transfer never counts. The episode ends immediately with failure, checked after every 2 ms physics step, when a glass tilts more than 15 degrees (spilled); a glass base centre leaves the footprint ellipse, or its height in the tray frame exceeds +22 mm (20 mm above the floor's top surface) or falls below -10 mm; the bottle touches the tray, a glass or a hand; the tray touches the source counter again after lift-off; the tray touches the receiving counter while its centre is more than 40 mm in x or 50 mm in y from (0.78, 0.00) m (no dragging); the tray or a glass moves downward faster than 0.6 m/s (dropped; a free fall of about 18 mm), or faster than 0.2 m/s while unsupported (the tray touching no hand and no counter; a glass touching neither the tray, the other glass, a hand nor a counter); the tray tilts more than 35 degrees; the tray or a glass goes below z = 0.86 m, touches the floor or leaves the workspace box x in [0, 1.15] m, y in [-0.6, 0.6] m, z in [0.86, 1.12] m (so the tray cannot be lifted over the bottle); or the physics becomes unstable. Later actions cannot undo a failure. Only actuator targets of the two wrist stages and hands are commanded: no object teleports, grasp welds, scripted object motion or applied forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
Two hands on two independent wrist stages must coordinate a closed-chain carry of a light, wide tray holding two
free, tall glasses: the tray has no grip other than the thin rim and the open handle slots at its ends, the glasses
stand loose on a 0.5-friction tray floor and fail at 15 degrees of tilt, the straight path is blocked by a fixed
bottle, the counters are separated by a gap, the set-down must land within 20 x 30 mm of the target without dragging,
and the hands must let go without disturbing the tray. Any spill, escaped or dropped glass, obstacle contact, dragged
tray or object below the counter tops ends the episode as a failure at once.

## Reference solution
`solution/` holds a validated Sharpa Wave trajectory of 1,072 controls (the episode ends with success after 952
controls; 120 hold rows of slack follow); in privileged mode `solve.sh` re-saves it to `/app/output/trajectory.npz`,
in standard mode it submits the same rows as float64 through the public client. Both hands hang fingers-down outside
the two handle slots, curl the fingertips inward and push them through the slots under the handle bar (a hook grip),
lift the tray 100 mm, carry it around the bottle (detour to y = -0.17 m) and across the gap, lower it onto the
receiving counter, pull the fingertips back out and rise. The authoring controller
(`scripts/dexhand/families/tray_glass_carry/tools/controller.py`) reads simulator state to place the fingertips and
level the hooks, but it only ever writes motor targets; it is never copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (1,148 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent (checked after every 2 ms physics step): spilled glass (tilt above 15 degrees),
glass off the tray footprint or lifted off the tray, any contact of the bottle with the tray, a glass or a hand, the
tray set back on the source counter or dragged on the receiving counter, a tray or glass falling faster than 0.6 m/s
(a free fall of about 18 mm) or faster than 0.2 m/s while unsupported (no drop-and-catch), a tray tilted beyond 35
degrees, any object below the counter tops, on the floor or outside the workspace, unstable physics, or the
3,000-control budget. The frozen thresholds come from the task, never from an agent archive. A no-op fails. Human
review and full agent-trial calibration remain pending; report this task as provisional.

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
Source: `scripts/dexhand/families/tray_glass_carry/`, generated by `scripts/dexhand/generate.py`. Scene: scene-expansion
task T48 ("Carry a tray with filled drink cups"); the tray (original ROMANTISK-style perforated oval serving tray, 365
convex mesh pieces) and the two glasses are frozen verbatim from `scripts/hand_support/tasks/T48/model.xml` in
`assets/t48_tray_glasses.xml` (sha256 in `assets/manifest.json`); counters, bottle obstacle, glass shells and the
150 mL water volumes are rebuilt from the T48 scene builder's dimensions. The T48 source was a kinematic demonstration
with prescribed object motion; here every object moves only through contact. Liquid is not simulated: each glass is a
rigid 0.275 kg body (glass plus 150 mL of water) and spilling is defined as a glass tilt above 15 degrees. The left
(mirrored) and right Sharpa Wave hands are those of the accepted `sweep_dustpan` rig (MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74`, Apache-2.0), each on its own six-axis wrist stage (slides kp 4000 N/m,
200 N; hinges kp 200 N m/rad, 30 N m). The Wuji Hand 2.2 models (`hand2/hand2_2`, wuji-technology/wuji-description
commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702`, MIT) replace them on the same stages with their vendor joints,
actuators and contact geometry unchanged. This is a bimanual transport feasibility task on floating wrist stages, not
an arm-reachability, liquid-sloshing or zero-shot claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
