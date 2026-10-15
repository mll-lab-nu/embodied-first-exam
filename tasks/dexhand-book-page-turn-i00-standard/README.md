# dexhand-book-page-turn-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-book-page-turn-i00-privileged` |
| Simulator / robot | `mujoco` / `sharpa-wave-floating` |
| Family / instance | `book_page_turn` |
| Oracle | `full` — solution/wuji/trajectory.npz is a validated Wuji Hand 2.2 trajectory of this instance (650 controls, motor targets only, physical contact only); the oracle uses it when the run selects wuji (privileged: DEXHAND_HAND=wuji; standard: the sim service's hand), and it replays to success in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Turn one page of the board book lying open on the desk. The book shows pages 4 (left) and 5 (right). Turn the next right-hand board, leaf 2 (printed pages 5 and 6), over the spine onto the left stack so that the book shows pages 6 and 7, and take the hand off the book. Progress is measured by leaf 2's binding hinge angle (joint `leaf_2_binding`: 0 = flat on the right-hand stack, pi = flat on the left-hand stack; it starts at about 0.068 rad because the board rests on its binding springback stop). The stages must happen in this order: lifted (angle above 30 degrees), past vertical (above 90 degrees), laid. Laid means, all at the same control: angle above 170 degrees, leaf 2 in physical contact with the left-hand stack (leaf 0, leaf 1 or the left cover), leaf-2 hinge speed at most 0.2 rad/s, every other leaf and both covers within 5 degrees of their start angles, and no contact between the hand and any part of the book. The laid condition must then hold for 50 consecutive controls (1 s); the episode ends with success at that moment. A partly turned page never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the book's spine body moves more than 3 cm or rotates more than 10 degrees from its start pose (book shoved or lifted), when any other leaf moves more than 30 degrees from its start angle (a second page turned), when either cover moves more than 30 degrees (the book closing), when the centre of mass of any book part is more than 2 mm below the desk top (z = 0.30 m), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, welds, scripted page motion or direct forces on the book. The book is free on the desk: eight rigid 1.2 mm laminated boards and two covers on passive binding hinges with friction and damping and a small vertical binding compliance; the board next to the open spread rests on its binding springback stop 4 degrees above the stack. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
The page is a thin rigid board resting 4 degrees above the stack under it: the hand has to catch its fore-edge
without catching the board below, carry it through a 180-degree arc around the spine, push it past vertical and let it
settle on the left-hand stack, all without shoving the free book. Then the hand must leave the book alone for a full
second. Any shoved or lifted book, second page or closing cover ends the episode as a failure at once.

## Reference solution
`solution/` replays the validated Sharpa Wave authoring trajectory: 650 rows of motor targets (the replay ends at
success after 391 controls, 7.8 s; the remaining rows are slack). In privileged mode `solve.sh` hands the rows in as
`/app/output/trajectory.npz`; in standard mode it submits the same rows as float64 through `rcb_client` in 250-row
chunks. The index fingertip catches the fore-edge of the raised board from below, the hand rotates about the spine
so the fingertip carries the board past vertical, the board settles on the left-hand stack under its binding
damping, and the hand backs away and parks. The authoring controller
(`scripts/dexhand/families/book_page_turn/author.py`) computes robot kinematics and motor targets only; it never drives
an object pose or applies an object force, and it is never copied into the agent's environment or image.

Wuji Hand 2.2: `solution/wuji/trajectory.npz` is a validated Wuji Hand 2.2 trajectory of this instance (650 rows of motor targets, physical contact only). When the sim service runs the Wuji Hand 2.2 (`DEXHAND_HAND=wuji`, `spec()["hand"]`), `solve.sh` submits these rows as float64 instead of the Sharpa Wave rows.

## Verification
standard mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: the book shoved or lifted (spine moved more than 3 cm or rotated more than 10
degrees), a second leaf moved more than 30 degrees, a cover moved more than 30 degrees (book closing), a book part
below the desk top, unstable physics, or the 3,000-control budget. The frozen scene and thresholds come from the task,
never from an agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this
task as provisional.

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
Source: `scripts/dexhand/families/book_page_turn/`, generated by `scripts/dexhand/generate.py`, from scene T39 of the
50-scene expansion ("Turn a page in a real board book"), whose film was a kinematic demonstration; this task makes the
page turn physical. Sharpa Wave assets: MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74`
(Apache-2.0). Wuji Hand 2.2 (`hand2/hand2_2`): wuji-technology/wuji-description commit
`829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), mounted on the same wrist stage with its vendor joints, actuators and
contact geometry unchanged. The book reuses T39's design: a 6 x 6 in board book with eight 1.2 mm laminated boards
(0.7 kg/m^2), two covers, a teal cloth spine wrap and the original sixteen page prints and cover (CC0, see
`assets/ORIGINAL_CONTENT_LICENSE.txt`; the page text is rasterized DejaVu Sans, Bitstream Vera license with
public-domain DejaVu changes; sha256 manifest in `assets/manifest.json`). Each board hangs from one free
spine body on a passive binding hinge (damping 0.006 N m s/rad, friction 0.002 N m) and a small vertical binding
compliance (200 N/m); the covers are glued to the spine (0.5 N m/rad). Contacts use thin boxes with the board
footprint; the 5 mm corner rounding is visual. The board next to the open spread rests on a binding springback stop
at 0.07 rad (4 degrees, a joint limit), as a new board book's stiff binding holds it slightly open; this is what lets a
fingertip catch its fore-edge. This is a rigid-board / flexible-binding reduced model on a floating wrist stage, not a
paper continuum, damage, full-arm or zero-shot claim.

### Change Log
- 2026-10-14 (board 0109, before the first scored run): 20 resets in standard mode (owner; PROTOCOL §4.5, DexToolBench's value). `POST /reset` starts a new episode from the frozen start (the same state hash as a fresh process); only the last episode is graded, a success ends the trial; `reward.json` adds `resets` and `reset_budget`. Before, one trial was one episode.
