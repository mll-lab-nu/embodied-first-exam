# embodied-olympics-fun-slalom-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-slalom-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `slalom` / seed 0 |
| Oracle | `none` — no reference solution; the referee is tested: positive by injection (the robot moved from waypoint to waypoint along the prescribed path inside the limit; a real walk round the whole path latches all 12 gates but takes 126.6 s); negatives: a skipped leg, the wrong side, turning back, a cone not rounded, the wrong finish half, a cone touched, down. The running policy turns at most 0.5 rad/s; human review in the pull request that adds the benchmark (PROTOCOL §4) |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Run the Illinois agility course: up the left side and round the far-left cone, back to the centre cone on the start line, weave up through the four centre cones and back down, up the right side and round the far-right cone, and back over the finish line, without touching a cone. (Embodied Olympics `slalom`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
About 60 m of path with five turns round a cone and six changes of side between cones 3.3 m apart, in 60 s: the walking gait covers 38 m in that time, and the running gait turns at most half a radian per second, so at speed it cannot follow the weave or round a cone. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
None (as `embodied-olympics-fun-slalom-i00-privileged`).

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: The course is 10.0 m long (x from 0 to 10.0 m) and 5.0 m wide, centred on y = 0: its left side line is half that width to the left of the centre line (y > 0), its right side line as far to the right. Corner cones stand where the side lines meet the start line x = 0 (the start cone on the left, the finish cone on the right) and the far line x = 10.0 m (the far-left and the far-right cone). Four centre cones stand on the centre line y = 0, the first on the start line and one every 3.3 m after it. The cones are free (0.09 m base radius, 0.23 m high, 0.25 kg). The clock starts at t = 0. The path, judged on your pelvis, in this order: (1) round the far-left cone: cross the left side line's continuation beyond the far line (x > 10.0 m), in either direction; (2) come back and go round the first centre cone on the start line's side: cross the centre line at x < 0 from the left half (y > 0) to the right half; (3) weave up: cross the centre line between the first and second centre cones from right to left, between the second and third from left to right, between the third and fourth from right to left; (4) go round the fourth centre cone: cross the centre line beyond it from left to right; (5) weave down: between the fourth and third from right to left, the third and second from left to right, the second and first from right to left; (6) go round the first centre cone again: cross the centre line at x < 0 from left to right; (7) round the far-right cone: cross the right side line's continuation beyond the far line (x > 10.0 m), in either direction; (8) finish: the leading point of your torso (not the head, arms, legs or feet) reaches the start line's plane x = 0 with your pelvis in the right half (y < 0). Any crossing of the centre line by your pelvis that is not the next one of this list, at any time, is leaving the prescribed path. You succeed when you finish within 60 s of robot time. A fall does not end the attempt: you are down while your pelvis is below 0.4 m, you may get up and go on, but 10.0 s down in a row end it. You fail if any part of you touches any of the eight cones, if you leave the prescribed path, when down for 10.0 s, or after 60 s. No oracle; human review in the pull request that adds the benchmark (PROTOCOL §4).

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
| Category | track-and-jumps |
| Rule book | The Illinois Agility Test (Getchell 1979; the standard field test of agility): a course 10 m long and 5 m wide marked by four corner cones, four more cones on its centre line 3.3 m apart; the runner sprints up the left side and round the far-left cone, back to the centre cone on the start line, weaves up through the four centre cones and back down, sprints up the right side and round the far-right cone and back to the finish; a touched or knocked cone voids the trial; deviations: the start: the test starts lying face down behind the start line; the robot starts standing, the front ends of its feet 0.02 m behind the line, and the clock runs from t = 0 (no starter) · the path is judged on the pelvis (which side of each cone it passes), the finish on the torso as in athletics (World Athletics TR 19: the leading point of the torso link's collision mesh on the line, interpolated between 1 ms physics steps) · a fallen runner: a robot whose pelvis is below 0.4 m is down; it may get up and go on, but 10.0 s down in a row end the attempt · the qualifying time, 60 s, is this benchmark's own round number: adult norms for this test are 15 to 19 s |
| Stages | far-left cone → bottom cone, first time → up 1-2 → up 2-3 → up 3-4 → top cone → down 3-4 → down 2-3 → down 1-2 → bottom cone, second time → far-right cone → finish |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 6000 control steps (60 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
