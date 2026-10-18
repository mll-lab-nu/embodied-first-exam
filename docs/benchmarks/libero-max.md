# LIBERO-MAX

Robot manipulation with a change mid-task: [LIBERO-MAX](https://github.com/liberomax/LIBERO-MAX)
([paper](https://arxiv.org/abs/2609.36518)) cases built on
[LIBERO-PRO](https://github.com/Zxy-MLlab/LIBERO-PRO) variants of [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO)
tasks, each with one online event, in both modes: 64 cases, 128 tasks.

| | |
|---|---|
| upstream | LIBERO-MAX @ `a1e3cef` (benchmark 3.0.0; event runtime and case parameters); LIBERO-PRO @ `2b910b5` (MIT; LIBERO package and assets), task data `zhouxueyang/LIBERO-Pro` @ `c86fc3b` (CC-BY-4.0); robosuite 1.4.0, MuJoCo 3.2.6 |
| tasks | `tasks/libero-max-<suite>-<task>-<event>-iNN-privileged` and `...-standard` |
| metadata | `simulator = "robosuite"`, `robot = "franka-panda"`, `family = "libero-max/<suite>/<event>"`, `oracle = "full"` |
| image | `ghcr.io/mll-lab-nu/eai-libero-max:0.1.1` (`images/libero-max/`; `sha256:0e5b5e15aaeb761e4b66772a351f4195392fa638572d47bec5d924305c89aa99`), 3.5 GB, CPU only; x86-64 with AVX-512 (see Host CPUs) |
| standard client | the shared client base and pins of `scripts/eai_standard/`; `rcb_client.py` and `rcb1.py` are byte copies of main's (HumanoidBench / VLABench); the standard `grade.py` is LIBERO-MAX's own (every path writes the same `reward.json` fields; it grades the live episode); `rcb_service.py` is a byte copy (the shared service's `live_verdict()` carries LIBERO-MAX's event record, `event_fired` / `event_step`, into `final.json`) |
| generator | `scripts/libero-max/` (`select_cases.py` → `cases.json`, `freeze.sh` → `frozen/`, `generate.py` → `tasks/`, `generate.py --check`) |

## Task definition
- **Cases.** LIBERO-MAX pairs a Base and a Dynamic rollout that share the policy's executed prefix; a coding agent is
  not a deterministic policy, so only the Dynamic case is a task here (no paired Base/Dynamic statistic; a Base twin can
  be added as a separate instance). Only LIBERO-PRO-derived cases (2,400 of 8,000) are used: LIBERO-plus has no licence
  file and ships third-party (TurboSquid) assets. The choice is deterministic and looks at no policy outcome
  (`select_cases.py`): per event and suite, cases in SHA-256-of-`case_id` order, duplicates (same scene and change)
  dropped, the first 10 frozen (20 for libero_10, whose long tasks the scripted reference solves less often); then per
  event the suites in turn, each time that suite's next verified case (goals that move an articulated part first), up
  to 8 per event. Result: 370 candidates, 179 verified, 64 chosen (8 per event; object 19, spatial 16, goal 15,
  libero_10 14: LIBERO-MAX has no obstacle_insertion case for libero_object and distractor_burst only for libero_object
  and libero_10). Goals: 57 pick-and-place (On / In), 5 stove knobs (4 TurnOn, 1 TurnOff), 2 a bowl into the bottom
  drawer that is then closed (In + Close). The 306 not chosen are listed in `cases.json` with their reason: 144 whose
  scripted reference failed (mostly crowded grasps, a white cabinet's bottom drawer the arm cannot push fully shut,
  opening the middle drawer: the hand stops above its handle), 47 without one (moka pots, plates, a frying pan and a large soup can
  wider than the gripper; placing into the microwave, which needs a sideways approach), 115 verified but not needed.
- **Instance.** `instance.json` holds the LIBERO-MAX case (LIBERO-PRO variant, initial-state index, policy seed, the
  frozen event with its trigger) and the hash of the simulator state the agent starts from (after LIBERO's 10 warm-up
  no-op steps). The scene is rebuilt from the pinned upstream data in the image by LIBERO-MAX's own code, and the
  rebuilt state is checked against the hash on every load (the standard service checks it when the episode begins and
  records a mismatch as `instance_mismatch`, `infra_error = 1`, before the agent is served).
- **One simulator per process.** Some cases do not rebuild bit-exactly a second time in the same process, so `lmx_tool`
  refuses a second Session in one process (loudly, with the reason), and every verification replay (privileged
  grader) and every video pass (standard service) runs in a fresh process.
- **Host CPUs.** The start state is bit-exact only with the numeric kernels it was frozen with, because robosuite's OSC
  controller and LIBERO's code run on numpy and scipy. Two parts of the stack choose kernels by CPU at run time:
  - **OpenBLAS.** numpy 1.22.4 and scipy 1.10.1 bundle OpenBLAS 0.3.18, which picks its kernels per CPU: Zen on the
    reference AMD Ryzen 9 7950X, but its generic Prescott (SSE3) kernels on CPUs it does not know (Intel Xeon Platinum
    8488C), where without the override no instance rebuilds. The image sets `OPENBLAS_CORETYPE=Zen` (AVX2 + FMA kernels; a build-time check
    asserts both libraries use them).
  - **numpy's own SIMD loops.** numpy dispatches its math loops at run time, and the frozen hashes use its AVX-512
    loops; an AVX2-only CPU (AMD EPYC 7R13, Zen 3) rebuilds only some instances. The reference CPU (AMD Ryzen 9 7950X) and the verified host CPU (Intel Xeon Platinum 8488C) dispatch the same targets, up to `AVX512_ICL`. So run LIBERO-MAX on hosts that dispatch like them (`AVX512_ICL`: Intel Ice Lake or newer Xeon,
    AMD Zen 4 or newer), and check any other host type with `rebuild_check.sh`.
  - **Exact or nothing.** There is no tolerance. On a host whose kernels differ, every Session refuses, loudly, and the
    error names the kernels in use (`lmx_tool.numerics()`).
    - Why no tolerance: a state off by rounding grows over a contact-rich episode (references fail even with their
      events at the recorded steps).
    - Before using a new host type, run `bash scripts/libero-max/rebuild_check.sh [parallel]`: every instance's start
      hash, plus its reference replayed to the recorded final hash, event step and success.
- **Event.** LIBERO-MAX's frozen change and trigger: the first control step at which the gripper is within the case's
  distance (0.18 m) of the trigger object (LIBERO-MAX's `distance_to_entity`), the change is applied once by
  LIBERO-MAX's backend (objects or fixtures moved, objects parked off-scene at reset brought in, camera pose and field
  of view, lighting, the image transform for colour theme and sensor noise). Applied identically in the agent's tool,
  the verifier's replays and the standard service; the replays reproduce the trigger step.
- **Actions.** LIBERO's native action in both modes, `[dx, dy, dz, drx, dry, drz, grip]` in [-1, 1], one per control
  step (1/20 s): the OSC_POSE controller moves the hand's target by up to 0.05 m and turns it by up to 0.5 rad
  (axis-angle, world frame) per step; grip +1 closes, -1 opens. In standard mode the type is `ee_delta` (action types
  are benchmark-defined).
- **Success and episode end.** LIBERO's success check (the BDDL goal: LIBERO's On / In predicates, and Close /
  TurnOn / TurnOff on a drawer's slide or the stove knob's hinge, with their real thresholds from LIBERO's articulated
  objects, stated per task in both instructions). LIBERO ends the episode the moment it holds (`done`), so the graded
  state is the trajectory's final state: a privileged trajectory with actions after that is invalid, and the standard
  service ends the episode with `reason = "success"` there.
- **Length.** Privileged deliverables have 1 ≤ T ≤ the suite's limit (220 / 280 / 300 / 520 control steps, LIBERO's
  evaluation horizons), counted after the 10 warm-up steps. Standard episodes have only a technical cap of 9,000 control
  steps (450 s of robot time) so that the episode's video pass fits the collect hook's wait (see Grading).
  LIBERO's environment is built with a horizon beyond both (robosuite refuses actions after its horizon; it does not
  touch the physics).
- **World frame.** Metres; the robot's base (fixed mount) at (-0.66, 0, 0.912) facing +x: x forward, y left, z up.
- **Standard observations.** `agentview` (fixed) and `wrist` (`robot0_eye_in_hand`), RGB 256×256, metric depth on
  request, upright images with LIBERO-PRO's pixel perturbation of the variant and, after the event, LIBERO-MAX's image
  change applied; intrinsics and pose in `/spec` at the start and the current ones in every submit response
  (`meta.cameras_now`: a camera_shift event moves agentview and changes its field of view). Proprioception: hand pose,
  finger positions, joint positions and velocities, last command. The agent is told that the scene may change once
  (what kinds of change), not which change or when. No object poses, no goal, no success signal.

### Notes on single cases
- A move event (`target_relocation`, `receptacle_relocation`) sets one entity's position (`libero_backend._move_object`):
  what rests in or on a moved receptacle stays behind, and an entity that lands on another is pushed apart by the
  physics. Both instructions say so.
- Four cases of `LIVING_ROOM_SCENE5_put_the_white_mug_on_the_left_plate...`: LIBERO's left plate (`plate_1`, in
  `plate_left_region`) is on the robot's right; the instructions say that left and right are as seen facing the robot.
