# embodied-olympics-fun-backflip-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-backflip-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `backflip` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (3.4 m/s up and 9 rad/s backwards: 360 degrees in 0.70 s of flight, the rotation stopped at touchdown, the stand is the robot's own); a salto that lands on its feet 36 degrees short of upright has its turn and landing counted; negatives: no turn, a forward flip, two thirds of a turn, a spin about the vertical with the pelvis on its side, a head-first landing, a roll on the ground, a hop shorter than the minimum flight, not from the feet. An open-loop squat jump of the G1 has 2.7 m/s and 0.55 s of air; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Do a standing backflip: jump, turn backwards through a full turn in the air, land on your feet and stand. (Embodied Olympics `backflip`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
A full backward turn needs about 0.6 s of flight with a fast rotation, from legs whose motors give 88 to 139 N m, and a landing on the feet that stops the rotation. No built-in action jumps at all. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-backflip-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The flip is one flight phase (nothing of you touches the ground) of at least 0.2 s that starts from your feet (at lift-off the last things on the ground were your feet, nothing else); shorter hops are ignored, and your first flight of at least 0.2 s is your attempt. The turn is measured on your pelvis: the angle it rotates backwards (head going back, feet coming forward) about the horizontal axis that was its left-right axis at lift-off, added up from lift-off while you are in the air; a rotation on the ground and a twist about the vertical do not count. It must reach 300.0 degrees before anything touches the ground (a full turn less the backward lean a standing take-off already has when the feet leave the ground and the lean a salto still has when its feet touch down: the landing and the stand have to finish the turn). The first touch after the flight must be with the feet only. You then stand for 2.0 s without a break: only your feet on the ground, your torso within 20.0 degrees of vertical, your pelvis slower than 0.35 m/s. You fail if the attempt did not start from the feet alone, if it lands with less than 300.0 degrees turned, if it lands on anything but the feet, if you fall at any time (a fall is: a part of you other than a foot touches the ground, or your pelvis is lower than 0.2 m; a crouch above that is not a fall), or after 20 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Rule book | FIG Code of Points, floor exercise: the salto backward tucked from a stand (a standing back tuck), landed on the feet; FIG Apparatus Norms, floor: a 12 m x 12 m performance area; deviations: FIG Apparatus Norms, floor: the floor is rigid and level, not the norm's sprung floor with its elastic surface, because the simulator's ground is rigid (a sprung floor would give energy back: this is not easier) · FIG Code of Points (execution is scored): the salto is judged pass or fail on the rotation, the feet-first landing and the stand, because the task is a single action without a judging panel · the Code of Points has no number for a completed salto; here the pelvis must have turned 300.0 degrees backwards between lift-off and the first touch (a full turn less the backward lean at lift-off and the forward lean a salto still has when its feet touch down); the feet-first landing and the stand judge the rest |
| Stages | take-off → full turn → landing → stand |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 2000 control steps (20 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
