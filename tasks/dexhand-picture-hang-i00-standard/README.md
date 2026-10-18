# dexhand-picture-hang-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-picture-hang-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `picture_hang` |
| Oracle | `full` — solution/trajectory.npz: 869 Sharpa Wave rows on the Marvin dual-arm robot (success after 669 controls, 200 rows of slack), recorded from the authoring controller tools/controller.py through tools/arm_author.py (IK to arm joint targets; motor targets only). Two fresh-process replays end with identical state hashes; float32-rounded rows also succeed. Wave-3 port of the 2026-10-14 floating-stage oracle. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Hang the framed picture on the two wall hooks. The free 2.0 kg frame (52 x 52 x 6 cm) stands upright on a console; two brass picture hooks are installed on the wall and two D-rings on passive hinges are screwed to the back of the frame. Lift the frame off the console with both hands, engage BOTH D-rings on their matching hooks (left ring on the left hook, right ring on the right hook), then let go: the picture must hang still and level from both hooks with no hand touching it. Success requires, in this order: (1) lift-off: the frame origin (the centre of its bottom edge) at least 0.02 m above its start height z = 0.72 m and no contact with the console; (2) engagement: both rings threaded on their own hooks (the hook's load saddle passes through the ring's D loop, with the ring between the hook's upturned lip and the wall; a ring resting on top of the lip does not count) and each ring touching its hook; (3) a released hang for 50 consecutive controls (1 s): both rings threaded, each hook carrying at least 20 % of the frame's weight vertically through its ring and both hooks together at least 85 %, no hand touching the frame, no frame contact with the console or the floor, the frame's top edge level within 3 degrees, its tilt from upright at most 0.10 rad, its centre-of-mass speed at most 0.02 m/s and its angular speed at most 0.15 rad/s. The episode ends with success at that moment; one engaged hook, or rings left on the hook lips, never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the frame touches the floor, when its origin leaves the workspace box x in [0.20, 0.76] m, y in [-0.45, 0.45] m, z in [0.60, 1.30] m, when it tilts more than 0.6 rad from upright, when after lift-off its origin falls more than 0.01 m below its start height, when after both rings were engaged no hand touches the frame while a ring is not threaded (it fell off a hook), when an arm, torso or stand link of the robot touches anything (only the hands may make contact), or when the physics becomes unstable; and when after lift-off the frame is held by nothing (no hand contact, no console contact and not hanging threaded on both hooks with both rings touching them): at the end of any control, or at any substep where its centre of mass is also moving down faster than 0.2 m/s (dropped, even if caught again, released early, dangling from one hook or resting on the hook lips). Later actions cannot undo a failure. Only the robot's actuator targets (14 arm joints and the fingers of both hands) are allowed; no grasp welds, scripted object motion or forces on the frame. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
A 2 kg, 52 cm frame has to be lifted and carried by two coordinated arms and hands without dropping or tipping it
(no arm link may touch anything), and both of
its passive D-rings (18 x 20 mm loops of 2 mm wire, 3 mm behind the frame's back) have to be passed over two 6 mm hook
saddles at the same time: the clearance between each hook's upturned lip and the wall is about 1 cm, the rings sit
behind the frame where cameras cannot see them well, and the frame's back face meets the hook lips just as the rings
clear them. Then the hands must let go so that the hooks alone carry the frame, level and still. Releasing early,
hanging the frame from one hook, or leaving the rings on top of the lips is a failure at once; there is no partial
credit.

## Reference solution
`solution/trajectory.npz` replays a validated Sharpa Wave trajectory on the dual-arm robot (869 controls; the replay
ends at success after 669). It was recorded from the authoring controller in the family folder
(`scripts/dexhand/families/picture_hang/tools/controller.py`, driven through `tools/arm_author.py`), which reads the
simulator state and converts its hand-pose commands into the 14 arm joint targets by inverse kinematics: the two palms
squeeze the top of the side rails, the arms lift the frame, carry it to the wall with the ring pivots just below the
hook saddles, slide the rings over the saddles, lower until the hooks carry the frame, open the hands and withdraw. It
commands only arm and finger targets, never sets an object pose or applies an object force, and it is never copied
into the agent's environment or image. The standard oracle submits the same rows through the public client.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent: the frame touching the floor, leaving the workspace box, tilting more than
0.6 rad, falling 1 cm below its start height after lift-off, falling off a hook after both rings were engaged, unstable
physics (all checked after every 2 ms substep), being held by nothing after lift-off (at the end of any control, or
at any substep while also falling faster than 0.2 m/s), or the 3,000-control budget. The frozen thresholds come from the task, never from an agent archive. A no-op fails. Human
review and full agent-trial calibration remain pending; report this task as provisional.

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
Source: `scripts/dexhand/families/picture_hang/`, generated by `scripts/dexhand/generate.py`. The scene is the
accepted T21 scene-expansion scene "Hang a large picture on two wall hooks" made physical: a frame with the outer size
of an IKEA SANNAHED 50 x 50 cm frame (52 x 52 x 6 cm, the 2.0 kg package weight used as the frame mass), two 35 mm-class
D-rings on passive hinges (damping 0.0004 N m s/rad, friction loss 0.0015 N m, 0 to 1 rad, a 0.005 N m/rad return
spring standing in for the frame back the ring cannot swing through), two ordinary bent-sheet brass hooks
(photo-based dimensions), a console and a wall; the print is Claude Monet, Water Lilies (1906), public domain (CC0).
Frame, rings and hooks are rigid project-authored primitives, not manufacturer CAD. The Sharpa Wave assets are pinned
to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the left Sharpa hand is a declared
mirror image of the right model (positions, rotations, hinge axes, inertial frames and mesh scales reflected), the same
construction as the dual-arm DexHand families, not a separate manufacturer left-hand model. The Wuji Hand 2.2 models
(`hand2/hand2_2`, left and right) are pinned to wuji-technology/wuji-description commit
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same flanges with their vendor joints, actuators
and contact geometry unchanged. The robot is the Tianji Marvin dual-arm stand of the accepted pot_shelf_transfer family (two
7-joint arms, position servos kp 700 N m/rad, kv 48, force limits 108/108/66/66/18/18/18 N m, Tianji meshes pinned in
the image), standing on a 0.10 m plinth in front of the console (which stands on its two rear legs so that the stand's base plate fits
under its front half); each hand sits rigidly on its arm's flange. This is a
simulated bimanual hanging task, not a zero-shot hardware claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
