# embodied-olympics-fun-sumo-i00-privileged

| | |
|---|---|
| Benchmark | Embodied Olympics - Fun |
| Mode | privileged |
| Twin | `embodied-olympics-fun-sumo-i00-standard` |
| Simulator / robot | `mujoco` / `unitree-g1` |
| Family / instance | `sumo` / seed 0 |
| Oracle | `full` — Reference: FALCON walking-policy rows with privileged poses: it pushes with the forearms low, steering 1 m beyond the opponent outwards, and wins at 11.6 s (the opponent down); 8 of 10 perturbed starts and 29 of 40 with its own numbers +-3 % succeed, below the 9 of 10 bar (chaotic shoving of two walking policies). Measured: success after 14.8 s of the 30 s limit, live and in a fresh replay, ending in the same state. |
| Agent time budget | 7200 s; tokens: protocol default (docs/protocol/running.md "Official runs") |
| Base image | `ghcr.io/mll-lab-nu/efe:embodied-olympics-fun-0.2.1` |

## Task
Win a sumo bout: force the opponent robot out of the ring, or make any part of it other than its feet touch the ground, before the same happens to you. (Embodied Olympics `sumo`: one Unitree G1 on the Embodied Olympics simulator, judged by a referee of events, geometry and contact rules.)

## Difficulty
The opponent is as heavy and as strong as you and walks into you on a balance policy that pushes back; the robot must stay on its feet under the impact and the shove, and turn the contact into the opponent leaving the ring or going down, with only fists and no belt to grip.

## Reference solution
`solution/oracle.py` drives the robot through the task's own tooling, closed loop on the privileged state, and writes the trajectory (`solution/solve.sh`). Reference: FALCON walking-policy rows with privileged poses: it pushes with the forearms low, steering 1 m beyond the opponent outwards, and wins at 11.6 s (the opponent down); 8 of 10 perturbed starts and 29 of 40 with its own numbers +-3 % succeed, below the 9 of 10 bar (chaotic shoving of two walking policies). Measured: success after 14.8 s of the 30 s limit, live and in a fresh replay, ending in the same state.

## Verification
`/tests/grade.py` replays `/app/output/trajectory.npz` from the frozen start in one fresh process (`rcb_rfo.py replay`:
one sim row per control step until the referee ends the attempt). Pass iff the referee's verdict is a success. The rules: The bout is on a dohyo: a clay mound 0.55 m high, 6.7 m square, with a ring of straw bales whose inside edge is a circle 4.55 m across (the bales stand 0.05 m proud of the clay). You stand facing the opponent behind your starting line (the white lines are 0.7 m apart, across the middle of the ring); the opponent, another Unitree G1, stands behind its line facing you. The bout starts at t = 0; the opponent charges at t = 0.5 s and keeps walking into you, arms forward, turning to face you. You win at the first moment the opponent touches the ground outside the ring (the mound beyond the bales, or the floor below the mound) with any part of its body, or touches the clay or the bales inside with any part other than its feet, provided you have not done the same before. You lose (the attempt fails) if that happens to you first: any part of you on the ground outside the ring, any part other than your feet on the clay or the bales, or your pelvis lower than 0.35 m above the clay. Both in the same instant is no decision and fails. Kicking the opponent's trunk (its pelvis or torso) with a foot is forbidden and fails. If there is no decision after 30 s, you fail.

## Resources
Caps per container (PROTOCOL §6).

| Container | CPUs | Memory | Processes | GPU memory | Disk |
|---|---|---|---|---|---|
| `main` (the agent's) | 8 | 16 GiB | 1024 | no GPU | 10 GiB |
| verifier | 4 | 8 GiB | no cap | no GPU | no cap |

- GPU: not needed.

## Details
| | |
|---|---|
| Category | throwing-catching-striking |
| Rule book | Japan Sumo Association, the rules of professional sumo (honzumo): the dohyo (the ring of 4.55 m inside the shobu-dawara bales on a raised clay mound, the two shikiri-sen starting lines 0.9 m long, 0.06 m wide and 0.7 m apart); the decision (kimarite / shobu-dawara rules): a wrestler loses when any part of his body touches the ground outside the ring, or any part other than the soles of his feet touches the ground inside it, first; forbidden techniques (kinjite) lose the bout (among them striking with a closed fist and kicking the chest or stomach); there are no weight classes; deviations: the opponent: a second Unitree G1 with a scripted policy, not a wrestler: from t = 0.5 s it walks at the walking policy's largest forward command (0.8 m/s commanded) straight at you, turning (at most 1.0 rad/s) to face your pelvis, both arms stretched forward at chest height; it never grips, never changes its plan and never gives up; it acts only through its own motors (Unitree's walking policy on the legs, the robot library's joint servo on the arms) · the tachiai: no shikiri ritual, no fists on the clay and no matta (false start): both stand behind their starting lines at t = 0, and the bout is on from then; the opponent charges at t = 0.5 s · the bodies: neither robot wears a mawashi (there is no belt to grip; the G1's hands are fists, pushing with them counts as an open-hand thrust, not a punch); 'the soles of the feet' are each foot's sole and foot shell (the G1's ankle-roll link) · the dohyo: a rigid mound 0.55 m high and 6.7 m square, its clay a firm surface with friction 0.6 (packed clay, 0.5 to 0.7 for clay courts after Nigg 2003; no sand layer, no give); the ring's bales are a row of 20 rigid half-buried capsules standing 0.05 m proud, their inside edge on the 4.55 m circle; the four tokudawara (the bales set outwards at the four sides) are not modelled · the decision is the referee's, on contact: the first physics step (1 ms) in which a part of a robot other than its feet touches the mound, the bales or the floor, or any part touches the mound outside the bales or the floor below it; both in the same step is no decision (in sumo a rematch); a bout with no decision after 30 s fails (honzumo has no time limit for the bout itself) · a kick with a foot on the opponent's trunk (pelvis or torso) is the kinjite of kicking the chest or stomach and loses the bout · you also lose when your pelvis is lower than 0.35 m above the clay (the benchmark's fall line: for the G1 a squat with the hips at the heels, from which it cannot get up; a rikishi is judged by touch alone) |
| Stages | win |
| Instance | `environment/instance.json` = `tests/instance.json`: the family's parameters, t = 0 state hash `c21c898d861922507998e3396ad58656af3894de5fbe7518bd180b614e07c0f4` |
| Episode | 3000 control steps (30 s at 100 Hz) |
| Action | sim rows of 151 floats per control step (`rfo/world.py`); six action types are views of it |
| Tooling | `/opt/tools/rcb_rfo.py`, `/opt/tools/rfo/` (the world, the action layer, the referee's toolkit; from the files-only image images/embodied-olympics-fun-files/, built from embodied_first_exam/benchmarks/embodied-olympics-fun/) and `environment/rfo_task.py` (this family's rules), the same files in the verifier's `/tests/` |
| Network | open: agents may search for and download public tools, robot models and pretrained controllers (owner, 2026-10-11; tasks/embodied-olympics-fun/README.md) |
