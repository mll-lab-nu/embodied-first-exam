# Writing a RoboOlympics family

A family is one sport task for one Unitree G1: a venue, a start, and a referee. It is one Python module,
`shared/rfo/tasks/<family_snake>.py`, defining `Task(TaskBase)`, plus a referee test `tests/test_<family_snake>.py`
and, where one exists, a reference solution `oracles/<family>/oracle.py`. The generator copies the core package
(`shared/rfo/{__init__,scene,looks,world,referee,task}.py`; `testing.py` stays here, for the tests) and the family's module (as `rfo_task.py`) into the task
directories; a task directory never holds another family's module.

Read first: `shared/rfo/task.py` (the hooks), `shared/rfo/scene.py` (venue building, collision classes, balls; how a
venue looks is not a family's business: `shared/rfo/looks.py` gives the sun, the sky and a material to every large flat
surface by its colour, so paint a lawn green, a track red, a wooden floor tan),
`shared/rfo/referee.py` (the toolkit), `shared/rfo/world.py` (the robot, the action layer, the grip), and the four
families that exist: `sprint` (a course), `penalty_kick` (a ball, contact rules, a goal), `free_throw` (a gripped ball,
release, a hoop), `standing_long_jump` (flight phases, a mark, a stable landing), with `tests/test_sprint.py`.

Run anything in the simulator image (CPU only, no GPU):

```bash
scripts/roboolympics/dev.sh /rfo/tests/test_sprint.py
scripts/roboolympics/dev.sh -c "from rfo.testing import make, hold, verdict; w, A = make('sprint'); hold(w, A); print(verdict(w))"
RFO_OUT=/some/dir scripts/roboolympics/dev.sh my_script.py     # /out in the container = $RFO_OUT (images, videos)
```

`/rfo` is `scripts/roboolympics` (read-only), `PYTHONPATH` is `shared/` and `tests/`. Look at your venue:
`imageio.imwrite('/out/x.png', w.render('venue', 640, 360))` (also `head_left`), then open the PNG.

## v2: official settings (owner, 2026-10-11)

The families are being reworked from the v1 "easy setting" to real ones: read `FAMILIES.md` first; it overrides any
advice below about scaling a rule book to the robot or setting a success line from what a controller reaches.
- `robot = "unitree_g1"` or `"unitree_h1"` (the Unitree H1-2: 1.78 m, 67 kg, 27 joints: legs hip yaw, pitch, roll, knee,
  ankle pitch, roll; one torso yaw; arms shoulder pitch, roll, yaw, elbow pitch, elbow roll, wrist pitch, yaw; leg
  motors 200 / 200 / 200 / 300 / 60 / 40 N m, arms 40 / 40 / 18 / 18 / 19 / 19 / 19; a walking policy, about 0.6 m/s,
  that drifts in heading; no running policy, so its action types are `stand`, `walk`, `joints`, `lowcmd`; its rest
  pose has the upper arms down and the forearms forward; its trunk and head are one hull, part `torso`: no `head`).
  `Actions(w.robot)`, `w.L` (the robot's joint layout and sim row), `w.robot.stand_z` adapt by themselves.
- `rulebook` and `deviations` on the Task; the venue's official dimensions in `params`.
- Balls from `scene.OFFICIAL` (`"football"`, `"basketball"`, `"volleyball"`, `"tennis"`, `"tabletennis"`, `"baseball"`,
  `"golf"`, `"shot"`, `"bowling"`): official size and mass, bounce from the rule book's drop test, drag and Magnus lift
  in the venue's air (MuJoCo's ellipsoid fluid model; `Scene()` has air by default). An implement that flies (javelin,
  discus) gets `fluidshape="ellipsoid"` on its geom too.
- RoboOlympics' realistic material may be copied in where a family needs it (its repository is at
  a checkout of https://github.com/CHIGUI0/roboolympics, MIT): the table-tennis ball / table / net contact pairs
  of `sports/tabletennis/sim/scene/tt_scene.xml` (DeepMind's system identification, Apache-2.0) and its serve library
  `sim/serve_library.json`; the bowling lane, pins and oil zones of `sports/bowling/sim/bowling.py`; the tennis and
  baseball flight coefficients; the athletics start procedure and hinged hurdle of `sports/athletics/track.py` (branch
  `athletics-v3`). Copy numbers and small data into the family's module (a task directory carries only the core
  package and its own module); say where each came from.

## The robot and its actions (the same in every family)

RoboOlympics' Unitree G1 (29 joints, 33 kg, 1.32 m; real joint, speed and torque limits; motor torque-speed curves;
self-collision), one control step = 10 ms = 10 physics steps. Action types (`Actions.types`), each ending in
`grip_left, grip_right`:

