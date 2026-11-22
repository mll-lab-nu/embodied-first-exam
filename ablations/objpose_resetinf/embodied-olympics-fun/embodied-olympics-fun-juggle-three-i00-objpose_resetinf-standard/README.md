# embodied-olympics-fun-juggle-three-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-juggle-three-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `juggle_three` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: Positive by a declared magic action (both hands the G1's own Dex3-1 at the device's torques, palms up; no weld): the red ball's real lob from the ball machine into the left hand and every catch are real (the hand closes when the ball reaches the palm and holds it between thumb and fingers for 0.05 s); injected: each throw (the opened hand's ball put 0.10 m above and 0.12 m inwards with the velocity of a 0.45 m arc onto the other hand) and a correction 0.15 m above each catching hand (the ball over the palm, its horizontal speed zeroed): ten catches in the cascade's order, the same state hash twice; the hands closing 0.02 s before the ball reaches the palm also make ten, closing earlier lets it bounce off the closed fingers. Negatives: nop (the red ball comes down on the closed left hand and hits the body), the waiting ball pushed in the machine, a low throw that comes back to its own hand, the wrong ball thrown (not caught), a fall. Stress: random arm targets with the balls in the hands: the balls fall out (a ball touched the ground at 0.77 s), nothing more than 9.6 mm into anything. RTF with the two Dex3-1 hands (71 degrees of freedom): 0.41-0.57 on a slower host, about 0.9-1.6 on the workstation (below the 1.5 a realtime twin needs).; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Juggle three balls in a cascade: throw each ball from one hand in an arc to the other, the hands in turn, catching each in the hand, until 10 catches have been made in a row. (Embodied Olympics `juggle-three`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
Each throw has to come down into a palm that is hardly wider than the ball, 0.4 m away, about 0.6 s later, the fingers must close on it within a few hundredths of a second before it bounces off, and the catching hand must have thrown its own ball before: three balls, two hands, never two in one. A throw is the hand opening while the arm moves, and errors add up from throw to throw, because a ball is thrown from wherever it was caught. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-juggle-three-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: Three balls (0.07 m across, 0.13 kg). Both your hands are three-finger hands (a thumb, an index and a middle finger) that hold things only by contact and friction. At the start your forearms point forwards, your palms up; the blue ball is held in your left hand, the yellow ball in your right hand, and the red ball rests in a small ball machine on the ground 1.0 m in front of you: it stands for the second ball of the right hand and is thrown for you at about t = 2.0 s (it is thrown when it has left the machine's wheels), on a lob about 0.4 m above your hand that comes down on where the centre of your left hand's grasp is at the start. Before that it may not be touched (by you or by a ball you hold). A catch: a hand holds a ball between its thumb and its fingers (the ball touches the thumb and the index or middle finger: a ball lying on the palm or on the fingers alone is not caught) for 0.05 s without a break, on a ball that has been thrown by the other hand (the red ball's first throw counts as the right hand's), the hold beginning at the latest 0.15 s after the ball first touched you again. A ball is in a hand from its catch (the blue and the yellow ball from the start) until it has touched nothing of that hand for 0.02 s: its release, at its last contact with the hand; a ball in a hand may touch nothing of you but that hand. A throw: after the release the ball, touching nothing but air, rises at least 0.3 m above the point where it left the hand; only the rise before the ball first touches you again counts. The cascade's order: the catches alternate between the hands, the left hand first, and take the balls in the order red, blue, yellow, red, ... You succeed at the 10th catch. You fail if a ball touches the ground; if a ball in a hand touches any part of you other than that hand (the other hand included); if a ball in flight touches any part of you other than a hand, or still touches the hand that released it later than 0.1 s after the release; if a ball is caught by the hand that released it, or before it has risen 0.3 m; if a ball that has touched a hand again is not held within 0.15 s (it rests on the hand or bounces off it); if a catch is out of the cascade's order (the wrong hand or the wrong ball); if the waiting ball is touched before its launch; if you fall (your pelvis lower than 0.35 m above the ground, or any part of you other than your feet on the ground); or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | throwing-catching-striking |
| Rule book | No rule book: the three-ball cascade as jugglers define and count it (siteswap 3; the International Jugglers' Association counts a run in catches): each ball is thrown from one hand and caught by the other, the hands throw in turn, the balls follow one another in a fixed order; a run ends with a drop; deviations: The hands are the G1's own Dex3-1 three-finger hands (a thumb, an index and a middle finger; 1.37 N m back-driven per finger joint, at the device's torques); nothing is welded. The robot holds one ball per hand, so "two balls in one hand at the start" is modelled: the third ball (the red one) is thrown into the left hand by a small two-wheel ball machine on the ground 1.0 m in front of you at about t = 2.0 s, on a lob about 0.4 m above the hand that comes down on where the left hand's grasp centre is at the start; its first catch counts as a catch of a ball thrown by the right hand. Until it is thrown it may not be touched. · A catch is the catching hand holding the ball between its thumb and its fingers (the ball touching the thumb and the index or middle finger) for 0.05 s without a break, the hold beginning at the latest 0.15 s after the ball first touched you again; a ball is in a hand from its catch until it has touched nothing of that hand for 0.02 s (released, at its last contact: a ball that rattles in the hand is not released), and it may touch nothing of you but that hand. · A throw is a release after which the ball, touching nothing, rises at least 0.3 m above where it left the hand; a hand-to-hand pass is not a throw. So that a ball laid on the other hand and lifted is not one, the rise counts only until the ball first touches you again. · The balls are spheres of a juggling ball's size and mass with a soft bounce; they fly in air (MuJoCo's ellipsoid fluid model: drag, a quasi-steady model), still air. |
| Stages | first catch → half way → ten catches |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
