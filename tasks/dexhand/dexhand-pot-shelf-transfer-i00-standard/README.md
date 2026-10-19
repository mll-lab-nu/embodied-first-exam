# dexhand-pot-shelf-transfer-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-pot-shelf-transfer-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `pot_shelf_transfer` |
| Oracle | `full` — solution/trajectory.npz: the 8,850 authoring rows of the accepted episode (bit-for-bit replay of the recorded states, tools/verify_oracle.py). Harbor 0.23 oracle reward 1 in both modes on 2026-10-14 (two fresh-process replays with identical state hashes; standard: live = replay). solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (8,266 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
A fixed dual-arm robot (two 7-joint arms, a dexterous hand on each wrist) stands at a kitchen worktop. A freely moving 1 kg two-handle stockpot (286 mm vessel diameter, 438 mm across its two loop handles) rests on the worktop; an open kitchen shelf is to the robot's left. Grasp the pot by its two handles, lift it with both hands, carry it into the shelf compartment and set it down upright on the shelf board at the target, then open both hands and withdraw them. The pot must never be dropped, tipped over, knocked against the furniture, the floor or a non-hand robot link, or leave its support while no hand carries it. Only the robot's position-controlled joint targets act on the world: there are no attachments, object actuators, scripted object motion or applied forces.

Mode `standard`. A fixed Tianji Marvin dual-arm stand (two 7-joint arms) carries a dexterous hand on each wrist:
Sharpa Wave by default (58 targets per row), Wuji Hand 2.2 selectable (54 targets per row). One row is one 2 ms
physics step (500 Hz). The pot is a free 1 kg rigid body; only the robot's position servos act on the world.

## Difficulty
Hard. Both hands must hook the two thin (14 mm) loop handles of a 438 mm wide pot, lift it clear of the worktop, keep
it level while the two arms carry it 0.36 m sideways and 0.04 m up into an open shelf compartment, set it down at a
4 cm target, then release and withdraw without dragging it. The arm servos have no gravity compensation, the episode
fails on the first drop, tip, collision or furniture contact, and the 2 s released hold must be reached within 60 s
of simulated time.

## Reference solution
`solution/trajectory.npz` holds an authoring controller's 8,850 Sharpa rows (17.7 s at 500 Hz): supported approach,
both-handle grasp, loaded lift, levelling, carry into the compartment, placement, release and withdrawal. The
episode reaches the 2 s released hold at row 8,602, where it ends. The rows are replayed bit for bit by the packaged
scene (every physics state equals the authoring recording). Privileged: `solve.sh` re-saves the rows as the
deliverable. Standard: `solve.sh` submits them through the client with `dt = 0.002 s`. The solution is never copied
into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (8,266 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
Privileged: the isolated verifier rebuilds the frozen scene with the trajectory's `hand` (default `sharpa`) and replays
only the `actions` rows twice in fresh processes; reward 1 iff both replays succeed with identical final state hashes.
Standard: the trusted sim service judges the episode it ran (the last one after resets) with the task's predicate and
the selected hand, after the agent's container is stopped; its record (`final.json`, `graded_by = "live"`) is the
verdict, and nothing is replayed to grade it. The isolated verifier reads only the service's artifacts. The
service then renders `replay.mp4` from the recorded trajectory in one video-only pass, which never changes the
verdict. A missing or unfinished record, a give-up after crashes between the agent's calls and a frozen instance
that does not build at the episode's start are infrastructure errors. Rows of the wrong width for the recorded
hand, non-finite or out-of-range targets, a wrong `task` or `actuator_names` label and oversized archives are rejected
(reward 0, `bad_trajectory = 1`). The predicate is evaluated after every physics step from simulator state only
(contacts, contact forces, poses, velocities, geometric distances): two ordered stages (bimanual carry, released hold
on the shelf) and fail-fast invariants (drop, fall, tip, collision, furniture contact, penetration, joint overshoot,
unstable physics, step budget); nothing else fails early, so setting the pot back down on the worktop and regrasping
it is allowed. Partial completion fails. A `nop` agent scores 0 (no archive; in standard mode the
untouched pot never leaves the worktop).

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 4 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: pot_shelf_transfer oracle/nop trials (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-14; rcb_monitor samples every 5 s for the agent container, docker cgroup memory.peak for the others): privileged verifier 3.68 GiB with two concurrent replays (3.92 GiB for two Wuji replays), standard sim sidecar 2.25-2.53 GiB, agent containers < 0.06 GiB; sweep_dustpan: one oracle replay 1.93 GiB max RSS (os.wait4, 599 s), standard sim sidecar 2.20 GiB (docker stats); x1.2 rounded up to a GB; two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), the agent's container: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 16 GiB memory. Limits measured: memory: 8 GiB lets an agent run about twenty 0.3 GiB simulator sessions (pot/sweep: three or four 2 GiB sessions) next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured; whole trial: + the sim service's 8 GiB cap (peaks 0.65 GiB, dual-arm 2.53 GiB).

## Details

### Notes
Source: `scripts/dexhand/families/pot_shelf_transfer/`, generated by `scripts/dexhand/generate.py`. The frozen MJCF is
the manager-accepted scene-expansion model of this task (two-handle stockpot to shelf); `tools/freeze.py` rewrites
only its mesh paths and appends three static cameras, and `tools/verify_oracle.py` proves the 8,850 authoring rows
replay to the accepted initial and final integration-state digests with every recorded qpos/qvel equal.

Assets: the pot is "Harvest Pot - Cookware" by Innerscene (CC0 1.0) at source scale, lid omitted; it is one 1 kg rigid
body (0.8 kg vessel + 0.2 kg dry payload), each hollow loop handle collides as 24 capsule chords, the vessel as 32 wall
boxes plus the source base mesh. Tianji Marvin arm geometry from DexForce's TianjiMarvin release (Apache-2.0) with
Genesis public inertia estimates (MIT); Sharpa Wave from MuJoCo Menagerie `0059d4335f8156206f63a35662313385f7ad6d74`
(Apache-2.0; the left hand is a declared mirror of the right model); Wuji Hand 2.2 from wuji-description
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT). Every mesh is checked against `assets/manifest.json` (sha256) before
the scene compiles; the arm and hand meshes come from the `eai-dexhand` image, the pot meshes from the task.

