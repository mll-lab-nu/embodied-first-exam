# LIBERO-MAX

## Overview
[LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) (Zhang et al., 2026, arXiv 2609.36518) tests whether a robot
policy adapts when the world changes mid-task. Each case is a [LIBERO-PRO](https://github.com/Zxy-MLlab/LIBERO-PRO)
variant of a [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) task (Franka Panda at a table, robosuite /
MuJoCo) with one online event: the first time the gripper comes within 0.18 m of a task object, the scene changes once
(an object or its receptacle moves, an obstacle or distractors appear, the camera shifts, or the lighting, colours or
image noise change). 64 cases over 29 families (LIBERO suite × event), each in the privileged and standard modes: 128
task directories.

| | |
|---|---|
| upstream | LIBERO-MAX @ `a1e3cef` (event runtime and case parameters); LIBERO-PRO @ `2b910b5` (LIBERO package and assets); task data `zhouxueyang/LIBERO-Pro` @ `c86fc3b`; robosuite 1.4.0, MuJoCo 3.2.6 |
| tasks | `tasks/libero-max/libero-max-<suite>-<task>-<event>-iNN-privileged` and `-standard` |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda"`, `family = "libero-max/<suite>/<event>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/efe:libero-max-0.1.1` (`images/libero-max/`; `sha256:0e5b5e15aaeb761e4b66772a351f4195392fa638572d47bec5d924305c89aa99`), 3.5 GB |
| hardware | CPU only (MuJoCo physics, OSMesa rendering), no GPU; an x86-64 CPU with AVX-512 (Others, Host CPUs) |

```bash
harbor run -d embodied-first-exam@all -p tasks/libero-max -a codex -m openai/gpt-6-astra
```
Every image is public: Harbor pulls it.

## Upstream and license
- **LIBERO-MAX** ([liberomax/LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) @
  `a1e3cef258b3e00487db5282aef4e36010aaf401`; Zhang et al., [*LIBERO-MAX: Do Robot Policies Adapt When the World
  Changes?*](https://arxiv.org/abs/2609.36518), 2026) has no licence file. Two parts of it are used: (1) the event
  parameters and the case choice (the instances), (2) its event runtime in the image (`src/libero_max` and its source
  overlay; about 1,800 lines used: `substrate.py`, `pro_runtime.py`, `cosmos_integration.py`, `libero_backend.py`,
  `runtime.py`, `scenario.py`, `env_factory.py`). Its first author, Yunbei Zhang, gave written permission by email to
  redistribute both parts unmodified in this public repository and in a public Docker image, citing the paper and
  linking the repository:

  > I'm happy to grant permission to redistribute the two components as described. Please cite our paper and link to
  > the LIBERO-MAX repository. I'll also update the repository with a license soon.

  This page cites the paper and links the repository; when the repository adds a licence, the benchmark follows it.
  Both parts stay isolated: the instances are the only input that carries the parameters, so either part could be
  replaced by an own implementation of the same eight change types without touching the tools.
- **LIBERO-PRO** ([Zxy-MLlab/LIBERO-PRO](https://github.com/Zxy-MLlab/LIBERO-PRO) @
  `2b910b5b5f53016bef9907632f6f840f1ce2229c`): MIT, its LIBERO package and object assets; LIBERO itself is MIT. The
  task data (BDDL and initial-state files only) is LIBERO-PRO's Hugging Face dataset `zhouxueyang/LIBERO-Pro` @
  `c86fc3b8293185a6f373677018ff3e37f8391602`: CC BY 4.0.
- robosuite 1.4.0 (MIT) and MuJoCo 3.2.6 (Apache-2.0). No part is under a non-commercial licence.
- LIBERO-plus (no licence file, third-party TurboSquid assets) is a separate project and is not used.

## Changes from upstream
- **Only the Dynamic arm, only LIBERO-PRO cases.** LIBERO-MAX pairs a Base and a Dynamic rollout that share a policy's
  executed prefix. A coding agent is not a deterministic policy, so only the Dynamic case is a task (no paired
  Base/Dynamic statistic). Only LIBERO-PRO-derived cases (2,400 of LIBERO-MAX's 8,000) are used, because LIBERO-plus has
  no licence file.
- **Case choice** (deterministic; it looks at no policy outcome). Per event and suite, the cases in SHA-256-of-`case_id`
  order, duplicates (the same scene and change) dropped, the first 10 frozen (20 for `libero_10`); then per event the
  suites in turn, each time that suite's next case whose scripted reference succeeds (goals that move an articulated
  part first), up to 8 per event. Cases whose objects are wider than the gripper (moka pots, plates, a frying pan, a
  large soup can) or that place into the microwave have no reference and were not chosen.
- **Frozen instances.** `instance.json` holds the LIBERO-MAX case (LIBERO-PRO variant, initial-state index, policy
  seed, the frozen event with its trigger) and the hash of the simulator state the agent starts from, after LIBERO's 10
  warm-up no-op steps. The scene is rebuilt from the pinned upstream data by LIBERO-MAX's own code, and the rebuilt
  state is checked against the hash on every load. The extra seeds of a task (`tests/seeds/`) change only the
  initial-state index.
- **One simulator per process.** Some cases do not rebuild bit-exactly a second time in the same process, so
  `lmx_tool` refuses a second `Session` in one process, and every verification replay and every video pass runs in a
  fresh process.
- **Episode length.** robosuite's horizon is set beyond every limit (it refuses actions after its horizon; it does not
  touch the physics). Privileged trajectories keep LIBERO's evaluation horizons (220 / 280 / 300 / 520 control steps for
  `libero_spatial` / `libero_object` / `libero_goal` / `libero_10`); standard episodes have only a technical cap of
  9,000 control steps (450 s of robot time). The two modes share the goal but not the length rule.
- **Episode end, standard mode.** Upstream ends an episode the moment LIBERO's success check holds. In standard mode a
  success ends nothing: the episode ends at the agent's `/finish`, at the step cap or at the session's end, and is
  judged on the state it ends in. The privileged mode keeps upstream's rule.
- **Numeric kernels pinned.** The image sets `OPENBLAS_CORETYPE=Zen` so that the start states rebuild bit-exactly on
  every supported CPU (Others, Host CPUs).
- **Left out of the image:** LIBERO's demonstrations and dataset download utilities, LIBERO-MAX's policy runners,
  manifests, results and figures, every `.git`, and the Hugging Face client used to fetch the task data.
- **Added:** the tooling `lmx_tool.py`, the verifiers and the standard-mode service
  (`embodied_first_exam/benchmarks/libero-max/`).

## Interface
- **Actions** (both modes): LIBERO's native action `[dx, dy, dz, drx, dry, drz, grip]` in [-1, 1], one per control step
  (1/20 s). The OSC_POSE controller moves the hand's target by up to 0.05 m and turns it by up to 0.5 rad (axis-angle,
  world frame) per step; grip +1 closes, -1 opens.
- **World frame:** metres; the robot's base (fixed mount) at (-0.66, 0, 0.912) facing +x: x forward, y left, z up;
  quaternions w x y z.
- **Event.** LIBERO-MAX's frozen change and trigger: at the first control step on which the hand is within 0.18 m of
  the trigger object (LIBERO-MAX's `distance_to_entity`), LIBERO-MAX's backend applies the change once (objects or
  fixtures moved, objects brought in, the camera's pose and field of view, the lighting, the image transform for the
  colour theme and the sensor noise). It is applied identically in the agent's tool, the verifier's replay and the
  standard service.
- **Privileged:** `/opt/tools/lmx_tool.py` (`Session`): the frozen scene, `step`, privileged state (every object's
  pose, the articulations, the goal), LIBERO's success check, cameras, `save_trajectory`, `replay_fresh`. The
  deliverable is `/app/output/trajectory.npz` (`actions`, shape (T, 7)).
- **Standard** (protocol `eai-standard/3.0`): the service in the `sim` sidecar, action type `ee_delta`. Cameras
  `agentview` (fixed) and `wrist` (`robot0_eye_in_hand`), RGB 256×256, metric depth on request, upright images with
  LIBERO-PRO's pixel perturbation of the variant and, after the event, LIBERO-MAX's image change. Intrinsics and pose
  are in `/spec` at the start and the current ones in every submit reply (`meta.cameras_now`: a camera_shift event moves
  agentview and changes its field of view). Proprioception: hand pose, finger positions, joint positions and velocities,
  the last command. The agent is told that the scene may change once (which kinds of change), not which change or when.
  No object poses, no goal, no success signal. One episode, no reset.

## Grading
- **Success** is LIBERO's success check: the AND of the variant's BDDL goal predicates (`On`, `In`, `Close`, `TurnOn`,
  `TurnOff`), with LIBERO's own geometry and thresholds. Each task README states its goal with the numbers. Two LIBERO
  rules matter: `In` of a region (a basket's or a drawer's) checks only that the object's origin lies in the region's
  box, never contact; `On` of an object needs contact and origins less than 3 cm apart horizontally.
- **Privileged: one replay.** `tests/grade.py` replays the trajectory once, open-loop, in a fresh process from the
  verifier's own copy of the instance. LIBERO ends the episode the moment its check holds, so success means the check
  first holds on the last row; rows after it make the trajectory invalid. 1 ≤ T ≤ the suite's limit. A host that does not
  rebuild the start state is `grader_error = infra_error = 1`; a replay process that fails is `grader_error = 1`.
- **Standard: the live episode.** Nothing is replayed to grade it. Every standard task runs agent-ended episodes
  (`RCB_AGENT_END=1`): `lmx_tool.Session` reports LIBERO's check as things stand and keeps stepping, and the episode is
  judged on its end state (no settle or hold window; LIBERO's check has none). The service checks the start state
  against the instance's hash when the episode begins (`instance_mismatch`, an infrastructure failure);
  `live_verdict()` adds LIBERO-MAX's event record (`event_fired`, `event_step`) to `final.json`. `tests/grade.py`:
  `success = live_success ∧ graded_by = "live" ∧ finalized ∧ ¬infra`, a simulator error is the agent's 0.
- **Grading (standard mode): the video and the collect budget.** Every frame here is an OSMesa render (about 70 ms at
  256×256, 0.24 s on a busy host), so the episode is not recorded live. Once `final.json` is finalized,
  `server.py` `render_video()` replays `trajectory.npz` once in a fresh process with the
  agentview camera on and writes `replay.video.json` (whether the replay ended in the live end state). A failure, a
  timeout or a crash costs only the video. The collect hook (`finalize.sh`) signals the service every 30 s until
  `final.json` is finalized, then waits for the video. **Collect budget:** the video pass of N control
  steps takes B + N × s + V, with B ≤ 180 s to build the scene, s = 0.5 s per control step on a busy host (about 0.1 s
  on a quiet one) and V ≤ 240 s of frames (`lmx_tool._ReplayVideo`: one frame per `video_stride` control steps, frames
  skipped once the time spent exceeds 240 s × the fraction replayed; `LMX_VIDEO_BUDGET_S`, `LMX_VIDEO_MAX_FRAMES`). For
  N = 9,000 that is 4,920 s; `RCB_COLLECT_WAIT_S` and `RCB_VIDEO_TIMEOUT_S` are 5,400 s, and the hook's `timeout_sec`
  is 180 + 5,400 + 120 = 5,700 s (up to 180 s for the service's PID file, 120 s of slack).

## Tasks
Families are `libero-max/<suite>/<event>`; the number of cases (each one privileged and one standard task):

| event | `libero_spatial` | `libero_object` | `libero_goal` | `libero_10` | total |
|---|---|---|---|---|---|
| `camera_shift` | 2 | 2 | 2 | 2 | 8 |
| `distractor_burst` | – | 7 | – | 1 | 8 |
| `illumination_switch` | 2 | 2 | 2 | 2 | 8 |
| `obstacle_insertion` | 3 | – | 3 | 2 | 8 |
| `receptacle_relocation` | 2 | 2 | 2 | 2 | 8 |
| `sensor_noise_onset` | 2 | 2 | 2 | 2 | 8 |
| `target_relocation` | 3 | 2 | 2 | 1 | 8 |
| `visual_theme_switch` | 2 | 2 | 2 | 2 | 8 |
| total | 16 | 19 | 15 | 14 | 64 |

LIBERO-MAX has no `obstacle_insertion` case for `libero_object`, and `distractor_burst` only for `libero_object` and
`libero_10`. Goals: 57 pick-and-place (`On` / `In`), 5 stove knobs (4 `TurnOn`, 1 `TurnOff`), 2 a bowl into the
bottom drawer that is then closed (`In` + `Close`). Every task has a reference solution (`solution/oracle.npy`, the same
in both modes of a case; the case is the instance's `case.case_id`, not the task name).

- **Instances.** Each case's `instance.json` is committed in three byte-identical copies: the privileged task's
  `environment/instance.json` and `tests/instance.json` and the standard task's `environment/sim/instance.json`
  (`check-instance-copies.sh`).
- **Moves.** A move event (`target_relocation`, `receptacle_relocation`) sets one entity's position
  (`libero_backend._move_object`): what rests in or on a moved receptacle stays behind, and an entity that lands on
  another is pushed apart by the physics. Both instructions say so.
- **Left and right.** In the four cases of `LIVING_ROOM_SCENE5_put_the_white_mug_on_the_left_plate...`, LIBERO's left
  plate (`plate_1`, in `plate_left_region`) is on the robot's right; the instructions say that left and right are as
  seen facing the robot.
- **The caddy's back compartment.** In `STUDY_SCENE1_..._back_compartment_of_the_caddy` with the mug (LIBERO-PRO's task
  variant replaces the book), the back compartment is the narrow back cell, about 5.5 cm across, narrower than the mug.
  LIBERO's `In` holds once the mug's origin is inside the region's box, so a mug resting on its opening counts. The
  instructions say so; the check is unchanged.
- **Shifted bowls.** The `initial_pose_position_angle` cases of `pick_up_the_black_bowl_{on,next_to}_the_cookie_box...`
  shift the target bowl 0.17 m in x and -0.06 m in y and turn it 45 degrees, so the sentence's spatial relation no
  longer holds; the instructions say which bowl is meant.

## Others
- **Host CPUs.** The start state is bit-exact only with the numeric kernels it was frozen with, because robosuite's
  OSC controller and LIBERO run on numpy and scipy. Two parts of the stack choose kernels by CPU at run time:
  - OpenBLAS: numpy 1.22.4 and scipy 1.10.1 bundle OpenBLAS 0.3.18, which picks Zen kernels on the reference AMD
    Ryzen 9 7950X but its generic Prescott (SSE3) kernels on CPUs it does not know (Intel Xeon Platinum 8488C). The
    image sets `OPENBLAS_CORETYPE=Zen` (AVX2 + FMA kernels; a build-time check asserts both libraries use them).
  - numpy's own SIMD loops: the frozen hashes use its AVX-512 loops. The reference CPU and the Intel Xeon Platinum 8488C
    dispatch the same targets, up to `AVX512_ICL`; an AVX2-only CPU (AMD EPYC 7R13, Zen 3) rebuilds only some
    instances. Run LIBERO-MAX on hosts that dispatch like them: Intel Ice Lake or newer Xeon, AMD Zen 4 or newer.
  - There is no tolerance: a state off by rounding grows over a contact-rich episode. On a host whose kernels differ,
    every `Session` refuses, and the error names the kernels in use (`lmx_tool.numerics()`).
- **Cost.** About 20 ms of physics per control step and about 70 ms per 256×256 camera image (OSMesa) on the reference
  machine; busy hosts are several times slower. A privileged trial's verifier needs one fresh replay plus a video
  replay; the standard verdict is out within seconds of the collect hook's signal.
- **Rebuilding the image.**
  ```bash
  docker build -t ghcr.io/mll-lab-nu/efe:libero-max-$(cat images/libero-max/VERSION) -f images/libero-max/Dockerfile .
  ```
