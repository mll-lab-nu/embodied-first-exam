# dexhand-usb-plug-insert-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-usb-plug-insert-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `usb_plug_insert` |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave episode on the Marvin right arm (1,595 controls; success after 1,475, then 120 unexecuted hold rows of slack): pinch and lift as in the floating-stage episode, a planned joint-space change of the arm's IK branch while the plug is carried, closed-loop alignment in front of the desk edge, insertion into port 4, release and a 1 s released hold. Two fresh-process replays succeed with identical state hashes, and the rows rounded to float32 also succeed. The standard oracle submits the same rows through the public client. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Connect the USB cable to the hub. You drive the right arm and hand of a Tianji Marvin robot standing in front of the desk (left arm parked). A four-port USB hub rests free on the desk with its ports facing the desk's front edge (world -y); the cable's USB-A plug lies on its side on the desk, with its 0.5 m cable. Pick up the plug, turn it so its polarized (top) face points up, and insert it into port 4, the rightmost port (hub-local x = +33 mm), then let go. Success requires three stages in order. (1) Grasped and lifted: the thumb and at least one other finger touch the rigid plug (shell, housing or strain relief), the plug touches nothing else, and the plug origin (the centre of its metal shell tip) is at z >= 0.73 m (30 mm above the desk top at z = 0.70 m). (2) Seated in port 4: in that port's frame the shell tip is at least 10.8 mm deep in the 12 mm cavity (90%), within 0.6 mm of the port axis sideways and 0.5 mm vertically, the plug axis is within 5 degrees of the port axis, and the plug's top face is within 20 degrees of the hub's top face (correct polarity). (3) Released: the plug stays seated in port 4 with no hand contact on the plug, its cable or the hub and a plug speed of at most 0.01 m/s for 50 consecutive controls (1 s). The episode ends with success at that moment. A plug seated in any other port never counts. The episode ends immediately with failure when the hub moves more than 20 mm from its start position or tilts more than 20 degrees, when the plug falls below z = 0.685 m, when the plug or hub leaves the workspace box x in [0.25, 1.15] m, y in [-0.40, 0.95] m, z in [0.685, 1.10] m, when the cable's far USB-B end falls more than 5 cm below the desk top, when an arm link, the robot's stand or torso, or the parked left hand touches anything (`robot_collision`: the desk, the floor, the hub, the plug or cable, the working hand or another robot part), when the plug is dropped (after stage 1, at the first control at which the plug has no hand contact on it or its cable, is not engaged at least 3 mm deep in a port, and either falls faster than 0.2 m/s or lies on the desk or floor), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. Each port is an open rectangular cavity with generous clearance (0.25 mm per side across, 0.15 mm per side in height); the receptacle tongue and contacts are visual, and there are no retention springs, so the plug stays in by friction and its own weight. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
A 7 g plug lying on its side must be picked up with fingertips much larger than its 8 mm housing, turned polarity-up in
the hand, carried past the desk edge and aligned to a cavity with 0.15-0.25 mm clearance, then released without
pulling it back out or disturbing the light, free hub. The grasp must survive the drag of a 0.5 m cable. Any drop,
displaced hub or partial insertion fails.

## Reference solution
`solution/trajectory.npz` holds the validated Sharpa Wave trajectory on the Marvin right arm: 1,595 rows of 58 targets;
the replay ends at success after 1,475 controls (the remaining 120 hold rows are slack and are not executed). The hand
picks the plug up with a thumb against index and middle fingertips and lifts it; the arm then changes its posture in
joint space while carrying the plug (the pick and the insertion under the desk edge need different arm
configurations), turns it polarity-up in front of the desk edge, aligns it with port 4 in closed loop on the plug pose,
inserts it about 11.9 of 12 mm, releases it (index up, thumb down, then open) and withdraws. In standard mode the oracle
submits the same rows through `rcb_client` in 250-row chunks. The authoring controller that produced the rows
(`scripts/dexhand/families/usb_plug_insert/tools/arm_author.py`, closed loop on the simulator state) computes robot
motor targets only; it never drives an object pose or applies an object force, and it is never copied into the agent's
environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent: a dropped plug, the plug below z = 0.685 m, the hub moved more than 20 mm or
tilted more than 20 degrees, plug or hub outside the workspace box, the cable's far end pulled off the desk, an arm
link, the robot's stand or the parked hand touching anything, unstable
physics, or the 3,000-control budget. A no-op fails. Human review and full agent-trial calibration remain pending;
report this task as provisional.

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
Source scene: T24 "Connect a USB cable to a held device" (scene-expansion kinematic demo,
`scripts/scene_expansion/repairs/usb_cable_meta_delivery_trajectory_r1`): original authored real-scale four-port hub
and USB-A-to-B cable dimensions and materials (`assets/usb_scene.json`, sha256 in `assets/manifest.json`). Physical
modelling for a 2 ms dexterous-hand task: the hand is carried by the right arm of a Tianji Marvin robot standing in
front of the desk (floor 0.10 m lower than in the source, so the desk top is 0.90 m above it, and the desk's two front
legs set back under the top to clear the robot's base plate; both disclosed), the hub rests free on the desk (one hand; the hub is not held), each port is
an open cavity with generous clearance, receptacle tongue and contacts are visual, retention springs are omitted, the
hub's upstream cable is a visual rigidly attached to the hub, and the plug cable is a passive 20-link ball-joint rod.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
