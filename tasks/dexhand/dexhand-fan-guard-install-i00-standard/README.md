# dexhand-fan-guard-install-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-fan-guard-install-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `fan_guard_install` |
| Oracle | `full` — solution/ replays the recorded Sharpa Wave episode in both modes (2,665 controls; success after 2,485; all four clips start open and are closed by the hand): two fresh-process replays with identical state hashes, float32 rows succeed. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Install the front guard on the desk fan. The unpowered fan stands on the worktop facing the operator (its axis points along world -x); its rear wire guard carries four perimeter U clips at 45, 135, 225 and 315 degrees. All four clips start swung open (hinge angle 1.40 rad); the hand has to close every one of them. A closed lower clip (225 or 315 degrees) forms an open-topped U channel that can carry the guard's rim. The detached front guard (0.369 m wire cage, 185 g, with a raised hub cap at its centre) lies flat on the worktop, dome up. Lift the guard, turn it upright with its dome facing the operator, seat its rim on the rear rim, close all four clips over the two rims (the lower clips may be closed before or after the guard is seated; the upper clips can only lock over a seated guard), and take the hand away. Success requires, in order: (1) the guard seated: guard centre within 5 mm of the fan axis, axial seat error within 2.5 mm and guard axis within 5 degrees of the fan axis; (2) the guard still seated, all four clip hinges in their locked range (hinge angle at most 0.12 rad) and the guard rim inside every clip's U channel (in each clip's frame, with origin at its hinge, x toward the operator along world -x and y radially outward, the guard-rim point nearest that clip lies at x from 6.8 to 9.9 mm for the upper clips and 6.8 to 8.6 mm for the lower clips and y from -4.8 to -2.2 mm, i.e. between the rear rim and the clip's lip and inside its bridge), each upper clip having locked at or after the first control at which the guard was seated; (3) the complete condition with no hand contact on the guard, the clips or the fan, guard speed at most 0.02 m/s and angular speed at most 0.2 rad/s, for 50 consecutive controls (1 s). The episode ends with success at that moment; a guard that is only placed, or clips that are only partly closed, never count. The episode ends immediately with failure, checked after every 2 ms physics substep, when the fan moves more than 3 cm from its start or tilts more than 0.10 rad, when the guard touches the worktop, a table leg or the floor after its centre of mass has been lifted more than 5 cm above its resting height (dropped or set back down), or at the first substep at which the guard touches nothing while its centre of mass falls faster than 0.2 m/s (dropped, even if caught again), when the guard touches the fan's base, stem, neck, motor housing, feet or buttons, when the guard's centre of mass falls below the worktop (z < 0.65 m) or leaves the workspace box x in [0.20, 1.10] m, y in [-0.55, 0.55] m, z in [0.60, 1.40] m, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The clips are rigid U channels on passive hinges held by an elastic over-centre spring (a modelled snap detent); the guard is a rigid wire cage. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
All four perimeter clips start swung open, as in the source scene, and nothing holds the guard on the fan until clips
are closed. With one hand, the two lower clips have to be swung closed first (a fingertip reaches behind each open
clip beside the rim and pushes it past its elastic over-centre point), which turns them into open-topped channels.
The 0.369 m wire guard must then be picked up from flat on the worktop, turned upright with its dome toward the
operator and placed on the fan's rear rim within a 0.65 mm axial window above those two channels, released so that it
hangs by itself, and the two upper clips swung closed over both rims, without pushing the 2.15 kg fan off its feet or
knocking the guard out of its seat; then the hand must leave the installed guard. The predicate checks the seat
(concentric, axial and parallel tolerances), all four clip hinges with the rim inside every clip's channel, the order
of the stages and a released stable hold. A dropped guard or a displaced or tipped fan ends the episode as a failure
at once.

## Reference solution
`solution/` holds a validated Sharpa Wave trajectory (2,665 controls; the replay ends at success after 2,485 controls,
leaving 180 rows of slack): the index fingertip closes the lower clips (225 then 315 degrees), the hand grips the hub
cap, lifts and turns the guard, hangs it in the two lower channels, lets go and closes the upper clips (45 then
135 degrees). Privileged mode re-saves these rows; standard mode submits the same rows as float64 through
`rcb_client` (one row per 50 Hz control, `hold`). It is an open-loop recording: it is deterministic and survives
float32 rounding. It was recorded from a closed-loop authoring controller
(`scripts/dexhand/families/fan_guard_install/tools/author.py`) that computes wrist-stage and finger targets only from
robot kinematics and the simulator state; it never drives an object pose or applies an object force, and it is never
copied into the agent's environment or image.

## Verification
Standard mode. The trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors.
The episode ends at the first success or the first failure.
Failures are fail-fast and permanent: the fan moved by more than 3 cm or tilted by more than 0.10 rad, the guard back
on the worktop, a table leg or the floor after it was lifted, the guard touching nothing while its centre of mass
falls faster than 0.2 m/s (a drop fails at once, even if the guard is caught again), the guard striking the fan base, stem, neck, motor
housing, feet or buttons, the guard below the worktop or outside the workspace box, unstable physics, or the
6,000-control budget. The frozen thresholds come from the task, never from an agent archive. A no-op fails. Human
review and full agent-trial calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 2 GB | 2 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-2 integration smoke (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier <= 0.64 GiB with two concurrent replays, standard sim sidecar <= 0.96 GiB, agent containers < 0.05 GiB; one fresh replay process 0.26-0.39 GiB max RSS (os.wait4); x1.2 rounded up to a GB, raised to the 2 CPU / 2 GB design minimum (an agent's own simulator sessions take about 0.3-0.5 GiB each)
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run more than a dozen 0.3-0.5 GiB simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks <= 0.96 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/fan_guard_install/`, generated by `scripts/dexhand/generate.py`. The scene is
adapted from the scene-expansion T26 desk-fan front-guard scene (an HTF1220-style estimate: cage radius, wire layout,
three-paddle blade meshes, fan body, masses and the four perimeter U clips are kept). All four clips start open, as in the source, and
the hand closes all of them. Modelling choices, stated plainly: the guard's centre badge is enlarged into a 22 mm
raised hub cap (source: a 6 mm badge disc) so a fingertip grip fits in front of the dish wires (the source badge stands
only about 2 mm proud of the inner spoke ends, which an 8 mm fingertip cannot pinch reliably); the clip snap leaf is
represented by an elastic over-centre tendon detent on each clip hinge (a passive spring, not an actuator); the lower
clips' lips sit 1.3 mm deeper than the upper clips' so a guard hung in them cannot tip forward; the dish wires collide
with the hand, the rims, the clips and the table but not with the other cage's dish wires; the plug and cord are
static decoration. The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0). The Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same
wrist stage with its vendor joints, actuators and contact geometry unchanged. This is a rigid-wire, rigid-clip
assembly model on a floating wrist stage, not a model of wire or snap-leaf elasticity or a full-arm claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s, at most the video limit). The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
