# dexhand-coffee-stir-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-coffee-stir-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `coffee_stir` |
| Oracle | `full` — solution/trajectory.npz replays the validated Sharpa Wave authoring trajectory on the Marvin right arm (1,882 controls; success after 1,802, then 80 unexecuted hold rows of slack). Two fresh-process replays succeed with identical state hashes, and the rows rounded to float32 also succeed. The standard oracle submits the same rows through the public client. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Mix the milk into the coffee: stir it six times with the teaspoon, then lay the spoon on the worktop beside the mug. The 300 g mug (inner radius 50 mm, 100 mm tall, 8 mm floor) stands upright on the stone worktop (top at z = 0.75 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee, milk already poured, fills it to 64 mm above the mug base (z = 0.814 m). The approved source film (a kinematic demonstration without hands) starts with the teaspoon suspended upright above the rim; here the right hand holds the 35 g teaspoon there, upright, bowl down, in a thumb-index pinch near the top of its handle, with the bowl centre about 0.12 m above the mug base just over the rim (the milk is already poured; the film pours it from an offscreen supply). With the Wuji hand selected (no Wuji start grasp exists yet), the spoon instead starts leaning in the mug (bowl on the mug floor, handle on the rim) and the open Wuji hand hangs about 0.25 m above the mug; the stages are the same. Success requires three stages in order. (1) Submerged in hand: the thumb and at least one other finger touch the spoon, and the bowl centre, bowl tip and bowl neck (23 mm either side of the centre along the spoon) are all between 4 mm and 64 mm above the mug base and within 50 mm of the mug axis. (2) Stirred: the bowl centre revolves at least six full turns about the mug's vertical axis (world frame; net signed angle). The angle accumulates only while the stage-1 condition holds and the bowl centre is at least 8 mm from the axis; a step of more than 0.785 rad in one control is ignored, and the count restarts from zero whenever the bowl leaves the coffee before six turns are complete. (3) Laid down: no part of the hand touches the spoon, the spoon touches the worktop and not the mug, its bowl centre and handle end are both at least 0.10 m from the mug axis horizontally, its axis is within 15 degrees of horizontal, and spoon and mug are still (linear speed at most 0.02 m/s, angular speed at most 0.5 rad/s), for 50 consecutive controls (1 s). The episode ends with success at that moment. The coffee is not simulated: it exerts no force, and the mixing is judged only by these bowl revolutions below its surface. The episode ends immediately with failure, checked after every 2 ms physics substep, when the mug tilts more than 10 degrees, slides more than 20 mm or is lifted more than 5 mm; when the spoon touches the floor, or touches the worktop before the six turns are complete; when the spoon touches neither the hand, the mug nor the worktop while its centre of mass falls faster than 0.2 m/s (a dropped spoon cannot be caught again); when the mug touches the floor; when a spoon reference point (bowl centre, tip, neck or handle end) is more than 3 mm below the worktop top or the mug base more than 5 mm below it; when the bowl centre or the handle end leaves the workspace box x in [0, 0.96] m, y in [-0.48, 0.48] m, z in [0.70, 1.60] m; when a fingertip enters the coffee (inside the mug radius below the coffee surface); when an arm link, the stand or the parked left hand touches the mug, the spoon or the worktop; or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The approved source film (kinematic, without hands) starts with the spoon suspended above the rim; here the hand holds
the thin teaspoon (5.4 mm handle) upright above the mug in a light thumb-index pinch near the top of the handle. The arm has no gravity compensation, the spoon hangs like
a pendulum and slowly creeps through a two-finger pinch, and the bowl must circle six full turns inside a 50 mm cavity
below the coffee surface while the hand stays out of the coffee. The spoon then has to be lifted clear of the rim,
carried beside the mug and laid flat on the worktop without dropping it, and released so that it lies still: a light,
easily knocked 300 g mug (10 degree tilt / 20 mm slide limits) and an unforgiving drop rule make every phase count.

## Reference solution
`solution/` replays a recorded physical Sharpa Wave episode on the Marvin right arm (1,882 controls; the replay ends
at success after 1,802, then 80 unexecuted hold rows of slack): the bowl is centred over the mug and dipped 32 mm above
the mug base, the pinch is driven around a 15 mm circle so the hanging spoon stirs (6.7 commanded turns, six counted
revolutions), the spoon is lifted clear of the rim, carried 0.23 m beside the mug, lowered until its bowl rests on the
worktop and turned down about the bowl until it lies flat, the fingers open and slide off the handle, and the hand
withdraws; the 1 s laid-down hold then completes. In standard mode the same float64 rows are submitted through
`rcb_client` in 250-row chunks. The authoring controller that produced the rows
(`scripts/dexhand/families/coffee_stir/tools/demo_arm.py`) computes motor targets from the simulator state only (arm
IK with a joint integral, open-loop pinch circle); it never sets an object pose or applies an object force, and it is
never copied into the agent's environment or image. Only a Sharpa reference exists.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure. Failures are
fail-fast and permanent: mug tilted over 10 degrees, slid over 20 mm or lifted over 5 mm, spoon touching the floor, or
the worktop before the six turns are complete, spoon touching neither hand, mug nor worktop while falling faster than
0.2 m/s (no catch window), an object below the worktop or out of the workspace box, a fingertip in the coffee, an arm
link, the stand or the parked left hand touching the mug, the spoon or the worktop, unstable physics, or the
3,000-control budget. Stirring counts only while the thumb and at least one other finger touch the spoon.
Thresholds come from the frozen task, never from an agent archive. A no-op fails. Human review and full agent-trial
calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-3 integration smoke of the Marvin-arm families (Harbor 0.23, efe:dexhand-0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier 3.40-3.51 GiB with two concurrent replays, standard sim sidecar 2.13-2.65 GiB, agent containers < 0.05 GiB; one fresh replay process 1.75-1.81 GiB max RSS (os.wait4); x1.2 rounded up to a GB, the values of pot_shelf_transfer (the same robot); two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run three or four 1.8 GiB Marvin simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 2.65 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/coffee_stir/`, generated by `scripts/dexhand/generate.py`. Scene: the approved T11
"Mix coffee and milk" scene, including its start (spoon held upright above the mug), its six stirring turns and its
end (spoon laid on the worktop beside the mug) (mug 57/50 mm radii, 100 mm tall, 8 mm floor, rounded U handle; teaspoon with a 24 x 46 mm
pressed bowl and 181.7 mm axial reach; worktop top at z = 0.75 m); the visual meshes are the approved refined T11
presentation geometry (`assets/manifest.json`, sha256-pinned). Contact geometry: mug floor disk, 32 wall boxes and
three handle boxes; spoon shaft capsule (r = 2.7 mm) and two crossed flat bowl slabs. The coffee and milk are a visual
surface only; stirring is measured as revolutions of the bowl about the mug axis below that surface (no fluid drag,
buoyancy or mixing dynamics). The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same
flange with its vendor joints, actuators and contact geometry unchanged. The robot is the Tianji Marvin dual-arm stand
(two 7-joint arms, position servos kp 700 / kv 48, no gravity compensation; Tianji meshes pinned by the image's
`tianji/manifest.json`) at the world origin, its plate on the floor; the left arm is parked. Each hand's start state
(`task.json` `initial_qpos`) is a settled physical contact grasp produced by an authoring run (no weld). This is tool
use with an arm-mounted hand, not a fluid-mixing claim.

### Change Log
- 2026-10-14 (before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
