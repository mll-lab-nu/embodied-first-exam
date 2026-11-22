# embodied-olympics-fun-catch-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-catch-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `catch` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: Both hands are the H1-2's own Inspire five-finger hands at their default forces (20 N per fingertip, 30 N the thumb; no factor); a catch is one hand enclosing the ball (its fingers and its thumb or palm touching it from opposite sides, the two contact directions at least 90 degrees apart), held 1 s. The fly ball is thrown by the two-wheel pitching machine (21.4 m/s at the launch, it lands 1.32 m from the robot untouched). Positive by a declared magic action: real, the robot turns its palm up on stand rows and holds it there; injected once, when the descending ball is below 3 m it is put at rest on that palm; real, the hand closes round it, the catch and the 1 s hold (right and left hands; the same state hash twice). Negatives: nop (the ball lands within 3 m), onto the trunk, touched while still rising, the hand opened after the catch (the ball lies on the open palm: out of the hand), resting on the open palm never closed on (not caught in time), a fall. Stress: random arm targets with the ball in the hand, the ball at most 1.6 mm into the hand. Realtime: physics RTF about 2.1 on the reference workstation (estimated from a same-process comparison on a slower host), above 1.5.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Catch the fly ball: close one of your hands on the baseball before it touches the ground or your body, and keep it there. (Embodied Olympics `catch`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball is in the air for three seconds and comes down at about 17 m/s more than a metre away: the body has to walk there at 0.6 m/s and bring an open hand onto its line, and the fingers need a few tenths of a second to close round it, while a ball that meets the hand at that speed bounces off it in a few milliseconds. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-catch-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A baseball (0.073 m across, 0.145 kg, it flies in air with drag) is thrown by a two-wheel pitching machine 40.0 m in front of you: it leaves the machine's wheels 1.0 m above the ground at about t = 1.0 s, at about 21.35 m/s, about 45.0 degrees above the horizon and 1.18 degrees to the left of the line from the machine to you (it is launched when it has left the wheels), so that untouched it would come down within 3.0 m of where you stand at the start. Both your hands are five-finger hands (a thumb and four fingers, one closure command per hand) that hold things only by contact and friction; they start open. A catch: one hand's fingers and its thumb or palm touch the ball at the same time from opposite sides (the mean directions of the fingers' contacts and of the thumb's and palm's contacts at least 90.0 degrees apart: a ball lying on an open hand is not caught), after the ball has passed the top of its arc and at the latest 0.5 s after it first touched you. Before the catch the ball may touch only your hands and forearms. You succeed when, from the catch, the ball has stayed enclosed in that hand for 1.0 s (apart from breaks of at most 0.02 s) touching nothing but that hand. You fail if the ball touches the ground, or any part of you other than a hand or a forearm, before the catch; if it is touched before it has passed the top of its arc; if it is not caught within 0.5 s of first touching you; if after the catch it is out of the hand for longer than 0.02 s (dropped, slipped out or let go: a ball caught again does not count) or touches anything but the hand that caught it (your other hand, a forearm, your body, the ground); if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground) before the end; or after 9 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | Official Baseball Rules (MLB, 2024 edition): 3.01 (the ball), Definitions of Terms: "catch" (secure possession in the hand before the ball touches the ground, held long enough to show control), "in flight"; deviations: Definitions (catch): no glove; both hands are the H1-2's own Inspire five-finger hands (six self-locking drives; 20 N at each fingertip, 30 N at the thumb; a full close in about 0.8 s), bare. A catch is one hand enclosing the ball: its fingers and its thumb or palm touching the ball at the same time from opposite sides (the mean directions of the two contacts at least 90.0 degrees apart: the hand closed on it, not a ball lying on an open hand), at the latest 0.5 s after the ball first touched you; "held long enough" is 1.0 s in which the ball stays enclosed in that hand (breaks of at most 0.02 s) and touches nothing else, without falling. Nothing is welded: the ball is held only by the fingers' contact and friction and can slip out. · Definitions (catch): a ball that touches the body (any part other than the hands and the forearms) before it is caught is not a catch here (the rule would allow trapping it against the body), and neither is a ball held at the end by anything but the hand that caught it (the other hand, a forearm, the body). · The fly ball is not batted: a two-wheel pitching machine 40.0 m away throws it at about 21.35 m/s, about 45.0 degrees above the horizon, about 1.0 s after the start, with the little spin its wheels give it; where it comes down (within 3.0 m of where you stand) is this instance's draw. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. |
| Stages | catch → hold |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 900 control steps (9 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
