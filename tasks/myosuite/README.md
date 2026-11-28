# MyoSuite

## Overview

Muscle-level control of musculoskeletal human models: twenty-two MyoSuite tasks, from turning a key and twirling a pen
to returning a table tennis serve, handing an object to a prosthetic arm, kicking a goal and running with a powered
prosthetic leg. The main command is one excitation per muscle (a few families add non-muscle actuators: a positioned
wrist, two pelvis slides, the prosthesis's motors). There is no joint-level controller: every motion, grasp and in-hand
manipulation has to be built from muscle commands. 22 families in two modes, plus a realtime version of table_tennis:
45 task directories, `tasks/myosuite/myosuite-<family>-i00-privileged`, `-standard` and
`myosuite-table-tennis-i00-realtime`.

| | |
|---|---|
| upstream | [MyoSuite](https://github.com/MyoHub/myosuite) (Caggiano et al., 2022), version 2.12.2 (tag `v2.12.2`, `5635e1a`), with MyoChallenge 2022-2025 and MyoDex |
| simulator | MuJoCo 3.6.0, CPU physics; OSMesa rendering (EGL on a GPU in the realtime task) |
| bodies | MyoHand (39 muscles); MyoArm (34 or 63 muscles); MyoArm with torso (273 muscles + 2 pelvis slides); MyoArm next to the MPL prosthetic arm (17 motors); MyoLegs (80 or 290 muscles); MyoLeg with the OSL knee-ankle prosthesis (54 muscles) |
| score | MyoSuite's own `solved` held for a hold time, a MyoChallenge's own success event, or (MyoDex) our tracking rule on its reference motion |
| image | `ghcr.io/mll-lab-nu/efe:myosuite-0.1.1` (`images/myosuite/`) |

Quick start:
```bash
harbor run -d embodied-first-exam@all -p tasks/myosuite -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

| mode | the agent gets | resets | graded |
|---|---|---|---|
| privileged | `rcb_myosuite.Session`: the task's observation dict, MuJoCo model and data, actuator descriptions and moment arms, rendering, recording and self-replay | unlimited | `trajectory.npz`, replayed once in a fresh process |
| standard | the cameras, the body's own joints and muscles, `/kinematics`; muscle or actuator rows | 10 | the live episode, as it ran (nothing replayed) |
| realtime (table_tennis) | the same on a clock that does not stop | 10 | as standard |

## Upstream and license

- Upstream: MyoSuite, [MyoHub/myosuite](https://github.com/MyoHub/myosuite), version 2.12.2 from PyPI (tag `v2.12.2`,
  `5635e1a61c63b0363fa8b289c8cc137f0e4c736d`). Apache License 2.0.
- Models: MyoSim, the MPL arm and the object, furniture and YCB models bundled with MyoSuite, Apache License 2.0.
- MyoDex reference motions (the six `dex_*` families): derived from the GRAB motion-capture dataset; MyoSuite asks
  their users to comply with GRAB's licence (non-commercial scientific research).
- Simulator: MuJoCo 3.6.0 (Apache License 2.0).

## Changes from upstream

- **Instance.** One frozen instance per family: the env after `seed(0)` and then `reset(seed=0)`, saved with the
  MuJoCo integration state, every numeric model array (resets edit the model: goal sites, object sizes), the env's
  Python-side state and a state hash every load checks. The MyoChallenge envs draw their goal, mass or size inside
  `reset()` before `reset(seed=)` reseeds, so the env is seeded first.
- **Episode state.** For the challenge and MyoDex families, every reset restores the env's random generator and its
  Python-side objects (the OSL controller, the opponent and goalkeeper policies, MyoDex's reference cursor). The
  opponent and the goalkeeper are mocap bodies that MyoSuite moves in a mirror of the physics data, so their poses are
  saved too. Snapshots and the state hash use the robot wrapper's own MjData, where MyoSuite steps the physics.
- **Step budget.** MyoSuite's gym step limit (50 to 2,000 steps) is lifted; each task's own failures and time limits
  still apply.
- **Hold.** For the ten single-hand and arm tasks and sarc_key_turn, MyoSuite's `solved` must hold for 1 s of
  consecutive control steps (baoding: 5 s, one full circle of its moving targets). Baoding's targets are a
  precomputed path of 1,000 points, so its episode ends after 1,000 control steps.
- **MyoChallenge.** The challenge's own `solved` is the success event. bimanual counts the first `solved` step with
  its own contact check (MyoChallenge's evaluation counts more than 5 `solved` steps, but the env ends the episode one
  step after the first). osl_run asks for the finish line without a time limit (its official score is the distance
  reached within 1,000 steps). table_tennis ends the episode as a failure when the challenge's own contact test finds
  the rally lost (a second paddle touch, a second own-half bounce, the opponent's half without a hit): MyoSuite's
  `done` means to, but compares that test's enum with ints and never fires.
- **MyoDex.** MyoDex defines a dense reward only (its `solved` is always 0). Our rule: the object's motion since the
  start follows the reference's within 3 cm (and 0.5 rad of rotation for the four families where orientation is the
  point of the skill) at 90% or more of the control steps and at the last one, with the displacement error never
  above 5 cm, and no MyoDex termination (object or wrist 0.25 m off).
- **Image.** MyoSuite 2.12.2's Bimanual, Soccer and ChaseTag envs call `float()` on one-element arrays, which numpy
  2.4 rejects: the image pins numpy 2.3.5. MyoSuite's NPG baseline policies are removed from the image in the layer
  that installs MyoSuite.

## Interface

- **Privileged.** `/opt/tools/rcb_myosuite.py` (`from rcb_myosuite import Session`): `Session(task, instance)`,
  `reset()` (unlimited), `state()` (the task's observation dict), `muscles()`, `joints()`, `actuators()`,
  `moment_arms()`, `model` / `data`, `step(a)`, `status()`, `render_frame(cam)`, `record_start()` /
  `record_stop()`, `replay(rows)`, `save_trajectory(rows, path)`, `render_video(rows, path)`. One action row holds one
  real number per actuator; for a muscle, excitation u = 1 / (1 + exp(-5 (a - 0.5))), not clipped.
- **Standard.** The `sim` sidecar serves `GET /spec`, `GET /status`, `POST /observe`, `POST /submit`, `POST /finish`,
  `POST /kinematics` and `POST /reset` through `rcb_client.py` and the `efe-robot` MCP tools (wire protocol
  `eai-standard/3.0`).
  - Action type `muscle` (all-muscle bodies) or `actuators` (with the non-muscle ones: MyoDex's 6-DoF wrist
    positioning, table tennis's pelvis slides, the MPL prosthesis's motors; osl_run's prosthesis columns are ignored,
    MyoSuite's own controller drives it). Nothing is clipped by the service; each non-muscle actuator's command is in
    `/spec`.
  - Every camera of the scene, 640 x 480, depth on request, with its mount. A camera that rides on a body of the scene
    (chase_tag's `opponent_view`, soccer's `goalkeeper_view`) gives images only: no pose, since its pose would be that
    body's position.
  - Proprioception: the body's own joints (`q_`, `qd_`, `effort_`) and muscles (`act_`, `len_`), plus the pelvis pose
    and velocity of the free-standing bodies. Never the key, pen, die, balls, objects, opponent or goalkeeper.
    MyoDex's reference motion (relative to the object's start) is in `/spec` `reference_motion`.
  - `/kinematics`: the fingertip sites and the camera mounts, and fingertip-position IK.
  - `POST /reset` abandons the running episode, or follows one that has ended, and restores the frozen instance; the
    client has no `reset()`, so the instructions call it through `Robot._post`. One call returns at most 1000
    images. A malformed request field is a 400 before anything runs.
- **Realtime (table_tennis).** The shared realtime layer with the standard task's frozen instance, action, success rule,
  proprioception and cameras, on a clock that does not stop (one 10 ms control step per 10 ms of wall time at
  slowdown 1); when the plan runs out the last row is held. Rendering uses EGL on a GPU, as an OSMesa frame of this
  scene takes about 1.3 s.

## Grading

- **Success rules** (each task's README states its family's rule with every threshold):
  - *hold*: MyoSuite's `solved` held for the hold time in consecutive control steps; MyoSuite's `done` is a failure.
  - *event*: the challenge's own success event (bimanual: with its contact check); its failures (table_tennis: also
    a lost rally) and time limits (table_tennis 3 s, bimanual 10 s, soccer 10 s, chase_tag 20 s; osl_run none) end the
    episode with 0 before it.
  - *track*: the whole reference motion (57 to 99 control steps), judged at its end; MyoDex's termination is a
    failure.
- **Privileged.** `tests/grade.py` checks `trajectory.npz` (readable, this family, shape (T, actuators), finite, at
  most the family's row limit, which its instruction states; no `.npz` entry larger than those rows) and replays it
  once in a fresh process. The replay ends at the first success, at a failure, or when the rows run out (0). A replay
  that gives no result, or a frozen start that does not rebuild with its recorded hash, is `grader_error` with
  `infra_error`. A second replay renders `replay.mp4` after the verdict, in the verifier's time left.
- **Standard and realtime.** The service judges the live episode. A success is never shown and never ends the episode.
  The episode ends at `/finish`, at a failure, at the episode's own end (MyoDex's reference motion, baoding's 1,000
  target points) or at the end of the agent's time. A hold is judged on the state the episode ends in; at `/finish` or
  the session's end a hold that has begun is run out from that state with the last command held. A challenge's event
  counts once it has happened, also when a failure ends the episode later. 10 resets; only the last episode is graded.
  The frozen start is checked when the episode begins (`instance_mismatch`, infrastructure). A simulator error from
  the agent's actions is the agent's 0. The video is one render pass after the verdict and never changes it.

## Tasks

| family | MyoSuite env | body (muscles) | control step | rule |
|---|---|---|---|---|
| `key_turn` | `myoHandKeyTurnFixed-v0` | MyoHand (39) | 20 ms | hold 1 s |
| `obj_hold` | `myoHandObjHoldFixed-v0` | MyoHand (39) | 20 ms | hold 1 s |
| `arm_reach` | `myoArmReachFixed-v0` | MyoArm (34) | 20 ms | hold 1 s |
| `hand_reach` | `myoHandReachFixed-v0` | MyoHand (39) | 20 ms | hold 1 s |
| `hand_pose` | `myoHandPoseFixed-v0` | MyoHand (39) | 20 ms | hold 1 s |
| `pen_twirl` | `myoHandPenTwirlFixed-v0` | MyoHand (39) | 10 ms | hold 1 s |
| `die_reorient` | `myoChallengeDieReorientP1-v0` | MyoHand (39) | 10 ms | hold 1 s |
| `obj_reorient` | `myoHandReorient8-v0` | MyoHand (39) | 10 ms | hold 1 s |
| `baoding` | `myoChallengeBaodingP1-v1` | MyoHand (39) | 25 ms | hold 5 s (one orbit) |
| `relocate` | `myoChallengeRelocateP1-v0` | MyoArm (63) | 10 ms | hold 1 s |
| `sarc_key_turn` | `myoSarcHandKeyTurnFixed-v0` | MyoHand (39, half force) | 20 ms | hold 1 s |
| `table_tennis` | `myoChallengeTableTennisP1-v0` | MyoArm with torso (273 + 2 pelvis slides) | 10 ms | event |
| `bimanual` | `myoChallengeBimanual-v0` | MyoArm (63) + MPL arm (17 motors) | 10 ms | event + contact check |
| `soccer` | `myoChallengeSoccerP1-v0` | MyoLegs (290) | 10 ms | event |
| `chase_tag` | `myoChallengeChaseTagP1-v0` | MyoLegs (80) | 10 ms | event |
| `osl_run` | `myoChallengeOslRunFixed-v0` | MyoLeg (54) + OSL prosthesis | 5 ms | event |
| `dex_apple_lift` | `MyoHandAppleLift-v0` | MyoHand (39) + 6-DoF wrist | 20 ms | track (57 steps) |
| `dex_cylinder_pass` | `MyoHandCylindersmallPass-v0` | MyoHand + wrist | 20 ms | track (86) |
| `dex_bunny_inspect` | `MyoHandStanfordbunnyInspect-v0` | MyoHand + wrist | 20 ms | track (99, with orientation) |
| `dex_hammer_use` | `MyoHandHammerUse-v0` | MyoHand + wrist | 20 ms | track (99, with orientation) |
| `dex_cup_pour` | `MyoHandCupPour-v0` | MyoHand + wrist | 20 ms | track (81, with orientation) |
| `dex_airplane_fly` | `MyoHandAirplaneFly-v0` | MyoHand + wrist | 20 ms | track (99, with orientation) |

table_tennis is the benchmark's one dynamic family (the ball is served at reset), so it alone has a realtime task;
every other family's objects start at rest, and chase_tag's opponent stands still in its frozen instance.

Selection rule: MyoSuite 2.12.2 registers 398 env ids, most of them variants (50 MyoDex objects with Fixed, Random and
motion envs; the basic tasks with Fatigue, Sarcopenia and Reafferentation; the challenges in P1, P2 and evaluation
forms). One task is kept per distinct capability, each deterministic (repeated replays in one process and in a fresh
process give the same final state):

| category | families | why |
|---|---|---|
| single hand and arm | key_turn, obj_hold, arm_reach, hand_reach, hand_pose, pen_twirl, die_reorient, obj_reorient, baoding, relocate | MyoSuite's base tasks and the hand challenges, fixed goal |
| muscle condition | sarc_key_turn | the same key turn with every muscle at half force (sarcopenia, a stateless change); fatigue (a stateful model) and reafferentation (a tendon transfer) are not used |
| MyoChallenge 2023-2025 | table_tennis, bimanual, soccer, chase_tag, osl_run | dynamic interception with a held tool; a hand-over to a prosthesis; whole-body locomotion to a ball and a kick; locomotion to an opponent; running with a powered prosthesis. P1 or Fixed variants (fixed start) |
| MyoDex object motions | dex_apple_lift, dex_cylinder_pass, dex_bunny_inspect, dex_hammer_use, dex_cup_pour, dex_airplane_fly | lift, pass, inspect, tool use, pour, fly: one per skill |

Not used: MyoDex's Fixed and Random repositioning envs (their reference starts 0.57 m from the object while MyoDex's
termination fires beyond 0.25 m, so the episode ends at the first step whatever the action); the other MyoDex motions
(near-duplicates of the six skills); the challenges' P2 and evaluation variants (wider randomization, which a frozen
instance does not keep); leg walking and standing and torso posing (covered by the locomotion challenges and
hand_pose); elbow and finger pose and reach (near-duplicates of hand_pose and hand_reach).

## Others

- **Reference solutions.** key_turn, obj_hold and arm_reach include one (`oracle = "full"`): MyoSuite's own NPG
  baseline policies rolled out from the frozen instance and cut at the first success (72, 57 and 128 rows), rounded
  to float32 so that both modes execute the same rows. The other nineteen families have none.
- **Where upstream holds answers.** The PyPI wheel ships the NPG baselines (the reference solutions of three
  families), and an agent could pip-install `myosuite==2.12.2` and rebuild the simulator locally to plan offline. The
  agent's network is the model APIs and the package registries only; the instruction asks the agent not to fetch a
  solution, and a trial that installs `myosuite`, `myo-sim` or `robohive` is one to look at. GitHub and Hugging Face
  stay unreachable.
- **Files.** Each task directory carries its frozen instance (`instance.npz`) and, where its family has one, its
  reference solution. The shared code (the tool `rcb_myosuite.py`, the graders, the standard service `server.py` with
  `video.py` and `finalize.sh`) is in `embodied_first_exam/benchmarks/myosuite/` (the realtime task's `rcb_service.py`: `standard-files`);
  the task Dockerfiles copy it by digest from the files-only image `efe:myosuite-files-<images/myosuite-files/VERSION>`.
  Build the base image from the repository root:
  `docker build -f images/myosuite/Dockerfile -t ghcr.io/mll-lab-nu/efe:myosuite-$(cat images/myosuite/VERSION) .`
