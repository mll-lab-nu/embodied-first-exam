# dexhand-envelope-letter-insert-i00-privileged

| | |
|---|---|
| Benchmark | DexHand |
| Mode | privileged |
| Twin | `dexhand-envelope-letter-insert-i00-standard` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `envelope_letter_insert` |
| Oracle | `full` — solution/trajectory.npz: Sharpa Wave rows on the Marvin right arm (2,446 rows; success after 2,346 controls, 100 hold rows of slack), float32-exact. Authored closed loop on the wave-2 wrist stage and followed with the arm by IK (tools/arm_port.py); two fresh-process replays give identical state hashes; no arm, stand or parked-hand contact with the task objects. No Wuji Hand 2.2 reference for the arm rig. |
| Agent time budget | 3600 s; tokens: protocol default (PROTOCOL §5) |
| Base image | `ghcr.io/mll-lab-nu/eai-dexhand:0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Put the folded letter into the envelope. A tri-folded A4 letter (a stiff 99 x 210 x 2 mm card, 5 g) lies flat on the desk at (0.48, -0.14) m; an empty DL wallet envelope (110 x 220 mm, 6 g) lies flat at (0.48, 0.16) m with its open mouth along its +X long edge and the open flap on the desk beyond the mouth. The envelope is a pocket: back and front walls 4 mm apart, permanent 3 mm side seams (narrowing to nothing over the last 10 mm before the mouth) and a 4 mm bottom seam, and a 30 mm elastic mouth lip that starts closed (flush with the front wall, 4 mm above the back wall); a fingertip or the letter can lift it. Both objects are free and move only through contact. Move the letter to the mouth and feed it in through the mouth, then let go. Stages, measured on the letter's four corners (centre plane) in the envelope's own frame (origin at the envelope centre on the desk, x towards the mouth, mouth line x = 55 mm): (1) the letter is at the mouth: both leading corners are at least 10 mm past the mouth line, inside the side seams (|y| <= 107.6 mm) and between the walls (height 1.2 to 4.4 mm) while both trailing corners are still outside the mouth line; (2) the letter is inserted: at most 5 % of its 99 mm length (4.95 mm) is outside the mouth line, all four corners are inside the side seams, in front of the bottom seam (x >= -51.6 mm) and between the walls; (3) released: stage 2 holds with no contact between the hand and the letter or the envelope, and both objects at rest (linear speed <= 0.01 m/s, angular speed <= 0.2 rad/s), for 50 consecutive controls (1 s). Stages count in order; the episode ends with success when the hold completes. The episode ends immediately with failure, checked after every 2 ms physics substep, when the letter or the envelope falls below the desk top (origin z < 0.698 m), touches the floor, is dropped (touches nothing - no hand, desk or envelope - while its centre of mass falls faster than 0.1 m/s), leaves the desk (origin x outside [0.18, 0.78] m, y outside [-0.40, 0.40] m, or z > 1.00 m), when the letter is pressed through an envelope wall, seam or the mouth lip (any point of the letter's mid-plane inside one of them) or interpenetrates the envelope by more than 0.7 mm, when the envelope is pushed more than 5 cm from its start or tilted more than 0.35 rad, when the robot's arm, stand or parked left hand touches the letter or the envelope, or when the physics becomes unstable; later actions cannot undo a failure. Only robot actuator targets are allowed; no object teleports, welds, scripted object motion or object forces. The episode allows at most 6000 controls at 50 Hz; reaching that limit without success is a failure. Simplifications: the folded letter is simulated as one rigid 2 mm card with rounded fold edges (paper bending is not simulated); the envelope is one rigid pocket whose seams are solid walls, whose open flap is a thin wedge on the desk and whose mouth lip is a passive spring hinge; the flap is never sealed. The hand is on the right arm of a dual-arm robot standing at the desk's +x edge; the left arm stays parked.

## Difficulty
The letter is thin, light and flat on the desk, so it cannot simply be grasped: it has to be pressed and slid with the
fingertips, squared to the envelope mouth (the letter is 210 mm wide in a 214 mm cavity: 2 mm lateral clearance per
side) and fed in without ramming the light envelope across the desk. The last part of the letter cannot be reached
from above (the front wall covers it), so the hand has to push the trailing fold edge under the closed mouth lip.
Every corner is checked against the mouth line, the seams and both walls; partial insertion, a letter on top of the
envelope or a hand still touching either object never counts.

## Reference solution
`solution/trajectory.npz` is a Sharpa Wave authoring trajectory on the Marvin arm (2,446 rows; success after 2,346
controls). A closed-loop scripted controller that reads the letter and envelope poses authored the motion on a
six-axis wrist stage; the achieved hand poses were then followed with the right arm by damped-least-squares inverse
kinematics from the measured arm state (plus a joint integral for servo sag), and the executed arm and finger targets
were recorded. The rows are motor targets only; the controller never drives an object pose or applies an object force,
and it is not copied into the agent's environment. No Wuji Hand 2.2 reference trajectory is packaged for the arm
rig (the wave-2 Wuji rows were for the wrist stage); a Wuji run starts from the same arm pose.

## Verification
privileged mode. The verifier rebuilds the frozen scene with the recorded hand and replays only numeric motor targets
twice in fresh processes. Both replays must succeed and have identical final integration state hashes; in standard
mode the replay hash must also equal the live final hash. A replay ends at the first success or the first failure.
Failures are fail-fast and permanent: the letter pressed through an envelope wall, seam or the mouth lip, or
interpenetrating the envelope by more than 0.7 mm, the letter or the envelope below the desk top, touching the floor, dropped
(touching nothing while its centre of mass falls faster than 0.1 m/s) or leaving the desk, the envelope pushed more than 5 cm or tilted more than 0.35 rad, the robot's arm, stand or parked left hand touching the letter or the envelope, unstable physics, or the 6,000-control
budget. A no-op fails. Human review and full agent-trial calibration remain pending; report this task as provisional.

## Compute resources
Minimum allocation for one trial (docs/protocol/README.md §2.9; `[metadata.resources]` in `task.toml`). The agent phase counts every container of the trial at once (the agent's, and in standard modes the simulator sidecar); the verifier phase runs after it.

| | Agent phase | Verifier |
|---|---|---|
| CPU cores | 2 | 2 |
| Memory | 5 GB | 5 GB |
| GPU memory | 0 GB | 0 GB |

- GPU: not needed.
- Measured: wave-3 integration smoke of the Marvin-arm families (Harbor 0.23, eai-dexhand:0.2.0, CPU-only, 2026-10-15; one privileged and one standard Sharpa oracle per family; docker cgroup memory.peak): privileged verifier 3.40-3.51 GiB with two concurrent replays, standard sim sidecar 2.13-2.65 GiB, agent containers < 0.05 GiB; one fresh replay process 1.75-1.81 GiB max RSS (os.wait4); x1.2 rounded up to a GB, the values of pot_shelf_transfer (the same robot); two cores for the two concurrent verifier replays
- Limits in the agent phase (docs/protocol/README.md §2.10; `[metadata.resources.limits]`, shown to the agent in `instruction.md`; always measured and reported, and exceeding one fails the trial only when the run sets `RCB_LIMITS_ENFORCE=1`), every container of the trial: no GPU, 8 GiB memory, 512 processes, 10 GiB of new files under `/app`, `/tmp`, `/root`; 60 s within 120 s. Expected peak of the whole trial: 0 GiB GPU memory, 8 GiB memory. Limits measured: memory: 8 GiB lets an agent run three or four 1.8 GiB Marvin simulator sessions next to its harness; measurements as in the [[rule]]; processes 512 and disk 10 GiB: design defaults, not yet measured.

## Details

### Notes
Source: `scripts/dexhand/families/envelope_letter_insert/`, generated by `scripts/dexhand/generate.py`, from the
approved T38 scene (DL wallet envelope 110 x 220 mm, A4 letter folded in thirds to 99 x 210 mm, writing desk at z =
0.70 m). Physics simplifications: the folded letter is one rigid 2 mm card with rounded fold edges (paper bending is
not simulated); the envelope is one light rigid pocket whose 3 mm side seams and 4 mm bottom seam are solid walls,
whose open flap is a thin wedge on the desk and whose 30 mm mouth lip is a passive elastic hinge that starts closed
(flush with the front wall) as in the source scene's start; the walls are 4 mm apart (the cavity a rigid 2 mm letter
card needs; the source's paper walls are 0.2 mm apart), so the closed mouth admits the letter's rounded leading fold; the side seams narrow to nothing over the last 10 mm before the mouth (wallet-envelope side flaps). The
letterhead texture is the scene's project-original artwork (`assets/letter.png`). The Sharpa Wave assets are pinned to
MuJoCo Menagerie commit `0059d4335f8156206f63a35662313385f7ad6d74` (Apache-2.0); the Wuji Hand 2.2 model
(`hand2/hand2_2`) is pinned to wuji-technology/wuji-description commit `829c9aa27cb12c3a49d5b8d63c9869dd8f656702`
(MIT) with its vendor joints, actuators and contact geometry unchanged. The robot is a fixed Tianji Marvin stand with
two seven-joint arms (base at (1.15, -0.25, 0.10) m, facing -x, its plate on the floor beyond the desk's +x legs); the hand is on the right flange,
the left arm is parked. The arm model is the frozen pot_shelf_transfer Marvin (`arm_rig.py`).

### Change Log
- 2026-10-16 (board 0136, video only): the verifier renders the replay video (`/logs/verifier/replay.mp4`) with a third fresh replay after `reward.json` is written, in its remaining time. Before, the privileged verifier rendered no video. The video films at most 300 steps (a longer episode at a larger stride; an OSMesa frame of an arm scene takes up to ~3.6 s on two cores), and the video, verifier and collect limits cover the longest archive the row limit allows. The verdict, the replays and `reward.json` are unchanged.