| type | row | who drives the legs |
|---|---|---|
| `stand` | waist 3 + arms 14 joint targets | the platform holds the stance (stand gains + gravity support) |
| `walk` | vx, vy, wz + waist 3 + arms 14 | Unitree's walking policy: commands |vx| ≤ 0.8, |vy| ≤ 0.5 m/s, |wz| ≤ 1.57 rad/s (about 0.6 m/s real at 0.8) |
| `run` | vx, vy, wz | RoboOlympics' running policy, all 29 joints: 0 ≤ vx ≤ 5 (stable to about 4 m/s), |vy| ≤ 0.12, |wz| ≤ 0.5 |
| `run_arms` | vx, vy, wz + arms 14 | the running policy drives legs and waist |
| `joints` | 29 joint targets | the agent (default PD gains) |
| `lowcmd` | 29 × (q, dq, tau, kp, kd) | the agent (Unitree LowCmd) |

Measured capability of this robot (RoboOlympics' own measurements and the family authors'; use them to set success
lines that are possible): walking about 0.6 m/s at the largest command; running 4 m/s (20 m from a standstill in 6.7 s);
a walking robot pushes a 0.3 kg ball to about 1.8 m/s, a running one harder; a straight-arm underarm swing in `stand`
mode releases a 0.3 kg ball at 5 to 10 m/s, a javelin at 12 m/s, a 1 kg shot at 5.6 m/s (the robot staying up if it
switches to `walk` at zero command after the release); a punch drives a 0.6 kg pad to 3 m/s; an open-loop squat jump
leaves the ground at 2.7 m/s (0.55 s of air, no landing controller); a public whole-body jump policy (ASAP, level 3)
does a 0.90 m standing long jump with 0.33 s of flight, clears a 0.14 m bar reliably and 0.18 m never; no controller
has cleared a 0.20 m hurdle; a run-up into a jump has always fallen; no single-leg hop or balance exists. The arms'
motors give 25 N m (wrists 5), the legs 88 to 139 N m. Agents are allowed to download public policies and tools, so
"hard, but done by a published G1 controller" is a fair success line; "beyond the motors" is not.

Things the family authors ran into: `stand` is open loop (no balance feedback; the body sways for seconds after an arm
move and topples after a hard swing unless the controller goes to `walk` at zero command); `run` → `walk` above about 0.6 m/s falls; a
foot stands on four small sole spheres, so a foot overhanging an edge is either supported or not; a tool on the
ground is "a part other than the feet on the ground" unless the family adds `right_tool` to `legal_ground`; `fall_z`
is an absolute pelvis height (a family on apparatus raises it by the apparatus' height); a physics blow-up ends the
attempt centrally (`world.UNSTABLE`), a family need not check.

Hands: the G1 has rubber fists, no fingers; each is a pad of 4.4 × 8 × 10 cm on the wrist mount (the 10 cm along the
forearm). Each hand has a **grip**: with `grip_<side>` ≥ 0.5 the hand holds the nearest *grippable* object whose
surface is within 3.5 cm of its palm point (the pad's middle) and that moves at most 6 m/s relative to it (a weld,
`World.grab`); < 0.5 lets go. The palm point is inside the pad, so only an object against one of the pad's two broad
faces (the mount's ±x) is in reach; an object a family welds elsewhere at reset (at the fist's end) cannot be gripped
again there. A family declares what is grippable (`sc.ball(..., grippable=True)` or `sc.grippables[name] =
{"radius": r, "half_length": L, "axis": "y"}` for a rod) and may veto a grip (`Task.may_grip`). A tool on a hand
(racket, paddle, club) is `sc.hand_tools["right"] = "<geom .../>"` (MJCF in the frame of the wrist mount: +z along the
forearm away from the wrist; `contype="4" conaffinity="0"`); its geoms are the robot part `right_tool`, replace the
pad, and collide with the rest of the robot's body (explicit pairs, `world.py`).

## The Task

```python
class Task(TaskBase):
    name = "penalty-kick"            # the family (kebab-case); the file is penalty_kick.py
    title, category                  # category: one of task.py's five
    time_limit_s = 20.0              # the episode fails with "time" here; keep episodes short (10-40 s)
    start = (x, y, yaw)              # the robot at t = 0 (standing, arms at rest)
    stages = ["kick", "goal"]        # the events that must happen, in order (progress = latched / total)
    params = dict(...)               # EVERY number of the rules; quoted by the texts as {name}
    fall_rule, fall_z, legal_ground  # default: a fall fails (pelvis < 0.35 m, or a part other than the feet on the ground)
    sentence, rules, venue, difficulty   # the texts (below)

    def build(self, sc): ...             # the venue (Scene); add sc.camera("venue", pos, target) -- every family has one
    def reset(self, w): ...              # place props: w.put, w.pin, w.grab(side, name, event=False)
    def referee_reset(self, w, ref): ... # selectors and trackers; put trackers in self.trackers (state hash)
    def before_step(self, w): ...        # each control step, before the action: launch a ball (w.launch) at its time
    def substep(self, w, ref): ...       # each physics step (1 ms): contact events, crossings
    def step(self, w, ref): ...          # each control step: slow conditions, holds, the success
    def privileged(self, w): ...         # object poses etc. for privileged tooling
```

The referee's rules of thumb (they are the benchmark's contract, review will check each):

