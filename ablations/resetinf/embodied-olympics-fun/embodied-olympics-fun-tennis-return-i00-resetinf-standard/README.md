# embodied-olympics-fun-tennis-return-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-tennis-return-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `tennis_return` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: The right hand is the H1-2's own Inspire five-finger hand at its default forces (20 N per fingertip, 30 N the thumb; no factor), the racket across the palm (tennis-serve's grip). With the racket square to the forearm, a parameter search over a backhand's poses, timing and spot found swings that pass the bounced ball within about 5 cm of the strings but none that meets it, so the positive is a declared magic action: real, the machine's 30.3 m/s serve and its bounce and a backhand swing with the racket held by the hand's own drives; injected, after the bounce the ball moved (its velocity kept) onto the strings' path 0.04 s ahead, and after the real hit its velocity set to (15, 1, 7) m/s; it clears the net by 3.2 m and lands at (20.1, 2.2); the racket stays in the hand through the 14.8 m/s impact; the same state hash twice. Negatives: nop (two bounces), the hand opened (the racket leaves the hand at 0.06 s), a volley, the ball onto the robot. Stress: random arm targets on the walking policy: the racket is shaken out of the hand, the handle at most 1.0 mm into the fingers. Realtime: physics RTF about 1.6 on the reference workstation (estimated from a same-process comparison on a slower host), just above 1.5.; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Return the serve: after the tennis ball has bounced once in your service box, hit it with the racket held in your right hand back over the net so that it lands in the singles court on the far side, without letting go of the racket. (Embodied Olympics `tennis-return`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The ball crosses the whole court in about a second and is still moving at more than 15 m/s when it reaches you, so the racket has to be in a path a few centimetres wide at an instant you must predict, and a robot that only walks cannot go far to meet it. The racket is held only by a hand's friction: a hard swing and the ball's impact twist it in the grip, so the face the ball meets is not where the arm put it, and a swing strong enough to return the ball over the net must not fling the racket out of the hand. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-tennis-return-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The court is the ITF singles court: 23.77 m long and 8.23 m wide, measured to the outside of the lines, with a service line 6.4 m from the net on each side. The net stands across the middle, 0.914 m high at its centre and rising in a straight line to 1.07 m at the posts, which stand 0.914 m outside the sidelines. The ball is the ITF ball (radius 0.0335 m, 0.0577 kg, with air drag and spin lift). The racket is a separate body, 0.685 m long and 0.3 kg, balanced 0.33 m from the butt, with a strung surface 0.33 m by 0.25 m and an octagonal handle 0.0335 m across its flats and 0.19 m long; at the start its handle is closed in your right hand (a five-finger hand), which holds it by contact and friction only: it can slip, turn in the hand and fall. The racket is in your hand while its handle touches the hand's fingers and its thumb or palm; it has left your hand when for more than 0.05 s it has not. About 3.0 s after the start a ball machine behind the far baseline serves the ball at 30.0 m/s into your right service box; it is served when it has left the machine's wheels. In order: the ball bounces once on your side; the racket, in your hand, hits it (the strings, the frame or any other part of the racket counts); its centre passes the net's plane from your side to the far side, above the net's top edge or outside a post (it may touch the net or a post on the way); and its first contact with the ground after that is inside the far half of the singles court, the lines included (the point under the ball's centre decides; ground contacts less than 0.02 s apart are one bounce): that is the success. You fail if the racket leaves your hand at any time (dropped, thrown or slipped out of the hand), if the racket touches the ball before its bounce (a volley), if the ball bounces a second time on your side before your hit, if after your hit the ball touches the ground on your side or outside the far court, if the ball touches any part of you (the hand included) at any time after the serve, if the racket touches the ball a second time (contacts less than 0.05 s apart are one hit) or stays on it longer than 0.05 s, if the ball passes the net's plane between the posts below the net's top edge, if any part of you or the racket touches the net or a post, or the ground beyond the net's plane, if you or the racket touch the ball before it is served, if you fall, or after 10 s. A fall is: your pelvis lower than 0.35 m above the ground, or any part of you other than your feet touching the ground; the racket may touch the ground on your side as long as it stays in your hand. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | ITF Rules of Tennis 2024: Rule 1 (the court), Rule 3 and Appendix I (the ball), Rule 4 and Appendix II (the racket), Rule 12 (a ball on a line), Rules 24 and 25 (losing the point, a good return); deviations: Rules 16-21 (the service): the server is a ball machine, not a player: a two-wheel machine on a stand behind the far baseline throws the serve from the server's strike point (2.7 m up) at about 3.0 s; there is no opponent, the attempt ends when your return lands · Rule 4 (the racket held in the hand): the hand is the H1-2's own Inspire five-finger hand (six drives, fingertip forces 20 N, the thumb 30 N), closed by one command; the handle lies across the palm, and the racket is held by the fingers' contact and friction alone, as a hand holds it · Rules 4 and 24 (the ball hit with the racket held in the hand; a thrown racket does not play the ball): "in the hand" is defined by contact: the racket's handle touches the hand's fingers and its thumb or palm; a break of up to 0.05 s (the jolt of an impact or a hard swing) is not a release · Rule 12 (a ball touching a line is in): the ball's footprint is one point, the point under its centre at its first contact with the ground (a real ball's footprint is about 5 cm across) · Rule 24 f (deliberately touching the ball twice, carrying it): intention cannot be judged: racket contacts less than 0.05 s apart are one hit, a later one is a second hit, and a contact longer than 0.05 s is a carry · Rule 1 (the net): the net is 4 panels a side, each a 2 cm thick plate that gives way across the net on a spring and a damper (the stiffness of a cable at 2000.0 N between the posts, an estimate: the rule sets the heights, not the tension; the net 6.0 kg in all) instead of a mesh of cord; each moves as one plate (a real net's mesh gives locally), and a fast ball that meets it comes back at about a tenth of its speed · wind and weather: none; the air is still (sea level, 15 C) |
| Stages | bounce → racket → over the net → in |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 1000 control steps (10 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
