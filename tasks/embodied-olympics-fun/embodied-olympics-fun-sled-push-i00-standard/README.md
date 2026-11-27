# embodied-olympics-fun-sled-push-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/3.0`) |
| Twin | `embodied-olympics-fun-sled-push-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-h1-2` |
| Family / instance | `sled_push` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by a declared injection on top of a real controller (the walking policy pushing with inverse-kinematics palm pads on the 1.04 m poles, plus an external force on the sled along its heading at the two handles, only while both palm pads are on their handles, topping its speed up towards 0.35 m/s, at most 30 N): the sled is wholly over the line at 58.0 s of 60 with 264 N s injected over 22.7 s (11.7 N on average); it is marginal (0.30 or 0.45 m/s, or a 50 N cap, fail: the sled leaves the lane or touches the body); negatives: nop, a body push, a palm on the deck, out of the lane, a fall. The controller alone moves the 5 kg sled (about 22 N to start on turf at friction 0.45) at most 9.8 m of the 12.5 m in 60 s: the palms press the poles partly downwards (about 15 N), which adds turf friction, and the sled drifts out of the lane in most of the 25 settings tried; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Push the sled by its handles along your lane until all of it is over the line ahead. (Embodied Olympics `sled-push`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The sled weighs 5.0 kg on high-friction turf: keeping it moving takes a steady push of about 22 N, against which the walking policy (trained for walking, not pushing) has to keep its balance on 67 kg. Bare palms can only push: if the sled drifts sideways or the hands slip off a handle, nothing holds it. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-sled-push-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: A prowler-type push sled stands on the turf in front of you, its two upright handles towards you: two steel runners 0.919 m long, 0.62 m apart outside, the handles 0.05 m thick and 1.041 m high at its rear corners; it carries 5.0 kg in all and its runners slide on the turf with a friction coefficient of 0.45. The sled's front edge stands on the start line; the finish line is 12.5 m beyond it, and the lane is 1.0 m to each side of its centre line. Push the sled: only your hands may touch it, and only on the two upright handles (they cannot grip: push, do not pull). The sled has moved once its rear has gone 0.1 m forward. You succeed when the whole sled, its rear included, is over the finish line. You fail if any part of you other than a hand touches the sled, or a hand touches it anywhere but on a handle; if any part of the sled leaves the lane; if you fall (your pelvis lower than 0.5 m above the ground, or any part of you other than your feet on the ground); or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | HYROX Rulebook 2026/27 (the Sled Push station: the sled pushed 50 m in four 12.5 m lengths on the competition turf, each length counted when the whole sled is over the line; the athlete stays in the lane; the loads, the sled included: 102 kg Women Open, 152 kg Men Open and Women Pro, 202 kg Men Pro). There is no rule book for a sled push alone; HYROX's station is the closest official event; deviations: HYROX Sled Push (load): a light sled frame of 5.0 kg with the dimensions and the two 1.04 m push poles of a real weight sled (a 57 lb sled, the lightest with upright poles found: 25.9 kg, 114 N to start on this turf), so that the start takes about 22 N, within what this robot's walking pushes. 5.0 kg in all (0.0 kg of plates) is 7 % of the robot's 67.0 kg. HYROX's lightest official load, 102 kg (Women Open), takes about 450 N to start on the turf: far beyond a 67 kg robot pushing at hip height. · HYROX Sled Push (distance): one 12.5 m length, not four: one action, not the station. · HYROX Sled Push (technique): the sled is pushed with the palms only, on the two upright handles; hands cannot grip (the H1-2's hands are its fixed hands, which do not close), and no other part of the body may touch the sled. · Turf friction: MuJoCo has one friction coefficient per contact: the runners slide on the turf at mu 0.45, the measured push-sled-on-AstroTurf static range (0.37-0.53, Hoffmann 2014) mid value, above the measured kinetic range (0.28-0.35): starting is as hard as on real turf, keeping it moving harder. |
| Stages | moved → line |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/3.0), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
