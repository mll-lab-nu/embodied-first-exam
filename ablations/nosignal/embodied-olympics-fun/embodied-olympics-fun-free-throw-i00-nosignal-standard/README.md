# embodied-olympics-fun-free-throw-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-free-throw-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `free_throw` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: The H1-2's own Inspire hands at the core's default forces (20 N fingertips, 30 N thumb; grip factor 1), H2-class arms (no weld): the ball starts between the two open hands, the arms pressing the palms on its sides (held 5 s at rest, the ball settling onto the thumbs and the palms' heels; one hand alone cannot hold the 0.24 m ball). Positive by a declared magic action: real hold, real opening of both hands with the arms moving out of the squeeze; injected at that step: the ball moved 0.15 m up and given the 58-degree shot's velocity (about 8 m/s) to the ring; the flight, the ring and the referee are real; the same state hash twice; a bank shot (injected) is also a goal. Negatives: nop (not released within 5 s), the hands opened (the ball drops to the floor), taken back after the release, the ball on the chest, walking onto the line, leaving the semi-circle, beyond the line while the ball drops in (and the same drop from behind the line is a goal), up through the ring from below, a fall. Stress: random arm targets with the ball held: it presses at most 0.4 mm into the hands.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Shoot a free throw: from behind the free-throw line, shoot the basketball you hold in your two hands so that it enters the basket from above. (Embodied Olympics `free-throw`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The 0.62 kg ball has to leave the hands at about 8 m/s on a steep arc to reach a ring 3.05 m high and more than 4 m away, with a margin of a few centimetres in air that slows it; the hands, smaller than the ball, have to push it and open in time, and both have to leave it at the same instant without spinning it off line. The arms' fastest swing gives less than that, and the body only stands by an open-loop stance. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-free-throw-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The official basket: a rigid ring of 0.45 m inner diameter (0.018 m metal), its top edge 3.05 m above the floor, its centre 0.375 m in front of a backboard 1.8 m wide and 1.05 m high whose lower edge is 2.9 m above the floor. The ball is a size-7 basketball (0.239 m across, 0.62 kg, it keeps 0.85 of its speed in a bounce on the floor); it flies in air (drag and spin lift). Your hands are five-finger hands that hold things only by contact and friction: the ball starts in them, between your two open palms, your arms pressing it, and is at your disposal at the start; it can slip out. A hand is its fingers, thumb, palm and wrist; a hand is on the ball while it touches the ball, gaps shorter than 0.03 s included; the ball is in your hands while at least one hand is on it. The release is the moment the ball is no longer in your hands (no hand on it); the ball can be released only once: a ball that slips or drops out of your hands is released too. The free-throw line's edge nearest to you is 4.225 m from the point under the ring's centre; the free-throw semi-circle has a radius of 1.8 m round the middle of that edge. You succeed when, after the release, the ball's centre goes down through the ring's plane inside the ring and on down to one ball diameter below it. You fail if the ball has not been released within 5.0 s; if, before the release, the ball touches any part of you other than your hands; if, before the ball has touched the ring or entered the basket, any part of you touches the floor on or beyond the free-throw line's near edge or outside the semi-circle; if any part of you touches the ball more than 0.05 s after the release (it cannot be taken again); if the ball touches the floor before it is through the ring; if the ball's centre comes up through the ring from below; if you fall before the ball is through (a fall: your pelvis lower than 0.35 m above the floor, or any part of you other than your feet on the floor); or after 12 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | basketball-and-rackets |
| Rule book | FIBA Official Basketball Rules 2024: Art. 2 (court), Art. 3 and the Basketball Equipment appendix (backboard, ring, size-7 ball), Art. 13 (how the ball is played: with the hands), Art. 14 (control: a player holds a live ball), Art. 16 (goal; a ball that passes through the basket from below is a violation), Art. 43 (free throws); deviations: the player's hands: the H1-2's own Inspire hands (five fingers, six drives: four fingers, the thumb's flexion and rotation; the core's fingertip forces, 20 N, the thumb 30 N: twice the device's), closed by one command per hand; they hold the ball by contact and friction only (nothing is welded), a hand smaller than a player's (its span about 0.2 m against the ball's 0.24 m). Any shooting style is allowed; the ball is released when no hand touches it any more. · Art. 13.1.2 (the ball is played with the hands only) is read strictly: until the shot is through, the ball may touch no part of you but your hands (fingers, thumb, palm and wrist); holding it against the trunk, the arms or a leg is not a hold of this task. · Basketball Equipment (basket): the ring is rigid (no pressure release) and the net is only drawn: it does not slow the ball. A goal is judged at the ring: the ball's centre down through the ring's plane and on to one ball diameter below it. · Art. 43.2.3: the ball is at your disposal at the start of the episode; there is no referee, no opponent and no rebound: one throw, and touching the ball after the release ends the attempt. |
| Stages | release → through the ring |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1200 control steps (12 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
