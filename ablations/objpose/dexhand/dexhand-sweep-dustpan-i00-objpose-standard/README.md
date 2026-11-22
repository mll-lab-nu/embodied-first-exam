# dexhand-sweep-dustpan-i00-standard

| | |
|---|---|
| Benchmark | DexHand |
| Mode | standard (`eai-standard/2.2`) |
| Twin | `dexhand-sweep-dustpan-i00-privileged` |
| Simulator / robot | `mujoco` / `marvin-bimanual-sharpa-wave` |
| Family / instance | `sweep_dustpan` / seed 0 |
| Oracle | `full` — solution/ (trajectory.json + parts) holds the accepted authoring episode's 132,521 Sharpa Wave control rows (2000 Hz, float64) plus 16,000 copies of the last row (8 s hold); replayed in the frozen scene the accepted rows reproduce the accepted run bit for bit and succeed after 132,392 steps in two fresh processes with identical state hashes. |
| Agent time budget | 3600 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350` |

## Task
Sweep all six pieces of debris on the floor into the dustpan and lift the loaded pan. A fixed two-arm robot starts with a broom held in its right hand and a dustpan held in its left hand; the pan's entrance ramp rests on the floor next to six small rigid debris pieces (packaging pieces, bottle caps, a wood chip and a crumpled-paper ball). Push the debris over the ramp with the broom's bristles, then raise the dustpan. Success requires 2000 consecutive physics steps (1.0 s) in which all of these hold: in the dustpan's own frame every collision shape of all six pieces lies over the pan floor (at least 1 mm inside its 460 mm side-to-side width, inside its 262 mm depth, no lower than 1 mm below the top of the floor plate and no higher than 110 mm above the pan origin); all six pieces touch the pan (contact force at least 1 mN); the pan origin is at least 50 mm above the floor; every piece moves slower than 0.03 m/s and rotates slower than 0.8 rad/s; and every piece has been touched by the bristles at some point. The episode ends with that success, or fails immediately and permanently when: a piece leaves the floor work area (world x outside [0.45, 1.00] m, y outside [-0.50, 0.40] m, or its center more than 0.25 m above or 0.01 m below the floor at z = -0.10 m); any part of the robot touches a piece of debris with at least 1 mN (sweep with the broom only); from 1.2 s on, fewer than two collision parts of a tool's own hand press on its handle with at least 0.01 N each, or the handle's grip point has moved more than 25 mm or turned more than 0.25 rad relative to that palm since 1.2 s (dropped or slipping tool); a tool is pressed (more than 0.01 N) by any robot part other than its own hand; the arms, torso or the two hands collide with each other; or the simulation becomes unstable. Five of six pieces, an unlifted pan or a hold shorter than 1 s is not a success. Only the robot's motor targets act; the tools and the debris are free bodies without welds, scripted motion or applied forces. One control row sets every motor target for one 0.5 ms physics step (2000 Hz); an episode has at most 160000 rows (80 s).

## Difficulty
Two arms must cooperate for about a minute of simulated time at a 2000 Hz control: the broom must stay in the right
hand while its passive bristles push six small rigid pieces of different shapes over the pan's entrance ramp, the pan
must stay in the left hand and seated on the floor while debris rolls in, and the loaded pan must then be lifted
without spilling. The predicate is strict: all six pieces, a lifted pan, a one-second stable hold, no robot contact
with the debris, no dropped or slipping tool and no debris outside the work area at any time.

## Reference solution
`solution/` (`trajectory.json` + five `trajectory.partNN.npz` parts below 2 MB, checked by sha256) holds the accepted authoring episode's 132,521 recorded Sharpa Wave motor-target rows
(2000 Hz, float64) produced by an authoring-only inverse-kinematics sweeping controller with dustpan-level feedback
(the controller is not part of the task), followed by 16,000 copies of its last row (an 8 s lifted-pan hold that only
adds margin). The oracle hands these rows in unchanged; the standard oracle submits them as float64 (rows rounded to
float32 already break the grip-rotation bound, so they do not succeed). Replayed in this task's frozen scene
they reproduce the accepted run bit for bit and succeed after 132,392 steps (66.2 s): all six pieces in the lifted pan
(81.8 mm), maximum grip drift 5.7 mm and rotation 0.229 rad, a 1.0 s terminal hold. Both hands are offered.
With Wuji Hand 2.2 the start differs only in the finger joints (`assets/reset_wuji.npz`, formed by closing the Wuji
fingers onto the frozen shafts); holding its targets keeps both tools for the whole 80 s horizon (at least 5
force-bearing contacts per handle, grip drift <= 4.4 mm, rotation <= 0.022 rad). No Wuji success is claimed.

## Verification
The trusted simulator service journals every executed row with the hand it runs (`DEXHAND_HAND`, default `sharpa`),
evaluates the predicate after every 0.5 ms physics step and ends the episode at the first success or failure. That
live episode is the verdict (`final.json`, `graded_by = "live"`): nothing is replayed to grade it (owner, 2026-10-17)
The separate verifier reads only the service's `final.json`: reward 1 requires live success. The
collect hook then renders `replay.mp4` from the recorded rows in one video-only pass, which never changes the
verdict. Missing service evidence is an infrastructure error. Release status: provisional (human review).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 2 | 4 GiB | 1024 | no GPU | 10 GiB |
| `sim` | 2 | 6 GiB | 1024 | no GPU | — |
| verifier (as `main`) | 2 | 4 GiB | no cap | no GPU | 10 GiB |

- GPU: not needed.

## Details

### Notes
Source: the DexHand family of this task.
Scene: the frozen MuJoCo model of the accepted sweeping episode, unchanged except for
tokenized mesh paths and four fixed task cameras (`assets/sweep_sharpa.xml`; every file and mesh is checked against
`assets/manifest.json` and `assets/external_assets.json` at load). Robot: fixed Tianji Marvin dual seven-joint arms
(DexForce embodichain geometry, Apache-2.0; Genesis estimated inertias, MIT; prototype position gains) with two Sharpa
Wave hands (MuJoCo Menagerie `sharpa_wave` at `0059d4335f8156206f63a35662313385f7ad6d74`, Apache-2.0; the left hand is
a documented mirror of the manufacturer right hand). The broom has 54 passive hinged
bristle-bundle capsules; the dustpan has a collision entrance ramp; the debris are rigid shape proxies of packaging
pieces, caps, a wood chip and crumpled paper. Tools start pre-held: no pickup, fine dust, paper deformation or
hardware identification is claimed. The arm and hand meshes are baked into the `efe:dexhand` image.
