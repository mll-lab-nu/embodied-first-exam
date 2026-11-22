# embodied-olympics-fun-pitch-target-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-pitch-target-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `pitch_target` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: The H1-2's own right Inspire hand at its default forces (20 N per fingertip, 30 N the thumb) holds the baseball against its palm by contact and friction (no weld). Positive by a declared magic action: real stance on the mound with both feet across the pitcher's plate and the hand opening; injected once, 10 ms after it starts to open, the ball moved 0.1 m forwards and up and given 22 m/s at 9.5 deg: released on the plate, it crosses the zone at 0.91 m height, 0.02 m off centre, at 20 m/s (strike); the same state hash twice; a 14.5 m/s lob through the zone is also a strike. Negatives: nop (pitch timer, ball still in the hand), release with no foot on the plate (behind it, in front of it), a bounce, high, wide, the hand opened (the ball drops to the mound), the ball touched after the release, a fall before the call. Stress: random arm targets with the hand closed: the ball drops out, never through the fingers (at most 1.9 mm into them). The clean release (the same rule as javelin): brushes by the right arm in the 0.2 s grace after the release may change the ball's velocity by at most 0.5 m/s in all; an injected blow on the palm (1.8 m/s) fails as 'struck after the release'. An agent's own-motor strike from a model run succeeds under it. Every rule above is judged in the family's own 1 ms substep hook.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Pitch a strike: from the pitcher's plate on the mound, with a foot on the plate, throw the baseball held in your right hand through the strike zone over home plate, on the fly. (Embodied Olympics `pitch-target`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
From 18.44 m the ball needs more than 13 m/s even on a high arc, and the zone is 0.43 m wide: a release direction right to about one degree. The H1-2 has no throwing motion; the speed has to come from the trunk and the whole arm while a foot stays on the plate and the body on the mound, and fingers that open no faster than 260 deg/s have to let the ball go at the right hundredth of a second. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-pitch-target-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The baseball (0.073 m across, 0.145 kg, it flies in air with drag and spin lift) starts held in your right hand, a five-finger hand that holds only by contact and friction: the ball can slip or roll out and drop. You stand on the pitcher's plate (a slab 0.61 m wide and 0.152 m deep, level with the mound's top) on a mound 5.486 m across whose top is 0.254 m above home plate; in front of the plate the mound falls 1 in 12. The front edge of the pitcher's plate is 18.44 m from the back point of home plate; home plate is 0.432 m wide and as deep, so its front edge is that much nearer. The strike zone is the rectangle above home plate's front edge, 0.432 m wide and from 0.46 m to 1.07 m above home plate. The pitch: the release is the moment the ball last touched you, once it has then touched nothing of you for 0.02 s (until then it is still in your hand, wherever it rests on you). There is one release: within 15.0 s of the start, and at that moment at least one of your feet is in contact with the pitcher's plate (it touches the mound and part of its sole is over the plate). After the release no part of you may touch the ball and your right hand may not hold it again (its fingers and its thumb or palm on it), except that your right arm and its hand may still brush it during the first 0.2 s, if those touches change its velocity by at most 0.5 m/s in all (the sum of their contact impulses over its mass: the release must be clean). You succeed when the ball's centre then crosses the plane of the zone inside the zone, before the ball has touched the ground. You fail if no foot is on the plate at the release; if the ball is not released in time; if it touches the ground (the mound included) at any time before home plate, also before the release; if it crosses the plane outside the zone (a ball); if it is held again or touched after the release (but for the grace above); if you fall before the call (your pelvis lower than 0.75 m above home plate's level, or any part of you other than your feet on the ground or the mound); or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | Official Baseball Rules (MLB, 2024 edition): 2.01 and Appendices 1-2 (the pitcher's plate 60 ft 6 in from the back point of home plate, 10 in above it; the mound), 2.02 (home plate), 3.01 (the ball), 5.07(a) (the pivot foot in contact with the plate), 5.07(c) (the 15 s pitch timer), Definitions of Terms: "strike zone", "in flight"; deviations: 3.01 (the ball in the pitcher's hand): the hand is the H1-2's own Inspire five-finger hand (six drives for four fingers and a thumb, fingertip forces 20 N, the thumb 30 N, one closure command for the whole hand); the ball starts held against its palm by the fingers' and thumb's contact and friction only (no seams: no grip-made spin beyond what the fingers' motion gives). The release is the moment the ball last touched you before it had touched nothing of you for 0.02 s. · Definitions (strike zone): there is no batter, so the zone's height is fixed, 0.46 m to 1.07 m above home plate (the hollow of the knee to the midpoint of the torso of a 1.8 m batter). A strike is called when the ball's centre crosses the zone's front plane (home plate's front edge) inside the zone, in flight; the rule's "any part of the ball through any part of the zone" (the plate's whole depth, the ball's edge) is not used: stricter. · 5.07(a): "the pivot foot in contact with the plate" is judged at the release: a foot that touches the mound and whose sole is over the plate; either foot may be the pivot foot. Wind-up and set positions and balks are not judged (no runners). · 5.07(c): the pitch timer runs from the start of the episode: the ball must be released within 15.0 s. · No batter, catcher or umpire: a backstop behind home plate; one pitch (a ball dropped or caught again is no second chance), and a fall before the call ends the attempt as a failure. · Flight: quasi-steady aerodynamics (MuJoCo's ellipsoid fluid model: drag and Magnus lift), still air. · The pitch is the hand's alone: the rule book has no article on the pitcher touching the ball in flight after the release; here the right arm may still brush it during 0.2 s after the release, but those touches may change its velocity by at most 0.5 m/s in all (the sum of their contact impulses over its mass): a harder touch is a second propulsion, and fails the pitch. |
| Stages | release → strike |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
