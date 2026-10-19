# dexhand-boot-sole-brush-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-boot-sole-brush-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `boot_sole_brush` |
| Oracle | `full` — solution/trajectory.npz: the 1,688-row Sharpa Wave witness on the Marvin right arm (success at control 1,538, then 150 hold rows), authored by tracking the wave-2 floating-hand episode's hand-root poses with arm inverse kinematics (closed loop, joint integral; the brush-transfer segment re-timed 3x slower); two fresh-process replays succeed with identical state hashes, float32-rounded rows succeed, and no arm, stand or parked-hand contact occurs in any physics substep. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Brush all six soil clods off the upward-facing sole of the boot into the collection tray. The boot stands sole-up on a fixed boot-rack peg inside the tray (its sole plane is at z = 1.292 m); six small dry soil clods are lodged in its tread, held there by gravity and friction only (no glue or cohesive bond is simulated, so a clod moves as soon as something pushes it). The shoe brush lies bristles-down on the counter: pick it up with the robot's right hand and sweep the sole with the bristles. Success requires, in order: (1) the brush's bristle field touches the boot while the hand touches the brush and the brush does not touch the counter, for at least 10 controls in total; (2) every clod has been touched by the brush's bristle field (contact with the wooden back does not count) while it was still up on the boot (clod centre at most 0.01 m below the sole plane), and every clod centre lies inside the tray walls (x in [0.366, 0.694] m, y in [-0.184, 0.384] m) below the wall top (z < 0.931 m); (3) then, for 50 consecutive controls (1 s), all six clods stay in the tray with linear speed at most 0.05 m/s while the brush touches neither the boot nor any clod and is withdrawn (bristle-field centre at least 0.04 m above the sole plane, or at least 0.18 m horizontally from the sole centre). The episode ends with success at that moment; fewer than six clods never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the boot moves more than 0.03 m or tilts more than 0.35 rad from its reset pose; when a clod touches the counter or the floor, falls below the counter top (z < 0.886 m) or leaves the workspace box x in [0.25, 1.2] m, y in [-0.45, 0.45] m, z in [0.886, 1.8] m; when any part of the right hand touches a clod (clods must be brushed, not picked); when the brush touches the floor, the tray or the rack, falls below the counter top, leaves the workspace box, or is released in the air (it touches nothing but clods while its centre of mass sinks faster than 0.2 m/s); when any part of the robot other than its right hand (the stand, the torso, a link of either arm, the parked left hand) touches anything, including the robot itself; or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed: no welds, teleports, scripted object motion or applied object forces. The boot, brush and clods are free rigid bodies; the brush's 32 bristle tufts touch the world through one compliant bristle-pad contact proxy (individual fibre bending is not simulated) and the clods are rigid (no fracture or adhesion). The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The robot's right hand, on a 7-joint arm without gravity compensation, must pick up a 14 cm shoe brush from the
counter with a stable contact grasp, carry it to a boot that stands sole-up 0.4 m above the tray (the brushing hand
works above the robot's shoulder height, near the edge of the arm's reach), and sweep the sole so that every one of six small loose clods is pushed over the sole
edge and falls into the tray, without touching a clod with the hand, without letting go of the brush in the air and
without knocking the boot off its peg. The clods weigh 1 g and are irregular; the sole has a central groove, an arch
and raised lugs, and the fingers that hold the brush hang close to the sole, so strokes have to be planned so that no
finger meets a clod. Pressing too hard or sweeping too fast flings clods past the tray, which fails the episode at
once, and so does any contact of the arms, the stand or the parked left hand. Partial cleaning never counts.

## Reference solution
`solution/trajectory.npz` holds the Sharpa Wave authoring witness on the Marvin right arm (1,688 rows of 58 motor
targets, success at control 1,538, followed by hold rows): a top-down pinch of the brush back (thumb on the near long
face, three fingers on the far face), lift, four centre-out strokes over the forefoot and the heel, withdrawal and a
1 s hold, with the left arm parked throughout. Privileged mode replays these rows; standard mode submits the same rows
through `rcb_client` (float64, hold interpolation, 50 Hz). The authoring tools
(`scripts/dexhand/families/boot_sole_brush/tools/arm_port.py`, which tracks the hand poses of an earlier floating-hand
witness with arm inverse kinematics) compute robot kinematics and motor targets only; they never drive an object pose
or apply an object force, and they are not copied into the task.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure. Failures are
fail-fast, checked after every 2 ms physics substep, and permanent: a displaced boot, a clod touching the counter or
floor or leaving the workspace, a hand-clod contact, a brush that touches the floor, tray or rack or is released in the
air, any contact of a robot part other than the right hand (stand, torso, arm links, the parked left hand), unstable
physics, or the 3,000-control budget. A no-op fails. Human review and full agent-trial calibration remain
pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-3 integration smoke of the Marvin-arm families (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier 3.40-3.51 GiB with two concurrent replays, standard sim sidecar 2.13-2.65 GiB, agent containers < 0.05 GiB; one fresh replay process 1.75-1.81 GiB max RSS (os.wait4); x1.2 rounded up to a GB, the values of pot_shelf_transfer (the same robot); two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run three or four 1.8 GiB Marvin simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 2.65 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/boot_sole_brush/`, generated by `scripts/dexhand/generate.py`, derived from scene
T29 ("Brush adhered debris from a shoe sole"), a kinematic demonstration in which no hand acted and the debris motion
was prescribed. The boot is the Poly Haven "Rubber Boots" left boot (CC0, credit: Powered by Poly Haven) with the
source scene's 292 convex contact patches; the brush is an original geometric reconstruction of a 14 cm beech shoe
brush with 32 plant-fibre tufts; the clods are the source scene's seeded irregular aggregates. Differences from the
demonstration, all disclosed in the task text: the soil is loose, lodged in the tread by gravity and friction (the
demo's cohesive soil bond is not simulated, so "adhered" debris becomes lodged debris); the boot rests sole-up on a
fixed boot-rack peg instead of being lifted, turned and set down by the hand, and the brush is not put back; the
bristle field touches the world through one compliant pad proxy (individual fibres do not bend); the tray is a 45 mm
deep basin with a soft, damped rubber liner. The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted on the same arm
flanges with its vendor joints, actuators and contact geometry unchanged. The robot is the Tianji Marvin two-arm rig
of `pot_shelf_transfer` (`arm_rig.py`; meshes checked against the image's Tianji manifest), standing on the floor
beside the counter.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
