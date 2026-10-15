# dexhand-bicycle-pump-stroke-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-bicycle-pump-stroke-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `bicycle_pump_stroke` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave authoring trajectory (902 controls, success after 802; six counted strokes, released hold); the standard oracle submits the same rows as float64 through the public client. Two fresh-process replays succeed with identical state hashes, and the rows rounded to float32 also succeed. solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (867 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Inflate the bicycle tire with the portable bicycle pump. A mini floor pump (Topeak Mini Morph type, 154 g class, barrel 0.25 m tall) stands free on its folding foot on the bench next to a 406 (20 inch) wheel lying on the bench; the pump's hose head is already locked on the wheel's Schrader valve and the tire starts partly inflated at 207.8 kPa gauge. The pump's T handle rests at the top of its 0.20 m travel: the piston is a passive slide whose compressed-air spring pushes the handle back up (about 6 N at the top and 46 N at the bottom of the stroke) with viscous damping and 1 N seal friction. A stroke counts when the handle is pushed down to a piston depth of at least 0.18 m (90 % of the travel) and then returns to a depth of at most 0.04 m (20 %); shallower strokes never count and are not failures. The tire pressure is a checker quantity, not simulated air: every counted stroke adds 380 Pa (the mean rise per stroke of the source gas model). Success requires, in this order: (1) at least 6 counted strokes; (2) tire pressure at least 210.0 kPa gauge; (3) the handle released at the top: piston depth at most 0.01 m, no hand contact with any part of the pump, pump tilt at most 0.0873 rad (5 degrees) from upright, pump centre-of-mass speed at most 0.02 m/s and handle speed at most 0.02 m/s, held continuously for 50 consecutive controls (1 s). The episode ends with success at that moment. The episode ends immediately with failure, checked after every 2 ms physics substep, when the pump tilts more than 0.2618 rad (15 degrees) from upright, when its base moves more than 0.03 m horizontally from its start or rises more than 0.02 m above it, when its centre of mass falls below the bench top (z < 0.70 m) or any pump part touches the floor, or when the physics becomes unstable; later actions cannot undo a failure. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The wheel, valve, locked pump head and hose are static props.

## Difficulty
The pump is free-standing, light (125 g) and narrow-footed (28 mm wide foot), with its T handle 0.45 m above the
bench: every downstroke needs about 45 N along the pump axis, and pushing off-axis levers it over. Six full-depth
strokes are required (partial strokes never count), then the hand must let go with the handle back at the top and the
pump standing still. Any tip, slide or lift of the pump ends the episode as a failure at once.

## Reference solution
`solution/trajectory.npz` replays the validated Sharpa Wave authoring trajectory: 902 controls; the sixth stroke is
counted at control 708 and the released hold completes at control 802, where the replay ends with success (the last
100 rows hold the final targets as slack). In privileged mode `solve.sh` hands these rows in; in standard mode it
submits the same rows as float64 through the public client in 250-row chunks. The authoring controller that produced
them (`scripts/dexhand/families/bicycle_pump_stroke/tools/controller.py`: palm over the pump foot, fingers wrapped over
the T-handle grip, six eased strokes to about 0.19 m depth, release and withdraw) computes motor targets only; it never
drives an object pose or applies an object force, and it is never copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (867 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: the pump tipping over 15 degrees, sliding more than 3 cm, lifting more than
2 cm, falling below the bench top or touching the floor, unstable physics, or the 3,000-control budget. The frozen
thresholds come from the task, never from an agent archive. A no-op fails. Human review and full agent-trial
calibration remain pending; report this task as provisional.

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
Source: `scripts/dexhand/families/bicycle_pump_stroke/`, generated by `scripts/dexhand/generate.py`. Scene geometry,
colours and poses come from the approved T50 scene-expansion film export (`assets/t50_scene.json`, meshes and sha256
manifest in `assets/`): Topeak MINI MORPH pump geometry and masses, the 32-spoke Schwalbe Big Apple 57-406 wheel with
its smooth tire shell, the Schrader valve and the locked TRK-RP04 head with its hose. Modelling scope: the pump is a
free rigid body on its foot; the piston chamber is a linear air spring on a passive slide (200 N/m, reference 0.23 m:
6 N at the top, 46 N at the bottom of the stroke), 15 N s/m damping and 1 N seal friction; tire pressure is a checker
quantity (380 Pa per counted stroke from a partly inflated 207.8 kPa start; the source scene needed 28 strokes from
200 kPa). The head is pre-locked on the valve and the wheel, valve, head and hose are static props (the two hose
segments at the pump outlet are visual only). The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same
wrist stage with its vendor joints, actuators and contact geometry unchanged.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
