# Badminton, low level: implement the high level's `act`

Agent as Robotics Engineer (docs/construction_zh.md step 3; [`skilleval/`](../../../skilleval/README.md)), built as
table tennis's (`sports/tabletennis/lowlevel/`). At the low level the player gets the robot's model, the joint-target
interface of the 9 joints `[base_x, base_y, q1..q7]` (real limits: the Panda's velocity, acceleration, jerk, torque and
torque rate through the robot's servo; the base's speed and acceleration) and the toolkit (`../seat/toolkit.toml`),
and its engineering task is to implement the high level's skill itself:

    act(t, pos, normal, vel[, base])   the racket head centre at pos, string-face normal along normal (either
                                  face), head velocity vel, at contact t s after the act's command takes effect;
                                  base (optional): where the base stands at contact

`toss` (the serve's toss) is the same command at both levels: nothing to implement.

Two ways the skill meets the match:

- **post-match** (the standard low task `badminton-match-wallclock-program-lowlevel-standard`): the player plays its own
  low-level match (joint targets); after it the platform takes `/app/output/skill/act.py` and evaluates it in an
  isolated container (`tools/skill_eval.py badminton <skill dir>`): the API test (hidden requests) and the competition
  test (our fixed reference strategy on the player's `act`, L1 and L2).
- **skill in the loop** (`RCB_SKILL_INLOOP`, `../../../skilleval/inloop.py`, `plugin.inloop_layer`; pilot
  `inloop_pilot.py`, task `make_inloop_task.py`): during the match the player's program sends `act` calls and the
  simulator lowers each with the player's own `act.py` in its sandbox; while a shuttle the robot may meet is in play
  joint commands are refused (409); `step()` runs every 20 ms; every call is logged with the sha256 of the skill's
  files, so the skill tested after the match is the one that played it.

| file | what |
|---|---|
| `../skill_api.py` | the contract's single source (`skilleval.contract.SkillContract`, P6); the high level's `act` schema and `/spec` `skill_contract` come from it; tolerances 2 cm / 3 degrees / 0.15 m/s + 10 % at the contact step |
| `../sport.toml` `[modes.low]` | the deliverable, the toolkit, the cases, the thresholds, `eval_pip` (SciPy, the seat's) |
| `../seat/toolkit.toml`, `../seat/lib/` | the manifest; `bm_kinematics.py` (9-joint FK / Jacobian, arm IK at a given base position, self-collision clearance, the base's go-to law), `bm_servo.py` 1.2.0 (the robot's own servo law on the robot-only model, with the joint-velocity rule of revision wallclock-12: setpoints at 0.9 of the velocity limits, the 1.05 x velocity reflex with the gantry's braking; a rollout follows the simulator bit for bit from rest and within 0.2 mm from a moving start, also through a reflex) |
| `../robot_model.py`, `../seat/robot_only.xml` | the robot's own model, cut out of the match scene |
| `evaluator.py` | the hooks of `skilleval/evaluate.py`: `skill_spec`, `platform`, `api_case`, `competition_match` (+ `COMPETITION_SEEDS`, `competition_summary`); `record` / `make-cases` rebuild `cases/` |
| `cases/` | `hidden.jsonl.gz`: the hidden requests and, on each match's first case, the recorded match's replay log (9-joint targets + tosses: a case starts from the replayed state, bit for bit; simulator side only, left out of the generated tasks); `public.jsonl`: the practice requests (request, the robot's state, our implementation's plan; no world state, no seed) |
| `reference/` | our act from the toolkit only (rule 4): the documented stance, multi-start IK chosen by how much of the head speed its swing reaches, a quintic or cubic swing, rolled out on the servo model from the observed state and corrected up to 6 times |
| `boundary/` | the IK block: the stance, IK to the requested pose, the arm there at its speed limit; no swing (rule 5) |
| `reference_results.json` | the platform / reference / boundary rows (`tools/skill_eval.py ... --record`) |
| `inloop_pilot.py` | the skill in the loop in process: our reference player's decisions sent as `act` calls, lowered by a skill directory; per-call wall time; replay check |
| `make_inloop_task.py` | writes the in-loop task from the generated low-level match task |

## The low level's observation

The low level's state adds the robot's full joint state and the servo's own state (what a real Franka reports:
libfranka `q`, `dq`, `q_d`, `dq_d`, `ddq_d`, `tau_J_d`): `q`, `qd` (9 each), `qd_target` (the velocity of the targets
in force: a new traj's base rows must join it), `servo` {`q`, `qd`, `qdd`, `tau` (7 each), `q_target_prev`, `steady`}.
Without it a robot-only rollout cannot know where the jerk-limited setpoint is (table tennis measured 4-7 cm of blade
error from a moving start; with it 0.05 mm). These fields change no play (the episode and the golden replays are
unchanged).

## The cases

`python3 lowlevel/evaluator.py record DIR` plays our truth-perception reference player with the platform's act on
L1 (101, 111, 121, 131), L2 (202, 212, 222, 232) and L3 (303, 313, 323, 333); each rally leg gives one candidate: the
start state of its first act, the contact of its last (the same contact step, t counted from the first act's effect
step). `make-cases DIR` keeps the feasible ones: from the start state the platform without its execution scatter plans
the request and its own rehearsal delivers it within 15 mm, 2.5 degrees and 0.10 m/s + 8 % (IK residual < 2 mm, the
base at its stance in time, no self-collision); a request beyond the joint speed limits is scaled the way the platform
scales it. 30 % (by a hash of the request) are public.

## The base

The base is the Festo EGC-185-BS-KF-40P ball-screw gantry (2 m/s, 15 m/s^2 per axis, x stroke 3 m; the screening's base
study replaced the 5 m/s belt axes). There is no automatic return: after a traj the base holds its last row's position
until a `move`. `act` takes an optional `base` (where the base stands at contact; the hidden requests all carry it: the
platform's stance when the reference player gave none). The low level is written so that a base change changes data,
not code: `robot_only.xml` is cut from the scene; the kinematics library takes the base's limits
from game spec (`limits.base`); the servo model's base gains are one block (`BASE_KP`, `BASE_KD`; the drive force is
the model's ctrlrange); the reference and boundary skills read the stance from the contract and the limits from spec.
After a base change: regenerate `robot_only.xml`, refresh the toolkit's sha256, re-record and re-make the cases
(`record`, `make-cases`), re-record the reference rows (`tools/skill_eval.py ... --record`).

## Results

See `reference_results.json` and the screening report (docs/screening/badminton.md, low level).