1. **Events, geometry, contacts; no reward.** `success` = every stage latched in order with no rule broken. Call
   `ref.stage(name)` when an event happens, `ref.fail(reason)` on a violation (it ends the episode), `ref.succeed()` at
   the end. A stage whose predecessor has not latched is ignored.
2. **False at t = 0 and for nop.** Standing still for the whole episode must fail (usually with "time").
3. **Count contact events, not contact frames**: `Touch(ref, A, B, gap)`; a legal touch is short (check
   `touch.duration` or `touch.longest` against a carry limit) and separated from the next by flight.
4. **Legal body parts per task**: `ref.part("feet", "shins")`, `ref.part("hands")`, `ref.part("forearms")`, `"head"`,
   `"robot"`; `ref.parts_touching(sel)` names the offenders for the fail event.
5. **Fast crossings on the physics step**: `Crossing`, `MouthPass` (whole ball through a rectangle), `HoopPass` (down
   through a ring), never a position check per control step for something that flies.
6. **Close the cheap exits.** For each task write down how to "succeed" without doing the sport (walk over the line
   instead of jumping, carry the ball into the goal, hold the ball while it "bounces", go round the bar, drop the
   ball through the hoop from above, hit the target with the wrong part) and make the referee refuse it; each one is
   a negative test.
7. **A held end state where the sport has one**: land and stand `ref.hold("stand", ref.standing(), seconds)`, catch
   and hold, a lift held overhead.
8. **Deterministic.** No Python randomness, no wall clock, no dict-order dependence; anything a tracker remembers is in
   `self.trackers` (values with `.state()`, or plain JSON values) so that `World.state_sha()` covers it.
9. **Scaled to the robot, numbers in `params`.** A real rule book's dimensions are scaled to a 1.32 m, 33 kg robot;
   every threshold the referee uses is a `params` entry and appears in `rules`.

Useful world calls: `w.pelvis()` (x, y, z, yaw), `w.com()`, `w.upright()`, `w.pos(body)`, `w.vel(body)` (free body),
`w.holder(name)`, `w.held`, `w.put / w.pin / w.unpin / w.launch`, `w.t`, `ref.time`, `ref.robot_span(axis)` (the
robot's extent along a direction: "the whole body is past the plane"), `ref.airborne()`, `Flights(ref)`,
`ref.contact_points(A, B)`, `ref.standing()`, `ref.metrics[...] = number` (reported, e.g. a distance or a count).

## The texts

`sentence` (one sentence, imperative), `rules` (the whole rule book the referee applies, every number as `{param}` or
`{time_limit_s}`; what succeeds, what fails), `venue` (where things are at t = 0 in the robot's starting frame, as an
athlete would know the venue; no instance-specific surprise such as a launch's exact speed), `difficulty` (two
sentences: what makes it hard for this robot). Plain words, metres and seconds, no formulas, no hint of a solution.

## The referee test (`tests/test_<family_snake>.py`, required)

A script with `main()` that asserts and prints `PASS <family>`, run by `dev.sh`. It must show:

- **nop fails**: `hold(w, A)` to the end → `failed` is set (and which reason).
- **a positive**: the referee says success. Preferably a real solution through the action interface. Where that is
  out of reach, an *injection*: set the simulator's state by hand (`rfo.testing.kick_robot`, `move_robot`, `w.put`,
  `w.launch`, `w.grab`) so that the sport's events really happen in physics (a ball that really flies through the
  ring; a robot that really leaves the ground and lands), and state in the test's docstring that it is an injection.
- **negatives**: at least one test per cheap exit of rule 6, each asserting the specific `failed` reason.
- **determinism**: the positive run twice gives the same `w.state_sha()`.

## The reference solution (`oracles/<family>/oracle.py`, optional)

```python
def solve(s):            # s: rcb_rfo.Session (privileged: s.world, s.state(), s.status())
    ...                  # drive s.step(type, row) until s.done; closed loop on privileged state is fine
```

It must succeed in at least 9 of 10 runs when the start is perturbed slightly (it is deterministic, so: it must not
sit on a knife edge; try two or three variations of its own gains) and finish in well under the time limit. A family
without one is fine (`oracle = "none"`, human review): say in your report what you tried and how far it got.

## Do not

Edit the core package or another family (report what you need instead; work around it inside your module), add
dependencies, use the network, write outside `scripts/roboolympics/` and your `RFO_OUT`, or commit.