- `STUDY_SCENE1_..._back_compartment_of_the_caddy` with the mug (LIBERO-PRO's task variant replaces the book): the back
  compartment is the narrow back cell, about 5.5 cm across, narrower than the mug; LIBERO's `In` (origin in the region's
  box, contact with the caddy) holds for a mug resting on its opening. The instructions say so; the check is unchanged.
- The `initial_pose_position_angle` cases of `pick_up_the_black_bowl_{on,next_to}_the_cookie_box...` shift the target bowl
  0.17 m in x and -0.06 m in y and turn it 45 degrees, so the sentence's spatial relation no longer holds; the
  instructions say which bowl is meant.

## Grading (standard mode)
The standard mode is graded by the live episode; nothing is replayed to grade it (docs/protocol/README.md H.4). The
privileged mode: the verifier's two fresh-process replays.

- **Live success.** LIBERO's success check on the episode the sim service ran: `lmx_tool.Session.step` reports it
  (`wrapped.step`'s `done`), `rcb_service` ends the episode there (`reason = "success"`) and `_finalize()` writes
  `success = live_success`, `graded_by = "live"`, `replays = 0`, the live end state (`state_sha`) and LIBERO-MAX's
  event record of the live episode (`event_fired`, `event_step`; `server.py` `live_verdict()`). The privileged rule's
  other condition, no action after the success (`invalid`), cannot occur live (the episode ends at the success, every
  later request is refused); there is no settle or hold window. `tests/grade.py`: `success = live_success ∧ graded_by = "live" ∧ ¬infra`.
- **Start state.** The frozen instance records the start state's hash (`initial_state_sha`, after LIBERO's 10 warm-up
  steps). The live service builds the scene without refusing (`Session(check=False)`) and `rcb_service` compares the
  state with that hash when the episode begins (`server.py` `start_sha`): a mismatch gives up as `instance_mismatch`
  (`infra_error = 1`) before the agent is served. A resume after a crash checks the journal replay against the logged
  hash (`resume_failed`, infra).