Modelling scope: estimated mass, inertia and contact compliance, no fluid, heat or deformation, internal hand
self-contact is not judged. Open kitchen shelf, not a narrow-cupboard challenge. The pot's 438 mm handles span the
board's depth direction, so at the target the front handle reaches about 32 mm past the board's open front edge; the
compartment test therefore admits at most 50 mm of overhang at the open front (all other faces are strict). Wuji Hand
2.2 composes on the same arm mounts with neutral fingers.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
- 2026-10-16 (board 0136, video only): the collect hook renders the replay video in its remaining time (timeout_sec minus 60 s) instead of a fixed 300 s, which cut the video of episodes longer than ~10k steps. The verdict, the replays and `reward.json` are unchanged; earlier results stay valid.
- 2026-10-17 (owner, board 0150/0151): standard mode graded by the live episode; no grading replay; video by one render pass from the trajectory after the verdict. `success` is the sim service's own verdict on the episode it ran (the same predicate a replay recomputed: the same rows through the same step, a success ending the episode); the collect hook no longer replays it twice in fresh processes, and `final.json` / `reward.json` drop `replay_success`, `deterministic` and `live_matches_replay` (`graded_by = "live"`, `replays = 0`). The service checks the frozen instance's files against the generator's record when an episode begins (`instance_mismatch`, an infrastructure error). A collect hook on `main` (`kill -9 -1`) stops whatever the agent left running before the service ends the episode. The agent's side (the instruction's grading sentence aside), the scene and the predicate are unchanged.
