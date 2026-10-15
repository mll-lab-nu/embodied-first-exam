# dexhand-coffee-stir-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-coffee-stir-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `coffee_stir` |
| Oracle | `full` |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Mix the milk into the coffee: stir the coffee with the teaspoon, then leave the spoon resting in the mug. The 300 g mug (inner radius 50 mm, 100 mm tall, 8 mm floor) stands upright on the stone worktop (top at z = 0.75 m) with its axis at x = 0.48 m, y = 0.015 m; the coffee, milk already poured, fills it to 64 mm above the mug base (z = 0.814 m). The coffee is not simulated as a fluid: mixing is measured as stirring. The 35 g stainless teaspoon (181.7 mm long, 24 x 46 mm bowl) starts leaning in the mug with its bowl on the mug floor and its handle on the rim. Three stages must be completed in order. (1) In the coffee: while the spoon is in the hand (the thumb and at least one other finger touch it), the bowl is submerged, i.e. the bowl centre and both bowl ends (23 mm either side of the centre along the spoon axis) lie below the coffee surface and above the mug floor (mug frame z between 0.004 and 0.064 m) and within 50 mm of the mug axis. (2) Stir: while the bowl stays submerged, at least 8 mm from the mug axis, and the spoon is in the hand (thumb and at least one other finger touching it; a single finger pushing the spoon does not count), the unwrapped angle of the bowl centre about the mug's vertical axis (world frame) must accumulate three full revolutions (1080 degrees net in one direction). Increments larger than 45 degrees per control are not counted, and the count restarts from zero whenever the bowl leaves the coffee before the three revolutions are complete. (3) Rest: the spoon is released (no hand contact) with its bowl still submerged in the mug, the spoon touching the mug, spoon and mug linear speeds at most 0.02 m/s and angular speeds at most 0.5 rad/s, continuously for 50 controls (1 s). The episode ends with success at that moment; partial completion never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the mug tilts more than 10 degrees, slides more than 20 mm horizontally from its start or is lifted more than 5 mm above its start height; when the spoon touches the worktop or the floor (dropped or carried out of the mug) or the mug touches the floor; when the spoon touches neither the hand nor the mug while its centre of mass falls faster than 0.2 m/s (a dropped spoon fails at that physics substep; there is no window to catch it again); when a spoon reference point (bowl centre, bowl ends, handle end) falls below the worktop top or the mug base falls below it; when the bowl centre or handle end leaves the workspace box x in [0, 0.96] m, y in [-0.48, 0.48] m, z in [0.70, 1.60] m; when a fingertip enters the coffee (inside the mug radius and below the coffee surface); or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, grasp welds, scripted object motion or direct object forces. The episode allows at most 3000 controls at 50 Hz (60 s); reaching that limit without success is a failure.

## Difficulty
The teaspoon is thin (5.4 mm handle) and starts leaning in the mug, so it has to be picked up with a precise pinch
and then driven like a pendulum or held stiffly enough that its bowl circles inside a 50 mm cavity under the coffee
surface. Three full revolutions are counted only while the bowl stays submerged and the hand touches the spoon; the
spoon then has to be set down in the mug and released without knocking the 300 g mug (10 degree tilt / 20 mm slide
limits) or dropping the spoon onto the worktop.

## Reference solution
`solution/` replays a recorded physical Sharpa Wave episode (1,265 controls; the replay ends at success after 1,165):
a thumb-index pinch near the top of the leaning teaspoon, the spoon raised upright with its bowl 37 mm above the mug
base, the pinch driven around an 18 mm circle so the hanging spoon stirs (five commanded turns, three counted
revolutions), the bowl lowered to the mug floor, the spoon leaned toward the rim, released, and the hand withdrawn;
the 1 s rest hold then completes. In standard mode the same float64 rows are submitted through `rcb_client` in
250-row chunks. The authoring controller that produced the rows (`scripts/dexhand/families/coffee_stir/tools/demo.py`)
computes motor targets from the simulator state only; it never sets an object pose or applies an object force, and it
is never copied into the agent's environment or image. Only a Sharpa reference exists: with Wuji selected, the
privileged oracle hands in the Sharpa rows (graded as a Sharpa episode) and the standard oracle stops at the hand check.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final state hashes; in standard mode the replay
hash must also equal the live final hash. A replay ends at the first success or the first failure. Failures are
fail-fast and permanent: mug tilted over 10 degrees, slid over 20 mm or lifted over 5 mm, spoon touching the worktop
or floor, spoon touching neither hand nor mug while falling faster than 0.2 m/s (no catch window), an object below the
worktop or out of the workspace box, a fingertip in the coffee, unstable physics, or the 3,000-control budget.
Stirring counts only while the thumb and at least one other finger touch the spoon.
Thresholds come from the frozen task, never from an agent archive. A no-op fails. Human review and full agent-trial
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
Source: `scripts/dexhand/families/coffee_stir/`, generated by `scripts/dexhand/generate.py`. Scene: the approved T11
"Mix coffee and milk" scene (mug 57/50 mm radii, 100 mm tall, 8 mm floor, rounded U handle; teaspoon with a 24 x 46 mm
pressed bowl and 181.7 mm axial reach; worktop top at z = 0.75 m); the visual meshes are the approved refined T11
presentation geometry (`assets/manifest.json`, sha256-pinned). Contact geometry: mug floor disk, 32 wall boxes and
three handle boxes; spoon shaft capsule (r = 2.7 mm) and two crossed flat bowl slabs. The coffee and milk are a visual
surface only; stirring is measured as revolutions of the bowl about the mug axis below that surface (no fluid drag,
buoyancy or mixing dynamics). The Sharpa Wave assets are pinned to MuJoCo Menagerie commit
`0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model (`hand2/hand2_2`) is pinned to
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT) and mounted on the same wrist
stage with its vendor joints, actuators and contact geometry unchanged. This is tool use on a floating wrist stage, not
a full-arm or fluid-mixing claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
