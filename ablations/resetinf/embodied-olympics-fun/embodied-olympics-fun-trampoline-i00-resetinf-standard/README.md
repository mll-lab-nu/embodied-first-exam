# embodied-olympics-fun-trampoline-i00-standard

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | standard (`eai-standard/2.1`) |
| Twin | `embodied-olympics-fun-trampoline-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `trampoline` / seed 0 |
| Oracle | `full` — Reference: a scripted G1 tuck jump (a balanced crouch, a lowcmd push on the sprung bed, the tuck held mid-flight, a squat landing that sinks as the bed recoils, one straight out-bounce, an ankle-strategy stand-up, 3 s still), chosen from 12 settings: 0.457 s of flight, a centre-of-mass rise of 0.32 m. The bed passes the FIG IV TRA 1 impact test in simulation (60 kg sphere from 4.00 m: deflection 0.988 m, in 940-1010 mm; rebound 3.486 m, in 3410-3660 mm). Negatives: nop, a tuck without a jump, pike first, a bent out-bounce, a second flight, a fall, an injected roll spin, an injected push onto the padding. The privileged twin's reference rows (755 control steps, success after 7.55 s) streamed through the client. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
On the trampoline, bounce as you like, then do one tuck jump, land on both feet, stop the bounce (one more straight out-bounce at most) and stand still. (Embodied Olympics `trampoline`; the robot as a service: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The robot must time its leg push with a bed that drops and recoils under it to gain height, tuck and open again in the air, land on both feet, and then kill the bounce of a springy bed with its legs until it stands still. In standard mode the agent has no simulator and no state: it sees through the robot's cameras, acts through the client, and has 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_replay.py` streams the privileged twin's reference solution, row by row, through the client (`solution/rows.npz`, recorded at generation time). Reference: a scripted G1 tuck jump (a balanced crouch, a lowcmd push on the sprung bed, the tuck held mid-flight, a squat landing that sinks as the bed recoils, one straight out-bounce, an ankle-strategy stand-up, 3 s still), chosen from 12 settings: 0.457 s of flight, a centre-of-mass rise of 0.32 m. The bed passes the FIG IV TRA 1 impact test in simulation (60 kg sphere from 4.00 m: deflection 0.988 m, in 940-1010 mm; rebound 3.486 m, in 3410-3660 mm). Negatives: nop, a tuck without a jump, pike first, a bent out-bounce, a second flight, a fall, an injected roll spin, an injected push onto the padding. The privileged twin's reference rows (755 control steps, success after 7.55 s) streamed through the client.

