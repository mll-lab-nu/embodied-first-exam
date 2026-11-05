# embodied-olympics-fun-sumo-i00-realtime

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | realtime (`eai-standard/2.3`) |
| Twin | `embodied-olympics-fun-sumo-i00-privileged` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `sumo` / seed 0 |
| Oracle | `full` — Reference: FALCON walking-policy rows with privileged poses: it pushes with the forearms low, steering 1 m beyond the opponent outwards, and wins at 11.6 s (the opponent down); 8 of 10 perturbed starts and 29 of 40 with its own numbers +-3 % succeed, below the 9 of 10 bar (chaotic shoving of two walking policies). In realtime mode the privileged twin's reference rows, each run of one action type planned at the control step where it ran (`submit(..., at=step)`), succeed at the task's S. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Real time | slowdown S = 1 (the world runs at 1/S of real speed: one control step every S x control_dt s of wall time; `RCB_SLOWDOWN`'s default); reset budget 5 (`RCB_RESET_BUDGET`'s default) (PROTOCOL §3) |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Win a sumo bout: force the opponent robot out of the ring, or make any part of it other than its feet touch the ground, before the same happens to you. (Embodied Olympics `sumo`; the robot as a service on a clock that does not stop, slowdown S = 1: its head cameras, joint sensors and IMUs, and the venue's fixed camera only.)

## Difficulty
The opponent is as heavy and as strong as you and walks into you on a balance policy that pushes back; the robot must stay on its feet under the impact and the shove, and turn the contact into the opponent leaving the ring or going down, with only fists and no belt to grip. The scene is dynamic (A second robot, scripted through its own motors, attacks from opp_start_s.), and in realtime mode time does not stop: once an attempt's clock starts the venue's timed events happen whatever the agent does, so it has to plan or stream the robot's rows from a program of its own, with no simulator and no state, and 5 resets (only the last attempt is graded).

## Reference solution
`solution/oracle_plan.py` plans the privileged twin's reference rows (`solution/rows.npz`) into the attempt at the control steps where they ran there (`submit(..., at=step)`; the first, at step 0, starts the clock); it uses no privileged information at run time. Reference: FALCON walking-policy rows with privileged poses: it pushes with the forearms low, steering 1 m beyond the opponent outwards, and wins at 11.6 s (the opponent down); 8 of 10 perturbed starts and 29 of 40 with its own numbers +-3 % succeed, below the 9 of 10 bar (chaotic shoving of two walking policies).

## Verification
The sim sidecar (`rcb_realtime.py` + `rcb_service.py`, the shared eai-standard/2.3 layer, with the standard twin's
`server.py`) runs the attempt on its clock and its referee judges it live; every control step the simulator applied is
recorded, and the live referee's call on the last attempt is the verdict (`final.json`: `graded_by` live, `replays` 0; no
grading replay, owner 2026-10-17); the video is rendered from the recorded attempt afterwards.
`/tests/grade.py` reads `/data/final.json`: pass iff the live attempt succeeded. The clock's record
(`stalls`, `max_lag_s`, ...) is copied into `reward.json` and decides nothing. `nop`: the attempt never starts (its
clock starts at the first submit), reward 0. The
rules: The bout is on a dohyo: a clay mound 0.55 m high, 6.7 m square, with a ring of straw bales whose inside edge is a circle 4.55 m across (the bales stand 0.05 m proud of the clay). You stand facing the opponent behind your starting line (the white lines are 0.7 m apart, across the middle of the ring); the opponent, another Unitree G1, stands behind its line facing you. The bout starts at t = 0; the opponent charges at t = 0.5 s and keeps walking into you, arms forward, turning to face you. You win at the first moment the opponent touches the ground outside the ring (the mound beyond the bales, or the floor below the mound) with any part of its body, or touches the clay or the bales inside with any part other than its feet, provided you have not done the same before. You lose (the attempt fails) if that happens to you first: any part of you on the ground outside the ring, any part other than your feet on the clay or the bales, or your pelvis lower than 0.35 m above the clay. Both in the same instant is no decision and fails. Kicking the opponent's trunk (its pelvis or torso) with a foot is forbidden and fails. If there is no decision after 30 s, you fail.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 4 | 10 GiB | 8192 | no GPU | 20 GiB |
| `sim` | 4 | 8 GiB | 8192 | 4 GiB | — |
| verifier | no cap | no cap | no cap | no GPU | no cap |

