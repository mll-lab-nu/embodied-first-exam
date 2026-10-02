# LIBERO-MAX

Robot manipulation with a change mid-task: [LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX) cases built on
[LIBERO-PRO](https://github.com/Zxy-MLlab/LIBERO-PRO) variants of [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO)
tasks, each with one online event, in both modes: 48 cases, 96 tasks.

| | |
|---|---|
| upstream | LIBERO-MAX @ `a1e3cef` (benchmark 3.0.0; event runtime and case parameters); LIBERO-PRO @ `2b910b5` (MIT; LIBERO package and assets), task data `zhouxueyang/LIBERO-Pro` @ `c86fc3b` (CC-BY-4.0); robosuite 1.4.0, MuJoCo 3.2.6 |
| tasks | `tasks/libero-max-<suite>-<task>-<event>-iNN-privileged` and `...-standard` |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda"`, `family = "libero-max/<suite>/<event>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-libero-max:0.1.0` (`images/libero-max/`), 3.5 GB, CPU only |
| standard client | the shared client base and pins of `scripts/eai_standard/`; `rcb_client.py`, `rcb1.py` and the standard `grade.py` are byte copies of main's (HumanoidBench / VLABench); `rcb_service.py` is too, plus one hook (3 lines): `verify()` may return `extra`, merged into the verdict, which LIBERO-MAX uses to record `event_fired` / `event_step` (live) and `replay_event_fired` / `replay_event_step` in `final.json` (evidence only, never part of the success rule; a candidate to upstream to the shared service) |
| generator | `scripts/libero-max/` (`select_cases.py` → `cases.json`, `freeze.sh` → `frozen/`, `generate.py` → `tasks/`, `generate.py --check`) |

## Task definition
- **Cases.** LIBERO-MAX pairs a Base and a Dynamic rollout that share the policy's executed prefix; a coding agent is
  not a deterministic policy, so only the Dynamic case is a task here (no paired Base/Dynamic statistic; a Base twin can
  be added as a separate instance). Only LIBERO-PRO-derived cases (2,400 of 8,000) are used: LIBERO-plus has no licence
  file and ships third-party (TurboSquid) assets. The choice is deterministic and looks at no policy outcome
  (`select_cases.py`): per event, cases in SHA-256-of-`case_id` order, duplicates (same scene and change) dropped, the
  first 20 frozen; then the first verified case of each suite, then the next verified ones, up to 6 per event.
  Result: 160 candidates, 80 verified, 48 chosen (6 per event; object 21, spatial 13, goal 11, libero_10 3).
  The 112 not chosen are listed in `cases.json` with their reason: 48 whose scripted reference failed, 32 without one
  (Open / Close / TurnOn goals, plates and mugs wider than the gripper), 32 verified but not needed.
- **Instance.** `instance.json` holds the LIBERO-MAX case (LIBERO-PRO variant, initial-state index, policy seed, the
  frozen event with its trigger) and the hash of the simulator state the agent starts from (after LIBERO's 10 warm-up
  no-op steps). The scene is rebuilt from the pinned upstream data in the image by LIBERO-MAX's own code, and the
  rebuilt state is checked against the hash on every load.
- **One simulator per process.** In the spike, 2 of 14 cases (a LIBERO-plus Sensor-Noise variant and a LIBERO-PRO
  camera_view_angle variant) did not rebuild bit-exactly a second time in the same process. `lmx_tool` therefore
  refuses a second Session in one process (loudly, with the reason), and every verification replay and replay video
  runs in a fresh process (privileged grader, standard service).
- **Event.** LIBERO-MAX's frozen change and trigger: the first control step at which the gripper is within the case's
  distance (0.18 m) of the trigger object (LIBERO-MAX's `distance_to_entity`), the change is applied once by
  LIBERO-MAX's backend (objects or fixtures moved, objects parked off-scene at reset brought in, camera pose and field
  of view, lighting, the image transform for colour theme and sensor noise). Applied identically in the agent's tool,
  the verifier's replays and the standard service; the replays reproduce the trigger step.
- **Actions.** LIBERO's native action in both modes, `[dx, dy, dz, drx, dry, drz, grip]` in [-1, 1], one per control
  step (1/20 s): the OSC_POSE controller moves the hand's target by up to 0.05 m and turns it by up to 0.5 rad
  (axis-angle, world frame) per step; grip +1 closes, -1 opens. In standard mode the type is `ee_delta` (action types
  are benchmark-defined, PROTOCOL §4.4 since #31).
- **Success and episode end.** LIBERO's success check (the BDDL goal: LIBERO's On / In predicates with their real
  thresholds, stated per task in both instructions). LIBERO ends the episode the moment it holds (`done`), so the graded
  state is the trajectory's final state: a privileged trajectory with actions after that is invalid, and the standard
  service ends the episode with `reason = "success"` there.
- **Length.** Privileged deliverables have 1 ≤ T ≤ the suite's limit (220 / 280 / 300 / 520 control steps, LIBERO's
  evaluation horizons), counted after the 10 warm-up steps. Standard episodes have only a technical cap of 9,000 control
  steps (450 s of robot time) so that the fresh grading replay fits the collect hook's timeout. LIBERO's environment is
  built with a horizon beyond both (robosuite refuses actions after its horizon; it does not touch the physics).
- **World frame.** Metres; the robot's base (fixed mount) at (-0.66, 0, 0.912) facing +x: x forward, y left, z up.
- **Standard observations.** `agentview` (fixed) and `wrist` (`robot0_eye_in_hand`), RGB 256×256, metric depth on
  request, upright images with LIBERO-PRO's pixel perturbation of the variant and, after the event, LIBERO-MAX's image
  change applied; intrinsics and pose in `/spec` at the start and the current ones in every submit response
  (`meta.cameras_now`: a camera_shift event moves agentview and changes its field of view). Proprioception: hand pose,
  finger positions, joint positions and velocities, last command. The agent is told that the scene may change once
  (what kinds of change), not which change or when. No object poses, no goal, no success signal.

## Licence-dependent parts
LIBERO-MAX has no licence file. Two parts depend on it: (1) the event parameters and case choice (`cases.json`, and the
instances made from it), (2) LIBERO-MAX's event runtime in the image (`src/libero_max`, about 1,800 lines used:
`substrate.py`, `pro_runtime.py`, `cosmos_integration.py`, `libero_backend.py`, `runtime.py`, `scenario.py`,
`env_factory.py`). If LIBERO-MAX's authors do not grant redistribution: replace (1) with independently drawn parameters of
the same eight change types (`cases.json` is the only input that carries them; the generator and tools are unchanged),
and (2) with an own implementation of the same operations in `lmx_tool.py`; until then the image can be `BUILD_ONLY`.
LIBERO-PRO (MIT / CC-BY-4.0) and LIBERO (MIT) need nothing beyond attribution.

## Rebuilding
```bash
docker build -t ghcr.io/mll-lab-nu/eai-libero-max:$(cat images/libero-max/VERSION) -f images/libero-max/Dockerfile .
python3 scripts/libero-max/select_cases.py candidates <LIBERO-MAX>/benchmark/max8000/libero_max_8000.json candidates.json
bash scripts/libero-max/freeze.sh candidates.json frozen-candidates 12      # ~2 min per case, one container each
python3 scripts/libero-max/select_cases.py pick candidates.json frozen-candidates scripts/libero-max/cases.json
bash scripts/libero-max/freeze.sh                                          # the chosen cases -> scripts/libero-max/frozen/
python3 scripts/libero-max/generate.py && python3 scripts/libero-max/generate.py --check
cd tasks && harbor add --scan . && cd .. && bash ci_checks/run_all.sh
```

## Evidence
| check | result |
|---|---|
| freeze (`freeze.sh`, eai-libero-max:0.1.0), 48 cases | not solved at the start 48/48; reference succeeds at its last step 48/48 (116–321 steps; the event fires at step 5–36); two fresh-process replays = live hash 48/48 |
| same cases frozen in the spike image (same pins, sources mounted) | identical initial and final hashes 48/48 |
| `harbor run -a oracle`, privileged | 48/48 reward 1 (deterministic, event fired, no errors) |
| `harbor run -a oracle`, standard (one case per event) | 8/8 reward 1 (live = replay, deterministic) |
| `harbor run -a nop` | 4/4 privileged and 4/4 standard reward 0 |
| scripted cheat attempts (patched tooling and success check, forged reward files, `sitecustomize.py`, tampered instance copy; hidden endpoints, wrong action type and `dt`, NaN rows, forged `final.json`) | privileged 0, standard 0; hidden endpoints 404, malformed submits 400 |
| `generate.py --check`, `task_conventions.py --check`, `ci_checks/run_all.sh` | clean; no LIBERO-MAX warnings |

Measured on the reference machine (AMD Ryzen 9 7950X): about 20 ms of physics per control step, about 70 ms per
256×256 camera image (OSMesa); a privileged oracle trial takes 2–3 min, most of it the verifier's two fresh replays.