## Verification
The sim sidecar's referee judges the live attempt, and that is the verdict (`final.json`: `graded_by` live, `replays` 0;
no grading replay, owner 2026-10-17); the frozen start is checked on the live simulator (`instance_mismatch`:
infrastructure), and the video is rendered from the recorded attempt afterwards. `/tests/grade.py` reads
`/data/final.json`: pass iff the live attempt succeeded. The
rules: You stand at the centre of the trampoline's bed, 1.155 m above the floor, facing +x along its length. A flight is a time of at least 0.1 s in which nothing of you touches anything; your centre of mass's height when you stand at the start is the reference height. Straight bounces first are free. The tuck jump is your first flight in which your body is not straight: at some moment of its middle half (from a quarter to three quarters of the flight's time) each leg must be tucked: the angle at the hip between your shoulder and your knee, and the angle at the knee between your hip and your ankle, both 135.0 degrees or less (180 is straight), held for at least 0.05 s without a break, and it must be a jump: in it your centre of mass rises at least 0.1 m above the reference height (a tuck without that height fails). A flight before it in which a hip or a knee closes to 135.0 degrees or less in the middle half without the tuck is another element and fails. Every landing must be on the bed, on your feet only, both feet within 0.1 s of each other. After the tuck jump's landing you may make one more flight, an out-bounce, which must be straight (hips and knees more open than 135.0 degrees through its middle half); a second flight fails. Then stop: stand still for 3.0 s without a break: only your feet on the bed, your torso within about 20 degrees of vertical, your pelvis slower than 0.35 m/s, your ankles at most 0.28 m apart. You fail on a landing with any other part of you on the bed, on touching anything other than the bed (the padding over the frame and springs, the end platforms, the floor), or after 30 s. Success: the tuck jump, its landing and the stop, in that order.

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
| Rule book | FIG Code of Points 2022-2024, Trampoline Gymnastics (valid from 1 January 2022; the edition the family was written from): Part I §14.2-14.3 (the tuck position: the angle between the upper body and the thighs and the angle between the thighs and the lower legs each 135 degrees or less; straight: the upper body-thigh angle greater than 135 degrees), §16.1 (an interruption: not landing simultaneously on both feet, landing on a part of the body other than the feet, seat, front or back, touching anything other than the bed, leaving the trampoline), §17.1-17.3 (the end: upright on the bed with the feet less than shoulder width apart, at most one controlled out-bounce in a straight position, then standing still for about 3 seconds), Part II §14 (a shape is judged in the middle phase of the element). FIG Apparatus Norms TRA 1 (01.01.2017): the frame 5.05 x 2.91 m inside, the bed 4.28 x 2.14 m at 1.155 m, area A 2.15 x 1.08 m and area B 1.08 x 1.08 m marked in red lines 13-24 mm wide with a 0.70 m red cross at the centre; the frame and springs padded 3-5 cm thick; end platforms with mats; and FIG Apparatus Norms IV TRA 1 (01.04.2024): the impact test, a 60 kg, 0.40 m sphere dropped from 4.00 m onto the centre: deflection 940-1010 mm, rebound 3410-3660 mm; deviations: Apparatus Norms TRA 1 (the bed): the web bed and its 118 springs are one flat plate on a vertical slide with a linear spring of 5690.0 N/m, the equivalent vertical stiffness measured at the centre of a 5.05 x 2.91 x 1.15 m competition trampoline (Qian et al. 2020, J Hum Kinet 73: 59-72), its moving mass 3.0 kg (an estimate: the literature's models treat the bed as massless) and a damping 3.0 N s/m chosen so that the norm's impact test passes (the family's test drops the 60 kg sphere from 4.00 m). The plate stays level: a real bed dips locally under the feet and throws an off-centre landing towards the middle (the norm's 1.67-2.02 m sideways rebound at its point 4); here an off-centre landing goes straight up, and the bed's stiffness does not grow with depth · Code of Points §1 and §16.1.3 (the exercise): one element, a tuck jump, instead of ten; straight bounces before it are free (in-bounces), as before an exercise starts; no execution, difficulty, time-of-flight or horizontal-displacement score: the attempt is valid or not · Code of Points §14.2-14.3 / Part II §14 (the tuck): judged on the robot's joint centres: in each leg the angle at the hip between the shoulder and the knee, and at the knee between the hip and the ankle, both at most 135.0 degrees, held at least 0.05 s within the middle half of the flight (a shape passed through on the way is not shown); the hands on the shins and the pointed toes (§14.3, §14.5: execution deductions) are not judged · Code of Points §14 (a jump): the rule book scores height (time of flight) but sets no minimum; a tuck counts only in a flight whose centre of mass rises at least 0.1 m above its height standing at the start, so that lifting the legs off the bed is not a jump · Code of Points §16.1.1 (both feet simultaneously): the second foot must touch the bed within 0.1 s of the first; a flight counts from 0.1 s in the air · Code of Points §16.1.4 (the landing): only the feet: seat, front and back landings, legal in an exercise, end this attempt as falls · Code of Points §17.1-17.3 (the stop): standing still is judged as 3.0 s without a break with only the feet on the bed, the torso within 20 degrees of vertical, the pelvis slower than 0.35 m/s and the ankles at most 0.28 m apart (the robot's shoulder width: the distance between its shoulder joints); the out-bounce must be straight (hips and knees more than 135.0 degrees open through its middle half) · the robot starts standing at the centre of the bed (placed there at t = 0, the bed bent under its weight), not climbing on |
| Stages | tuck jump → landing → stop |
| Service | `environment/sim/server.py` (the Embodied Olympics adapter) on `rcb_service.py` (eai-standard/2.1), `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