- **Infrastructure** (`infra_error = 1`, at most one retry, PROTOCOL H.5): no, unreadable or unfinalized `final.json`;
  the service's own give-ups (`sim_crashed` after crashes not all inside the agent's calls, `resume_failed`,
  `instance_mismatch`); a finalize that failed on the service's side (`grader_error = 1`). The agent's (0, never infra):
  the time running out, the step cap, a simulator error raised by the agent's actions (`sim_error`), crashes all
  inside its calls (`sim_crashed_on_call`). Video failures are never infra.
- **Video: one video-only pass after the verdict.** Recording live is not cheap here: every
  frame is an OSMesa render (about 70 ms at 256×256, 0.24 s on a busy host) inside the agent's calls. So once
  `final.json` is finalized (`video_pending: true`), `server.py` `render_video()` replays `trajectory.npz` once in a
  fresh process with the agentview camera on (`lmx_tool.py --replay ... replay.mp4`; its success is not read) and
  writes `replay.video.json` (the replay's end hash, the live one, `ends_in_live_state`, the stride). A failure, a
  timeout (`RCB_VIDEO_TIMEOUT_S`, 5,400 s) or a crash costs only the video (`video = false`).
- **Cost.** The verdict within seconds of the hook's signal, then one pass for the video only (CPU, the sim sidecar's
  4 CPUs; no GPU): no verdict waits on it.

