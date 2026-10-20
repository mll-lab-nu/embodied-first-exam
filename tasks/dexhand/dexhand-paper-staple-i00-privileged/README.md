# dexhand-paper-staple-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-paper-staple-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `paper_staple` |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave authoring trajectory on the Marvin right arm (942 controls; success after 742, then 200 unexecuted hold rows of slack). Two fresh-process replays succeed with identical state hashes. The standard oracle submits the same rows through the public client. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Square up three loose A5 sheets and staple them at a corner with the desk stapler, using the dexterous hand on the right arm of a fixed two-arm robot (the left arm stays parked). The sheets lie as a misaligned stack (each upper sheet shifted toward +x) with the bottom sheet's corner resting on the stapler's anvil mouth and the far edge on the desk. Slide the stack into the stapler throat against the stapler's paper stop, square the sheets, press the stapler head through its full stroke onto the stack and let it spring back. Stages, in order: (1) aligned: every corner of sheets 1 and 2 within 2.0 mm of the matching corner of sheet 0 (in sheet 0's plane), the sheets stacked in order (each 0.25-1.5 mm above the one below, along sheet 0's normal) and sheets 0-1 and 1-2 in contact; (2) in the throat: with (1), the staple point (stapler base frame (0.063, 0, 0.012) m, on the anvil under the driver blade) lies inside every sheet 3-30 mm from both edges of one corner and every sheet mid-plane is 0-6 mm above it; (3) pressed: with (1) and (2), the head hinge within 0.01 rad of its bottom stop (0.1701 rad) and the driver blade touching the top sheet; (4) released: after (3), with (1) and (2), the head back up (hinge <= 0.02 rad), no robot contact (either hand or any arm link) with any sheet or the stapler and every sheet's centre of mass slower than 0.02 m/s for 50 consecutive controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when a sheet centre falls below z = 0.77925 m (1 mm under its resting height on the desk top) or any sheet corner below z = 0.765 m, a sheet centre leaves the desk (x 0.25-0.99 m, y -0.36-0.36 m) or the workspace box (x 0.2-1.1 m, y -0.45-0.45 m, z 0.70-1.20 m), a sheet or the stapler touches the floor or a desk leg, a sheet or the stapler has no contact at all while its centre of mass falls faster than 0.2 m/s, the stapler base moves more than 3 cm horizontally from its reset position or tilts more than 0.26 rad, an arm link or the robot stand (anything of the robot but the two hands) touches the desk, the stapler or a sheet, or the physics becomes unstable; later actions cannot undo a failure. Only arm-joint and finger actuator targets are allowed. The head's return spring needs about 10 N pressed 8 cm in front of its hinge to start the stroke and about 25 N at the bottom stop. Sheets are 0.5 mm rigid plates (real A5 size and mass); staple formation is not simulated. At most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The three sheets must be squared to 2 mm at all four corners while being slid as one stack into a narrow stapler
throat against its paper stop by fingertips on a 7-joint arm without gravity compensation; pushing too low rides over
the sheet edges, pushing off-centre rotates the stack or shoves the stapler, and the spring-loaded head (about 10 N
rising to 25 N) must then be pressed through its full stroke and released with the stack still squared and in place.
Any sheet pushed off the desk, a dropped sheet, a knocked/tipped stapler or an arm link touching the desk, stapler or
sheets ends the episode at once.

## Reference solution
`solution/` replays the validated Sharpa Wave authoring trajectory on the Marvin right arm (942 controls; the replay
ends at success after 742 controls): a two-fingertip rake squares and feeds the stack against the paper stop, then the
straight index and middle fingers press the handle to the bottom stop (peak hand force about 40 N) and release it. The
authoring controller converts desired hand poses to arm joint targets
by inverse kinematics on the robot model only; it never drives an object pose or applies an object force, and it is
never copied into the agent's environment or image. No Wuji Hand 2.2 reference episode is packaged for this version.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent (see the task text). The frozen instance and thresholds come from the task, never
from an agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as
provisional.

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
Source: the DexHand family of this task, from the scene-expansion
T36 scene (desk, NOVUS B2 envelope stapler at its source pose, A5 sheets; stapler shells exported to `assets/*.obj` with
sha256 manifest). Robot: the Tianji Marvin stand and arms of `pot_shelf_transfer` (`arm_rig.py`, robot id
`marvin-bimanual-sharpa-wave`), stand origin at (0.58, -0.66, 0.10) on the floor (z 0) beside the desk's -y edge,
heading 135 deg, right arm active, left arm parked; no robot part overlaps the desk or its legs.
Sharpa Wave: MuJoCo Menagerie `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); Wuji Hand 2.2 (`hand2/hand2_2`):
wuji-technology/wuji-description `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted on the same arms.
Modelling scope: sheets are rigid 0.5 mm plates (five times real thickness, real A5 size and 80 g/m2 mass); the reset
props the bottom sheet's corner on the anvil mouth (a physically settled rest pose) instead of starting flat on the
desk as in the source; a paper insertion stop behind the anvil (not part of the real B2) squares the stack and sets the
staple position; the magazine is rigid with the base and the handle with its driver blade turns on one passive
spring-returned hinge (about 10 N to start, 25 N at the bottom stop) with a bottom stop; staple piercing and clinching
are not simulated. Paper-paper, paper-desk and paper-chrome friction are 0.4, 0.15 and 0.1.

### Change Log
- 2026-10-16 (video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
