# Table tennis, low level: implement the high level's `hit`

Agent as Robotics Engineer (docs/construction_zh.md step 3; [`skilleval/`](../../../skilleval/README.md)). PR #31
did this on the old fixed-base, velocity-limited robot (toolkit 1.0.0); this is the redo on the real-limits rail
version (revision 12/10, toolkit 2.0.0). At the low level the player gets the robot's model, the joint-target interface
of the 9 joints `[base_x, base_y, q1..q7]` (real limits: the Panda's velocity, acceleration, jerk, torque and torque
rate, the rail's speed, acceleration and jerk) and the toolkit (`../seat/toolkit.toml`), and its engineering task is to
implement the high level's skill itself:

    hit(t, pos, normal, vel)      the blade centre at pos, face normal along normal, blade velocity vel,
                                  at contact t s after the hit's command takes effect

The skill meets the match twice:

- **in the match** (the skill in the loop, `sport.toml [modes.low.inloop]`, `../../../skilleval/inloop.py`): the low
  tasks are generated with one skill container per seat (`tools/generate.py`: no network, read-only, no simulator
  files); the player's program sends `hit` calls and the simulator lowers each with the player's own `hit.py` running
  there; the call's compute counts in match time (the world runs on; the command takes effect when it returns); while
  a ball is in play joint commands are refused (409), `toss` is free; `step()` runs every 20 ms; every call is logged
  with the sha256 of the skill's files (`inloop_<seat>.jsonl`).
- **after the match**: the platform takes the final `/app/output/skill/hit.py` and evaluates it in an isolated
  container (`tools/skill_eval.py tabletennis <skill dir> --inloop-log <inloop_A.jsonl>`): the API test (hidden
  requests) and the competition test (our fixed reference strategy on the player's `hit`); the report says whether
  the evaluated skill is the one that played the match.

| file | what |
|---|---|
| `../skill_api.py` | the contract's single source (`skilleval.contract.SkillContract`, P6: inputs, timing, feedback, authority, failure handling); the high level's `hit` schema and `/spec` `skill_contract` come from it |
| `../sport.toml` `[modes.low]` | the deliverable, the toolkit, the cases, the thresholds, `eval_pip` (SciPy, the seat's) |
| `../seat/toolkit.toml`, `../seat/lib/` | the manifest; `tt_kinematics.py` (9-joint FK / Jacobian, arm IK at a given base position, the rail's go-to law and stance rule), `tt_servo.py` (the robot's own servo law on the robot-only model: a player's rollout is exact when it starts from the observed `servo` state) |
| `evaluator.py` | the hooks of `skilleval/evaluate.py`: `skill_spec`, `platform`, `api_case`, `competition_match` (+ `COMPETITION_SEEDS`, `competition_summary`); `record` / `make-cases` rebuild `cases/` |
| `cases/` | `hidden.jsonl.gz`: the hidden requests and, on each match's first case, the recorded match's replay log (9-joint targets + tosses: a case starts from the replayed state, bit for bit; simulator side only, left out of the generated tasks); `public.jsonl`: the practice requests (request, the robot's state, our implementation's plan; no world state, no seed) |
| `reference/` | our skill from the toolkit only (rule 4): two swing shapes (a cubic over the time available; a wind-up + constant-acceleration stroke), each rolled out on the servo model from the observed state and corrected (up to 6 times), table avoidance from above, services kept clear of the toss |
| `boundary/` | the IK block: the stance, IK to the requested pose, slew there; no swing (rule 5) |
| `reference_results.json` | the platform / reference / boundary rows (`tools/skill_eval.py ... --record`) |
| `inloop_pilot.py` | the skill in the loop in process (no wall clock): the in-loop oracle (`builtin_players.SkillReference`) plays through a skill directory; per-call wall time; replay check. The match service's version: `tools/live.py tasks/tabletennis-match-wallclock-program-lowlevel-standard OUT oracle` |

## What changed from #31

- 9 joints (the rail base is part of the skill: where the base stands at contact is the implementation's choice; the
  platform's is the stance rule) and the real limits (the rows are checked for speed and acceleration; the servo
  limits jerk and torque rate).
- The low level's observation adds the target's velocity `qd_target` (what a new trajectory's first row must join)
  and the servo's own state `servo` {q, qd, qdd (9 each), tau (7)}: the desired joint state and torque a real Franka
  reports (libfranka `q_d`, `dq_d`, `ddq_d`, `tau_J_d`). Without it a robot-only rollout cannot know where the
  jerk-limited setpoint is: measured 4-7 cm of blade error after 0.2-0.4 s from a moving start; with it 0.05 mm.
- The toolkit adds the servo model (`tt_servo.py`, the documented law of `/spec limits.controller` as code). Under the
  real limits the servo's lag is the main engineering problem; the model is what a robot vendor ships with its
  controller. It reads only the robot's own state.
- Case start states: replayed from the recorded match (bit-exact; #31 restored hand-picked fields of a snapshot,
  which the rail version's servo, rail limiter and serve state would have made fragile).
- Feasibility of a request: the platform's own rehearsal (the robot alone, no scatter) delivers it within 15 mm,
  2.5 degrees and 0.10 m/s + 8 % (#31: the planner's stroke flag "ok", which the limits-aware planner sets far more
  rarely: 40 of 130 instead of 55).
- Touching the table is allowed by the rules since revision 9/7 (D4): it is reported (`robot_table_contact`), not a
  failure; touching the net is a failure (`robot_net_contact`, a lost point).

## Results

See `reference_results.json` and docs/screening/tabletennis.md.