### Collect budget
The video pass of N control steps takes B + N × s + V:

| term | value | basis |
|---|---|---|
| B, building the scene in the fresh process | ≤ 180 s | 1–3 min on a busy sidecar (#110) |
| s, per control step (LIBERO renders its two observation cameras every step) | 0.5 s | busy batch host: 2,662 steps in 1,415 s including B, without a video (#125); about 0.1 s on a quiet host |
| V, the video's frames | ≤ 240 s | `lmx_tool._ReplayVideo`: one frame per `video_stride` control steps (2 up to 2,400 steps, a time-lapse of at most 1,200 frames beyond), frames skipped whenever the time spent exceeds 240 s × the fraction replayed (`LMX_VIDEO_BUDGET_S`, `LMX_VIDEO_MAX_FRAMES`) |
| N = 9,000 (the episode cap) | 180 + 4,500 + 240 = **4,920 s** | |
| `RCB_COLLECT_WAIT_S` | **5,400 s** | the hook's whole wait, verdict and video; 480 s (10%) to spare |
| the hook's `timeout_sec` | 180 + 5,400 + 120 = **5,700 s** | up to 180 s for the service's PID file, 120 s of slack |

The hook (`finalize.sh`) signals the service every 30 s until `final.json` is finalized, then waits while
`video_pending` is true, up to 5,400 s from its start. Only a service that crashed late in the episode needs the wait
for its verdict: it resumes by replaying its journal (crash recovery, not grading), at most N × s + B.

## Licence
LIBERO-MAX (Zhang et al., [*LIBERO-MAX: Do Robot Policies Adapt When the World Changes?*](https://arxiv.org/abs/2609.36518),
2026) has no licence file upstream; its authors have given written permission to redistribute the two parts below in
this benchmark, with attribution. Two parts come from it: (1) the event parameters and
case choice (`cases.json`, and the instances made from it), (2) LIBERO-MAX's event runtime in the image (`src/libero_max`,
about 1,800 lines used: `substrate.py`, `pro_runtime.py`, `cosmos_integration.py`, `libero_backend.py`, `runtime.py`,
`scenario.py`, `env_factory.py`). Both stay isolated: `cases.json` is the only input that carries the parameters, so either
part could be replaced by an own implementation of the same eight change types without touching the generator or the
tools. LIBERO-PRO (MIT / CC-BY-4.0) and LIBERO (MIT) need nothing beyond attribution. LIBERO-plus (no licence file,
third-party TurboSquid assets) is a separate project and stays out of scope.

The permission, by email from Yunbei Zhang (LIBERO-MAX's first author), in reply to our request to redistribute these
two parts unmodified in this public repository and in a public Docker image, citing the paper and linking the
repository:

> I'm happy to grant permission to redistribute the two components as described. Please cite our paper and link to the
> LIBERO-MAX repository. I'll also update the repository with a license soon.

This page cites the paper and links the repository; when the repository adds a licence, the benchmark follows it.

## Rebuilding
```bash
docker build -t ghcr.io/mll-lab-nu/eai-libero-max:$(cat images/libero-max/VERSION) -f images/libero-max/Dockerfile .
python3 scripts/libero-max/select_cases.py candidates <LIBERO-MAX>/benchmark/max8000/libero_max_8000.json candidates.json
bash scripts/libero-max/freeze.sh candidates.json frozen-candidates 8       # ~2 min per case, one container each
python3 scripts/libero-max/select_cases.py pick candidates.json frozen-candidates scripts/libero-max/cases.json
bash scripts/libero-max/freeze.sh                                          # the chosen cases -> scripts/libero-max/frozen/
python3 scripts/libero-max/generate.py && python3 scripts/libero-max/generate.py --check
bash scripts/libero-max/rebuild_check.sh 8                                 # per host type: 64/64 rebuild bit-exactly
cd tasks && harbor add --scan . && cd .. && bash ci_checks/run_all.sh
```

## Evidence
| check | result |
|---|---|
| freeze (`freeze.sh`), 64 cases | not solved at the start 64/64; reference succeeds at its last step 64/64 (66–409 steps; the event fires 64/64, at step 5–101); two fresh-process replays = live hash and event step 64/64 |
| same cases frozen twice (the candidate run and the final run, separate containers) | identical initial and final hashes 64/64 |
| `harbor run -a oracle`, privileged | 64/64 reward 1 (deterministic, event fired, no errors) |
| `harbor run -a oracle`, standard (one case per event; 5 of the 8 turn a stove knob or close a drawer) | 8/8 reward 1 |
| `harbor run -a nop` | 4/4 privileged and 4/4 standard reward 0 |
| scripted cheat attempts (patched tooling and success check, forged reward files, `sitecustomize.py`, tampered instance copy; hidden endpoints, wrong action type and `dt`, NaN rows, forged `final.json`) | privileged 0, standard 0; hidden endpoints 404, malformed submits 400 |
| `generate.py --check`, `task_conventions.py --check`, `ci_checks/run_all.sh` | clean; no LIBERO-MAX warnings |
| verdict before video, stubbed simulator: the real `rcb_service` + `server.py` with a fake replay process; `lmx_tool._ReplayVideo` with the real encoder | encoder open / append / close and render failures, a crash and a hang after the verdict: verdict intact, one replay, `video = false`; verdict on disk before the video is finished; a 1 s budget at 30 ms per frame holds (34 frames, 168 skipped, spread); 9,000 steps → stride 8, 1,126 frames |
| the same, real simulator (visual_theme_switch, 66 steps; a 2-CPU container on a host at load 44): `lmx_tool.py --replay` with a video; and two standard trials without Harbor (service, the reference through the client, `finalize.sh`, `grade.py`), one of them with a broken encoder | replay: final state hash = `report.json`'s, event at the recorded step, 34 frames; both trials reward 1 with that hash, one replay each: verdict on disk 66 s after the hook started and `finalized` (with the video) 3 s later; with the broken encoder verdict after 53 s, `video = false` |
| live grading, `scripts/libero-max/tests/test_live_grading.py`: the real `rcb_service` + `server.py` with a stub `lmx_tool` (no simulator), the real `finalize.sh` and `grade.py` | live success → 1, failure → 0, no replay before the verdict (the replay entry point fails the test if called), event record from the live episode; video failure, timeout and a replay that diverges leave the verdict unchanged; `instance_mismatch` at the start, a give-up after crashes between calls → infra; crashes all inside calls → 0, not infra; missing / unreadable / unfinalized `final.json` → infra; the hook stops at the verdict, waits for `video_pending`, and stops at its bound |
| `rebuild_check.sh` (start hash; reference replayed to the recorded final hash, event step and success), 64 instances | Intel Xeon 8488C: 64/64; AMD 7950X: 64/64 |
| `rebuild_check.sh`, AWS AMD EPYC 7R13 (Zen 3, no AVX-512) | 10 of the first 24 instances rebuild: numpy's AVX-512 loops are missing (OpenBLAS runs Zen); not a supported host |
| kernel probes on the 7950X, 6 instances (one per 11 in sorted order) | OpenBLAS Prescott forced: 0/6; Haswell forced: 6/6; Zen with numpy's AVX-512 loops off: 3/6 |

Measured on the reference machine (AMD Ryzen 9 7950X): about 20 ms of physics per control step, about 70 ms per
256×256 camera image (OSMesa); a privileged oracle trial takes 2–3 min, most of it the verifier's two fresh replays.
Busy hosts are several times slower: see Collect budget.

## Easy set

The benchmark owner's screening (ten runs, one trial per run and task directory). A directory is **easy** when a run solved it: a graded success within the task's time limit.
Where only one or two of the later runs solved a directory Luna had failed, their logs were checked for shortcuts and
for any access to tests, solutions or graders. It is **hard** when GPT-6 Luna and every later run that attempted it
failed, GPT-6 Astra and Claude Opus 5.5 among them; a standard directory that only Astra solved is hard as well. It is
**unverified** when only Luna attempted it and failed (the later runs only take bases Luna solved in no mode), and
**pending** without a Luna verdict. A base whose every mode is easy is in the easy set (`docs/easy_set.toml`, reason
`solved`): kept under its name and reported apart from the main table.

Runs: Luna `codex-gpt6_luna-xhigh`; Astra `codex-gpt6_astra-high`; Opus `claude_code-opus_5_5-high`; Sol 6.1
`codex-gpt6_1_sol-high`; Sol `codex-gpt6_sol-high`; Gemini 3.8 Flash `antigravity_cli-gemini_3_8_flash-high`; Gemini 4
Argon `antigravity_cli-gemini_4_argon-high`; DeepSeek V4.1 Flash `dsh-deepseek_v4_1_flash-high`; GLM 5.3 Flash
`claude_code-glm_5_3_flash-high`; Qwen3.8 27B `claude_code-qwen3_8_27b-high`.

29 of 64 bases are in the easy set; by directory: 93 easy, 0 hard, 35 unverified, 0 pending.

| base | easy set | privileged | standard |
|---|---|---|---|
| `libero-max-goal-akita-black-bowl-in-wooden-cabinet-top-target-relocation-i00` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 3.8 Flash |
| `libero-max-goal-akita-black-bowl-on-flat-stove-cook-target-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-goal-akita-black-bowl-on-plate-receptacle-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-goal-akita-black-bowl-on-wooden-cabinet-top-obstacle-insertion-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-cream-cheese-on-akita-black-bowl-obstacle-insertion-i00` |  | easy: Luna | unverified |
| `libero-max-goal-flat-stove-off-visual-theme-switch-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-flat-stove-on-illumination-switch-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-flat-stove-on-illumination-switch-i01` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-flat-stove-on-sensor-noise-onset-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-wine-bottle-on-plate-receptacle-relocation-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-wine-bottle-on-wine-rack-top-camera-shift-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-goal-wine-bottle-on-wine-rack-top-obstacle-insertion-i00` |  | easy: Luna | unverified |
| `libero-max-goal-wine-bottle-on-wine-rack-top-visual-theme-switch-i00` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 4 Argon |
| `libero-max-goal-wine-bottle-on-wooden-cabinet-top-sensor-noise-onset-i00` |  | easy: Luna | unverified |
| `libero-max-goal-yellow-stove-on-camera-shift-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-long-alphabet-soup-and-cream-cheese-in-basket-receptacle-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-long-alphabet-soup-and-cream-cheese-in-basket-target-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-distractor-burst-i00` |  | easy: Luna | unverified |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-receptacle-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-long-alphabet-soup-and-tomato-sauce-in-basket-sensor-noise-onset-i00` |  | easy: Luna | unverified |
| `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i00` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus |
| `libero-max-long-black-bowl-in-wooden-cabinet-bottom-closed-obstacle-insertion-i01` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-camera-shift-i00` |  | easy: Luna | unverified |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-illumination-switch-i00` |  | easy: Luna | unverified |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-visual-theme-switch-i00` |  | easy: Luna | unverified |
| `libero-max-long-porcelain-mug-and-white-yellow-mug-on-plate-visual-theme-switch-i01` |  | easy: Luna | unverified |
| `libero-max-long-white-yellow-mug-and-green-chocolate-pudding-on-yellow-plate-sensor-noise-onset-i00` |  | easy: Luna | unverified |
| `libero-max-long-white-yellow-mug-in-desk-caddy-back-camera-shift-i00` |  | easy: Luna | unverified |
| `libero-max-long-white-yellow-mug-in-desk-caddy-back-illumination-switch-i00` |  | easy: Luna | unverified |
| `libero-max-object-alphabet-soup-in-basket-receptacle-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-object-alphabet-soup-in-basket-target-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-object-alphabet-soup-in-basket-visual-theme-switch-i00` |  | easy: Luna | unverified |
| `libero-max-object-butter-in-basket-distractor-burst-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-butter-in-basket-receptacle-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i00` |  | easy: Luna | unverified |
| `libero-max-object-chocolate-pudding-in-basket-distractor-burst-i01` |  | easy: Luna | unverified |
| `libero-max-object-chocolate-pudding-in-basket-sensor-noise-onset-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-cream-cheese-in-basket-visual-theme-switch-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-green-bbq-sauce-in-red-basket-distractor-burst-i00` |  | easy: Luna | unverified |
| `libero-max-object-green-chocolate-pudding-in-red-basket-camera-shift-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-ketchup-in-basket-distractor-burst-i00` |  | easy: Luna | unverified |
| `libero-max-object-milk-in-basket-camera-shift-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-milk-in-basket-distractor-burst-i00` |  | easy: Luna | unverified |
| `libero-max-object-milk-in-basket-illumination-switch-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-milk-in-basket-target-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-object-orange-juice-in-basket-distractor-burst-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-orange-juice-in-basket-illumination-switch-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-object-salad-dressing-in-basket-sensor-noise-onset-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-spatial-akita-black-bowl-on-plate-camera-shift-i01` |  | unverified | easy: Luna |
| `libero-max-spatial-akita-black-bowl-on-plate-illumination-switch-i00` | yes | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 4 Argon |
| `libero-max-spatial-akita-black-bowl-on-plate-illumination-switch-i01` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `libero-max-spatial-akita-black-bowl-on-plate-obstacle-insertion-i00` | yes | easy: Luna | easy: Luna |
| `libero-max-spatial-akita-black-bowl-on-plate-obstacle-insertion-i01` |  | easy: Luna | unverified |
| `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i00` | yes | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon, GLM 5.3 Flash | easy: Astra, Opus, Gemini 4 Argon |
| `libero-max-spatial-akita-black-bowl-on-plate-receptacle-relocation-i01` | yes | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon | easy: Astra, Opus, Gemini 4 Argon |
| `libero-max-spatial-akita-black-bowl-on-plate-sensor-noise-onset-i00` | yes | easy: Astra, Opus, Gemini 4 Argon, DeepSeek V4.1 Flash | easy: Astra, Opus, Gemini 3.8 Flash, Gemini 4 Argon |
| `libero-max-spatial-akita-black-bowl-on-plate-sensor-noise-onset-i01` | yes | easy: Astra, Opus, Gemini 4 Argon | easy: Astra, Opus, Gemini 4 Argon |
| `libero-max-spatial-akita-black-bowl-on-plate-target-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-spatial-akita-black-bowl-on-plate-target-relocation-i01` |  | easy: Luna | unverified |
| `libero-max-spatial-akita-black-bowl-on-plate-visual-theme-switch-i00` |  | easy: Luna | unverified |
| `libero-max-spatial-black-bowl-on-yellow-plate-obstacle-insertion-i00` |  | easy: Luna | unverified |
| `libero-max-spatial-black-bowl-on-yellow-plate-target-relocation-i00` |  | easy: Luna | unverified |
| `libero-max-spatial-black-bowl-on-yellow-plate-visual-theme-switch-i00` |  | easy: Luna | unverified |
