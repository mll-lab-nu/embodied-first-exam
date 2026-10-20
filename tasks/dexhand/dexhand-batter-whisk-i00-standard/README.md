# dexhand-batter-whisk-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-batter-whisk-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `batter_whisk` |
| Oracle | `full` — solution/ replays the validated Sharpa Wave authoring trajectory on the Marvin arm rig (1,971 controls; the replay ends at success after 1,871 controls) in both modes; it succeeds in two fresh processes with identical state hashes, also with float32-rounded rows. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Pick up the balloon whisk, whisk the batter in the steel bowl, drain the whisk over the bowl and lay it down on the counter. The whisk starts at rest, leaning on the bowl rim with its handle end on the counter (where it settles when released from the source scene's start pose, standing in the bowl); both hands start open. The batter is not simulated: whisking is measured on the whisk-head point, 20 mm above the wire tip on the whisk axis, which is in the batter while it is between 3 mm above the bowl origin and the batter surface (35.7 mm above the bowl origin) and at least 4 mm inside the bowl wall. Complete five stages in order. (1) Picked up: a hand holds the whisk clear of everything else, i.e. the robot touches it, it touches neither the counter nor the bowl and its lowest point is at least 30 mm above the counter top, for 10 consecutive controls. (2) Immersed: the head point enters the batter. (3) Whisked: the head point circles the bowl axis by at least 5 full revolutions of net (signed, unwrapped) angle while it stays in the batter; leaving the batter before 5 revolutions resets the count to zero, and controls with the head point closer than 8 mm to the bowl axis add nothing. (4) Drained: while the robot touches the whisk, the wire tip is at least 10 mm above the bowl rim, the head point is within 55 mm of the bowl axis (over the opening) and the whisk hangs head-down within 30 degrees of vertical, for 25 consecutive controls (0.5 s). (5) Set down: lower the whisk until it touches the counter top while the robot still touches it (it is then placed), then let go; the episode succeeds when, for 50 consecutive controls (1 s), the whisk touches the counter top, touches neither the robot nor the bowl, lies within 30 degrees of horizontal with its centre of mass at least 120 mm from the bowl axis, and its centre of mass moves slower than 0.02 m/s and it turns slower than 0.3 rad/s. The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every control, when: the bowl tilts more than 10 degrees, slides more than 30 mm or rises more than 20 mm from its start; after the pickup, the whisk touches nothing, its lowest point is more than 2 mm above the counter top and its centre of mass moves downward faster than 0.2 m/s (dropped); after the pickup and before it is placed, the whisk touches the counter or is out of robot contact for more than 10 consecutive controls (dropped); after it is placed, the whisk touches neither the robot nor the counter for more than 5 consecutive controls (tossed); the bowl or the whisk touches the floor, has its centre of mass below the counter top (z < 0.68 m) or outside the workspace x in [0.25, 0.99] m, y in [-0.36, 0.36] m, z in [0.60, 1.50] m; or the physics becomes unstable. Before the pickup the whisk may be nudged or slide off the rim; the counter, floor and workspace rules still apply. Later actions cannot undo a failure. "Robot" means any hand, arm link or the stand. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct forces. The episode allows at most 4000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The whisk is not in a hand at the start: it leans on the bowl rim with its handle end on the counter, so a careless
grasp drags the free bowl (a 30 mm slide or 10 degree tilt fails). The robot is a two-arm Tianji Marvin with no gravity
compensation, so every hand pose comes from arm joint targets. The whisk must be picked up, turned upright and moved
through the batter in circles without striking the bowl wall, lifted clear to drain, turned from vertical to lying,
placed on the counter while still held and let go so that it comes to rest beside the bowl. Dropping the whisk after
the pickup, knocking the bowl or releasing the whisk in the air ends the episode as a failure at once.

## Reference solution
`solution/` replays the validated Sharpa Wave authoring trajectory on the Marvin rig (a closed-loop scripted
two-arm controller recorded as open-loop rows: the left hand hooks its fingertips over the near-left bowl rim and
steadies the bowl while the right hand closes a palm-down grasp on the whisk handle and lifts it off the rim; the left
hand lets go and withdraws; the right hand turns the whisk upright beside the bowl, lowers it into the batter, orbits
the bowl axis until five revolutions are counted, lifts and drains, carries and lays the whisk on the counter, opens
and withdraws). The authoring tools (`tools/author_arm.py`, `tools/armlib.py`, `tools/make_reset_arm.py`, damped
least-squares IK of the shared arm rig) read simulator state and write motor targets only; they never drive an object
pose or apply an object force, and they are never copied into the agent's environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent: bowl tipped, moved or lifted; whisk dropped after the pickup (touching nothing
while falling faster than 0.2 m/s more than 2 mm above the counter, counter contact or no robot contact before it was
placed, or neither robot nor counter contact for more than 5 controls after it was placed); bowl or whisk on the floor, below the counter top or outside the workspace; unstable physics;
or the 4,000-control budget. The frozen thresholds come from the task, never from an agent archive. A no-op fails.
Human review and full agent-trial calibration remain pending; report this task as provisional.

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
Source: `scripts/dexhand/families/batter_whisk/`, generated by `scripts/dexhand/generate.py`, from the T49 scene
"Hold a bowl and whisk batter" (scene expansion). The Roesle 150672 bowl and Roesle 950633 balloon whisk keep the
source geometry, masses and original authored meshes (`assets/manifest.json`, sha256); contact uses convex proxies
of the same profile. The 252 g batter charge is not simulated as a fluid: its mass is lumped rigidly into the bowl and
whisking is summarised by whisk-head revolutions inside the batter volume (no drag, no mixing field). The source
starts with the whisk standing in the bowl; without a hand that pose is not statically stable (the handle side is
heavier), so the start is the state in which the whisk settles when released from it: leaning on the rim, handle end on
the counter. The source's second hand holding the bowl is available (left arm) and the reference solution uses it to
steady the bowl during the pickup; it lets go before whisking because fingers hooked over the rim of this 12 cm bowl
would sit inside the whisking volume. The robot is the Tianji Marvin stand of `pot_shelf_transfer` (two 7-DoF arms,
position servos, no gravity compensation) at the world origin facing +x, with a hand on each flange (`arm_rig.py`).
The Sharpa Wave assets are pinned to MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0);
the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same flanges with its vendor joints, actuators and
contact geometry unchanged. This is a physical tool-use task for an arm-mounted dexterous hand, not a zero-shot claim.

### Change Log
- 2026-10-14 (before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
