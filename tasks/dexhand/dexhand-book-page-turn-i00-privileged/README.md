# dexhand-book-page-turn-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-book-page-turn-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `book_page_turn` |
| Oracle | `full` — solution/ replays the recorded Sharpa Wave episode on the Marvin arms in both modes (553 rows; success after 453 controls): two fresh-process replays with identical state hashes, float32 rows succeed. No Wuji reference solution. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Turn one page of the board book lying open on the desk in front of the robot. The book shows pages 4 (left) and 5 (right). Turn the next right-hand board, leaf 2 (printed pages 5 and 6), over the spine onto the left stack so that the book shows pages 6 and 7, and take the robot off the book. Every board starts flat on its stack (0.2 mm apart), so the robot has to separate the top board from the board under it itself. Progress is measured by leaf 2's binding hinge angle (joint `leaf_2_binding`: 0 = flat on the right-hand stack, pi = flat on the left-hand stack; it starts at about -0.005 rad, resting on leaf 3). The stages must happen in this order: lifted (angle above 30 degrees), past vertical (above 90 degrees), laid. Laid means, all at the same control: angle above 170 degrees, leaf 2 in physical contact with the left-hand stack (leaf 0, leaf 1 or the left cover), leaf-2 hinge speed at most 0.2 rad/s, every other leaf and both covers within 5 degrees of their start angles, and no contact between the robot (either hand, either arm or the stand) and any part of the book. The laid condition must then hold for 50 consecutive controls (1 s); the episode ends with success at that moment. A partly turned page never counts. The episode ends immediately with failure, checked after every 2 ms physics substep, when the book's spine body moves more than 3 cm or rotates more than 10 degrees from its start pose (book shoved or lifted), when any other leaf moves more than 30 degrees from its start angle (a second page turned), when either cover moves more than 30 degrees (the book closing), when the centre of mass of any book part is more than 2 mm below the desk top (z = 0.78 m), or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, welds, scripted page motion or direct forces on the book. The book is free on the desk: eight rigid 1.2 mm laminated boards and two covers on passive binding hinges with friction and damping and a small vertical binding compliance. The episode allows at most 3000 controls at 50 Hz; reaching that limit without success is a failure.

## Difficulty
Every board lies flat, 0.2 mm above the board under it, so the robot has to separate the top board itself: a
fingertip can lift only that board by pressing lightly on its 1.2 mm fore-edge face and dragging it up, without
touching the board below and without shoving the free book across the desk. The board then has to be carried through
a 180-degree arc around the spine, pushed past vertical and left to settle on the left-hand stack, and the robot must
leave the book alone for a full second. The hands sit on two 7-joint position-servo arms without gravity
compensation, so millimetre fingertip placement needs closed-loop corrections. Any shoved or lifted book, second page
or closing cover ends the episode as a failure at once.

## Reference solution
`solution/` replays the validated Sharpa Wave authoring trajectory on the Marvin arms: 553 rows of motor targets (the
replay ends at success after 453 controls, 9.1 s; the remaining rows are slack). In privileged mode `solve.sh` hands
the rows in as `/app/output/trajectory.npz`; in standard mode it submits the same rows as float64 through
`rcb_client` in 250-row chunks. The left arm places its index fingertip against the left stack's fore-edge as a stop
so the book cannot slide; the right index fingertip presses on leaf 2's fore-edge face just above leaf 3 and the right
hand turns about the binding, so fingertip friction lifts only the top board and carries it past vertical; the left
hand lets go once the board is past vertical, the board settles on the left-hand stack under its binding damping, and
the right hand backs away and parks. There is no Wuji Hand 2.2 reference solution. The authoring controller (`scripts/dexhand/families/book_page_turn/author.py`)
computes robot kinematics and motor targets only; it never drives an object pose or applies an object force, and it
is never copied into the agent's environment or image.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand (`hand` member of the trajectory archive
in privileged mode; the hand of the trusted service episode in standard mode) and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: the book shoved or lifted (spine moved more than 3 cm or rotated more than 10
degrees), a second leaf moved more than 30 degrees, a cover moved more than 30 degrees (book closing), a book part
below the desk top, unstable physics, or the 3,000-control budget. The frozen scene and thresholds come from the task,
never from an agent archive. A no-op fails. Human review and full agent-trial calibration remain pending; report this
task as provisional.

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
Source: `scripts/dexhand/families/book_page_turn/`, generated by `scripts/dexhand/generate.py`, from scene T39 of the
50-scene expansion ("Turn a page in a real board book"), whose film was a kinematic demonstration; this task makes the
page turn physical. Robot: the Tianji Marvin stand with two 7-DoF arms (the
`marvin-bimanual-sharpa-wave` rig shared with `pot_shelf_transfer`, `arm_rig.py`). Sharpa Wave assets: MuJoCo Menagerie
commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0). Wuji Hand 2.2 (`hand2/hand2_2`):
wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702` (MIT), on the same arm flanges with
its vendor joints, actuators and contact geometry unchanged. The book reuses T39's design: a 6 x 6 in board book with eight 1.2 mm laminated boards
(0.7 kg/m^2), two covers, a teal cloth spine wrap and the original sixteen page prints and cover (CC0, see
`assets/ORIGINAL_CONTENT_LICENSE.txt`; the page text is rasterized DejaVu Sans, Bitstream Vera license with
public-domain DejaVu changes; sha256 manifest in `assets/manifest.json`). Each board hangs from one free
spine body on a passive binding hinge (damping 0.006 N m s/rad, friction 0.002 N m) and a small vertical binding
compliance (200 N/m); the covers are glued to the spine (0.5 N m/rad). Contacts use thin boxes with the board
footprint; the 5 mm corner rounding is visual. Every board lies flat, as in the source. The desk (top z = 0.78 m) and
the book keep the T39 source pose in front of the robot stand; the desk's front legs are set back to x = 0.43 m so they
stand clear of the robot's base plate. This is a rigid-board / flexible-binding reduced
model, not a paper continuum, damage or zero-shot claim.

### Change Log
- 2026-10-16 (board 0136, video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
