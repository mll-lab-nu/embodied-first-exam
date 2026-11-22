# embodied-olympics-fun-high-bar-swing-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-high-bar-swing-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `high_bar_swing` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by a declared magic action (the G1 on a 1.1 m block behind the bar; its own Dex3-1 hands, drives 5 times the device's, declared: the one exception to the benchmark's 2x cap; no weld): the jump is one injected velocity (a 0.18 m rise), the hands close 0.12 s before the top and catch the bar, then an injected spin as from 60 deg and a gravity-like drive of at most 400 N m about the bar (no joint loaded by it): a full extended circle in 4.95 s, bottom load up to 8.6 body weights in 10 ms samples, all held by the hands' own drives; the same state hash twice. The grip-force need, the same magic action: 4 and 4.5 times let go, 5 and 6 times hold, forwards and backwards; capacity of the two hands on the bar: about 1 body weight at the device's torques (the catch tears them off), 1.55 at 1.5 times, 2.05 at 2 times. Negatives: nop (time), no catch (hands open: the mats), holding the bar without a jump, the hands opened (let go), a fall from the block (the mats), a tucked circle and a circle that turns back (referee-only rotations: no count). Stress: random joint targets on the bar then the hands opened: let go; the finger links press at most 3.3 mm into the bar.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Standing on the block behind the high bar, jump up and catch the bar with both hands, then do one giant swing: take your extended body in a full circle around the bar, without letting go. (Embodied Olympics `high-bar-swing`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A real jump: the legs must lift the whole robot about 0.15 m and forwards so that the bar enters the open hands, and the fingers must close round it in flight. Then nothing pushes you: the swing has to be pumped up from a hang by the legs, the waist and the shoulders, against motors of 88 N m at the hips and 25 N m in the arms, until the body goes over the top of the bar extended; the bottom of a giant swing pulls about four times your weight through the fingers and the arms, and the hands slide round the fixed bar against their own friction. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-high-bar-swing-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The bar is a competition horizontal bar: 0.028 m thick, 2.8 m above the floor, 2.4 m long between its two uprights, along the y axis; it is fixed and does not turn. Your hands are three-finger hands (a thumb, an index and a middle finger; each hand's drives 5.0 times the stock hand's torques); they hold the bar by their fingers' contact and friction only, so the bar can be torn out of a hand. A hand grasps the bar while the bar touches its index or middle finger and its thumb or palm; a hand is on the bar while the bar touches any part of it (fingers, thumb or palm: a hook grip counts). You start standing on the block and must jump to the bar: the catch is the moment both hands grasp the bar after you have left the block (grasping it before leaving the block fails). Before the catch you fail if you touch the mats or the floor; you may land back on the block and jump again. After the catch, when for more than 0.05 s a hand has not been on the bar you have let go (whether you opened the hand or the bar was torn out), and there is no regrip; only the hands may touch the bar; touching the block, the uprights, the mats or the floor fails. Your swing angle is the angle between straight down and the line from the bar to your centre of mass, seen from the side. The giant swing is a full circle of that line after the catch: the angle must travel 360.0 degrees in one direction (forwards or backwards) without turning back; a turn back of more than 5.0 degrees starts the count again from where you turned. The body must be extended over the top: whenever your centre of mass is higher than the bar it must be at least 0.59 m from the midpoint of your two wrists (nine tenths of the dead hang's: a slight pike or arch passes, a tuck or bent arms do not); if it comes closer there, the count starts again from that point. You succeed the moment the count reaches 360.0 degrees. Below the bar you may bend as you like to build up the swing. You fail after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 10 GiB |
| `sim` | 4 | 5 GiB | 1024 | no GPU | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | parkour-apparatus-balance |
| Rule book | FIG Apparatus Norms, men's artistic gymnastics, horizontal bar: the bar 2.80 m above the floor (2.60 m above the 0.20 m landing mats), 2.40 m between the uprights, 28 mm in diameter, fixed in the uprights; FIG Code of Points (men's artistic gymnastics), horizontal bar: the giant swing (a full circle round the bar with the body extended, in hang); deviations: the grip (the hands on the bar): each hand is the G1's own Dex3-1 three-finger hand (thumb 3 joints, index and middle 2 each, one motor per joint), closed round the bar; it holds the bar by its fingers' contact and friction alone, nothing is welded, and the bar can be torn out of the hand; the bar is fixed, as the norm's is, and a hand turns on it only by sliding round it or by the wrist's joints · the grip force: the hands' drives are 5.0 times the Dex3-1's (closing 0.49 N m, back-driven 1.37 N m per finger joint; the thumb's rotation 0.86 / 3.1 N m), because with the device's torques the two hands hold about one body weight on the bar (measured: torn off by the catch itself; 1.5 times: 1.55, 2 times: 2.05 body weights) while the bottom of a giant swing pulls about four or more (up to 8.6 in 10 ms here; gymnasts 3.5 to 3.7, Kopp & Reid 1980); in a giant swing in this venue 4.5 times the device's lets go and 5.0 times holds, forwards and backwards (measured). No Unitree hand is this strong · the grip (the hands stay on the bar): defined by contact: the catch is both hands grasping the bar (the bar touching each hand's index or middle finger and its thumb or palm); after it a hand is on the bar while the bar touches any part of it (a hook grip counts), and a break of up to 0.05 s (contacts flickering under a load) is not letting go · the mount: the robot (1.32 m) starts standing on a 1.1 m mounting block behind the bar and jumps to it (a rise of about 0.15 m), because it cannot reach a 2.80 m bar from the mats (a gymnast is lifted to the bar or jumps from a springboard) · FIG Code of Points (the body extended, judged by eye): the extension is measured from the wrists: whenever the centre of mass is above the bar it must be at least 0.59 m from the midpoint of the wrists (nine tenths of the dead hang's), because the referee has positions, not a judge's eye, and the hands may fold at the wrists on the fixed bar · FIG Apparatus Norms, horizontal bar (elasticity): the bar is rigid, not the norm's elastic steel bar on tensioned cables, because the simulator has rigid bodies only (the real bar's spring helps the gymnast: this is not easier) · FIG Code of Points (a routine is scored): one element is judged pass or fail, because the task is a single action |
| Stages | jumped → caught the bar → over the top → full circle |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