- GPU: any NVIDIA GPU, held by `sim`.
- Recommended GPU: any NVIDIA GPU with EGL (RTX 4090 / L4).

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | Japan Sumo Association, the rules of professional sumo (honzumo): the dohyo (the ring of 4.55 m inside the shobu-dawara bales on a raised clay mound, the two shikiri-sen starting lines 0.9 m long, 0.06 m wide and 0.7 m apart); the decision (kimarite / shobu-dawara rules): a wrestler loses when any part of his body touches the ground outside the ring, or any part other than the soles of his feet touches the ground inside it, first; forbidden techniques (kinjite) lose the bout (among them striking with a closed fist and kicking the chest or stomach); there are no weight classes; deviations: the opponent: a second Unitree G1 with a scripted policy, not a wrestler: from t = 0.5 s it walks at the walking policy's largest forward command (0.8 m/s commanded) straight at you, turning (at most 1.0 rad/s) to face your pelvis, both arms stretched forward at chest height; it never grips, never changes its plan and never gives up; it acts only through its own motors (Unitree's walking policy on the legs, the robot library's joint servo on the arms) · the tachiai: no shikiri ritual, no fists on the clay and no matta (false start): both stand behind their starting lines at t = 0, and the bout is on from then; the opponent charges at t = 0.5 s · the bodies: neither robot wears a mawashi (there is no belt to grip; the G1's hands are fists, pushing with them counts as an open-hand thrust, not a punch); 'the soles of the feet' are each foot's sole and foot shell (the G1's ankle-roll link) · the dohyo: a rigid mound 0.55 m high and 6.7 m square, its clay a firm surface with friction 0.6 (packed clay, 0.5 to 0.7 for clay courts after Nigg 2003; no sand layer, no give); the ring's bales are a row of 20 rigid half-buried capsules standing 0.05 m proud, their inside edge on the 4.55 m circle; the four tokudawara (the bales set outwards at the four sides) are not modelled · the decision is the referee's, on contact: the first physics step (1 ms) in which a part of a robot other than its feet touches the mound, the bales or the floor, or any part touches the mound outside the bales or the floor below it; both in the same step is no decision (in sumo a rematch); a bout with no decision after 30 s fails (honzumo has no time limit for the bout itself) · a kick with a foot on the opponent's trunk (pelvis or torso) is the kinjite of kicking the chest or stomach and loses the bout · you also lose when your pelvis is lower than 0.35 m above the clay (the benchmark's fall line: for the G1 a squat with the hips at the heels, from which it cannot get up; a rikishi is judged by touch alone) |
| Stages | win |
| Service | `environment/sim/rcb_realtime.py` (the shared realtime layer, eai-standard/2.3) with the standard twin's `server.py` on `rcb_service.py`, `rcb_rfo.py`, `rfo/`, `rfo_task.py`, `instance.json` (= the privileged twin's); EGL rendering on the GPU |
| Slowdown | S = 1 (`RCB_SLOWDOWN`'s default): RTF 0.87 with the clock flat out (physics only, the start command held, 4 attempts) on the slowest evaluation host kind (AMD EPYC 7763, one thread; estimated from Xeon Gold 6338 measurements); S = 1 in every family: Embodied Olympics runs the venue in real time (PROTOCOL §2's default would slow these hosts down; a slower host may fall behind, which the clock's record reports) |
| Observations | `head_left`, `head_right` (RGB 270 × 480, depth on `head_left`), `venue` (fixed); proprioception: joints, torques, targets, two IMUs, grip state |
| Episode | 3000 control steps (30 s at 100 Hz); 5 resets, the last attempt graded |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
