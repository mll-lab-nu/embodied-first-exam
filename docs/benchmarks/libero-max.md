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
| standard client | the shared client base and pins of `scripts/eai_standard/`; `rcb_client.py` and `rcb1.py` are byte copies of main's (HumanoidBench / VLABench); the standard `grade.py` started as one and is LIBERO-MAX's own since #110 (the verdict is in once `deterministic` is on disk; every path writes the same `reward.json` fields); `rcb_service.py` is a byte copy too, plus one hook (3 lines): `verify()` may return `extra`, merged into the verdict, which LIBERO-MAX uses to record `event_fired` / `event_step` (live) and `replay_event_fired` / `replay_event_step` in `final.json` (evidence only, never part of the success rule; a candidate to upstream to the shared service) |
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
  rebuilt state is checked against the hash on every load.
- **One simulator per process.** In the spike, 2 of 14 cases (a LIBERO-plus Sensor-Noise variant and a LIBERO-PRO
  camera_view_angle variant) did not rebuild bit-exactly a second time in the same process. `lmx_tool` therefore
  refuses a second Session in one process (loudly, with the reason), and every verification replay and replay video
  runs in a fresh process (privileged grader, standard service).
- **Host CPUs.** The start state is bit-exact only with the numeric kernels it was frozen with, because robosuite's OSC
  controller and LIBERO's code run on numpy and scipy. Two parts of the stack choose kernels by CPU at run time:
  - **OpenBLAS.** numpy 1.22.4 and scipy 1.10.1 bundle OpenBLAS 0.3.18, which picks its kernels per CPU: Zen on the
    reference AMD Ryzen 9 7950X, but its generic Prescott (SSE3) kernels on the AWS hosts' Intel Xeon Platinum 8488C
    (Sapphire Rapids), a CPU it does not know. With image 0.1.0 none of the 64 instances rebuilt there (the Session
    refused with a hash mismatch), and 3 references replayed to a failure. Image 0.1.1 sets `OPENBLAS_CORETYPE=Zen`
    (AVX2 + FMA kernels; a build-time check asserts both libraries use them). Forcing Prescott on the 7950X reproduces the
    mismatch, and forcing Zen on the 8488C removes it.
  - **numpy's own SIMD loops.** numpy dispatches its math loops at run time, and the frozen hashes use its AVX-512
    loops. Both reference CPUs dispatch the same targets (up to `AVX512_ICL`). With those loops switched off
    (`NPY_DISABLE_CPU_FEATURES`, standing in for an AVX2-only CPU), 3 of 6 sampled instances differ. A real AVX2-only
    CPU, an AWS AMD EPYC 7R13 (Zen 3, the rcb-gpu hosts), rebuilt only 10 of the first 24 instances checked with 0.1.1.
    So run LIBERO-MAX on hosts that dispatch like the two reference CPUs (`AVX512_ICL`: Intel Ice Lake or newer Xeon,
    AMD Zen 4 or newer), and check any other host type with `rebuild_check.sh`.
  - **Exact or nothing.** There is no tolerance. On a host whose kernels differ, every Session refuses, loudly, and the
    error names the kernels in use (`lmx_tool.numerics()`).
    - Why no tolerance: a state off by rounding grows over a contact-rich episode. With 0.1.0 on the 8488C, 3 of the 64
      reference trajectories failed even though their events fired at the recorded steps.
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
  are benchmark-defined, PROTOCOL §4.4 since #31).
- **Success and episode end.** LIBERO's success check (the BDDL goal: LIBERO's On / In predicates, and Close /
  TurnOn / TurnOff on a drawer's slide or the stove knob's hinge, with their real thresholds from LIBERO's articulated
  objects, stated per task in both instructions). LIBERO ends the episode the moment it holds (`done`), so the graded
  state is the trajectory's final state: a privileged trajectory with actions after that is invalid, and the standard
  service ends the episode with `reason = "success"` there.
- **Length.** Privileged deliverables have 1 ≤ T ≤ the suite's limit (220 / 280 / 300 / 520 control steps, LIBERO's
  evaluation horizons), counted after the 10 warm-up steps. Standard episodes have only a technical cap of 9,000 control
  steps (450 s of robot time) so that the fresh grading replay fits the collect hook's wait (see Collect budget).
  LIBERO's environment is built with a horizon beyond both (robosuite refuses actions after its horizon; it does not
  touch the physics).
- **World frame.** Metres; the robot's base (fixed mount) at (-0.66, 0, 0.912) facing +x: x forward, y left, z up.
- **Standard observations.** `agentview` (fixed) and `wrist` (`robot0_eye_in_hand`), RGB 256×256, metric depth on
  request, upright images with LIBERO-PRO's pixel perturbation of the variant and, after the event, LIBERO-MAX's image
  change applied; intrinsics and pose in `/spec` at the start and the current ones in every submit response
  (`meta.cameras_now`: a camera_shift event moves agentview and changes its field of view). Proprioception: hand pose,
  finger positions, joint positions and velocities, last command. The agent is told that the scene may change once
  (what kinds of change), not which change or when. No object poses, no goal, no success signal.

### Notes on single cases (2026-10-14, board 0113)
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

## Collect budget (standard mode)
When the agent's container is gone, the collect hook (`environment/sim/finalize.sh`) signals the service, which ends the
episode and replays it in a fresh process (`lmx_tool.py --replay`, one simulator per process). That replay is the
verdict, and it records `replay.mp4` on the way (a second replay for the video would outlast the hook for every long
episode, #125).

- **The verdict comes first and the video cannot touch it.**
  - The replay prints its verdict the moment it has executed the last action; `server.py` `verify()` returns it at
    once and `rcb_service` writes it to `final.json` (`deterministic` appears). The final frame, the encoder's flush
    and `replay.last.png` come after it; `render_video()` waits for them (at most 120 s) and moves the files into
    place, then `finalized` is set.
  - Rendering reads the scene and never steps physics: the final state hash is the same with and without the video.
  - A failure in the video (a render, the encoder, the disk, a crash or a hang after the verdict) only means
    `video = false`. The episode is never replayed again for a video. Only a replay process that dies before its
    verdict (a crash in native code) is replayed once more, without a video; that case is outside the budget below.
  - The video is written as `replay.part.mp4` and renamed when complete, so a killed replay leaves no truncated file.
- **The video's cost before the verdict is capped** (`lmx_tool._ReplayVideo`): frames go straight to the encoder; one
  frame per `replay_video_stride` control steps (in `final.json`): 2 up to 2,400 steps (10 fps, real time), and
  `ceil(steps / 1200)` beyond (a time-lapse of at most 1,200 frames; 8 for 9,000 steps). A frame is skipped whenever
  the time spent on the video so far exceeds 240 s × the fraction of the episode replayed, so the video adds at most
  240 s however slow the host is, and what is skipped is spread over the episode (`LMX_VIDEO_BUDGET_S`,
  `LMX_VIDEO_MAX_FRAMES` in the sidecar's environment change the two bounds).
- **Arithmetic.** The replay of N control steps takes B + N × s + V:

  | term | value | basis |
  |---|---|---|
  | B, building the scene in the fresh process | ≤ 180 s | 1–3 min on a busy sidecar (#110) |
  | s, per control step (LIBERO renders its two observation cameras every step) | 0.5 s | busy batch host: 2,662 steps in 1,415 s including B, without a video (the example behind #125); about 0.1 s on a quiet host |
  | V, the video inside the replay | ≤ 240 s | the cap; 1,200 frames at 0.07 s (reference machine) = 84 s, at 0.24 s (measured in a 2-CPU container on a host at load 44 on 32 cores) = 288 s, cut to 240 s |
  | N = 9,000 (the episode cap) | 180 + 4,500 + 240 = **4,920 s** | |
  | `RCB_COLLECT_WAIT_S` | **5,400 s** | 480 s (10%) to spare |
  | the hook's `timeout_sec` | 180 + 5,400 + 120 = **5,700 s** | up to 180 s for the service's PID file, 120 s of slack; `finalize.sh` counts wall-clock seconds |

  A second bound that does not rest on the per-step figure: the live episode ran on the same sidecar inside the
  agent's 3,600 s, at no less per step than the replay (the same `env.step`, plus the images the agent asked for). So
  5,400 s covers every live success whose replay is up to (5,400 − 180 − 240) / 3,600 = 1.38× slower than its live
  run. Before 2026-10-10 the wait was 3,000 s (#110: 9,000 × 0.25 s + build, sized without the video and with a
  per-step figure half of what busy hosts showed): a live success of more than about 5,000 steps on a busy host ended
  with `infra_error = 1`.
- **What the hook waits for.** `finalized` (PROTOCOL §4.8), which now follows the verdict within seconds. Three
  backstops stop it earlier or bound it; none can misgrade, because `tests/grade.py` reads `deterministic`, not
  `finalized`:
  - 300 s after the verdict is on disk (`RCB_VIDEO_GRACE_S`), should the service hang while finishing the video;
  - `RCB_FAIL_WAIT_S` after the start for an episode that ended **without** a live success: it is a failure whatever
    its replay says, so its replay is evidence only. The default is the overall wait (5,400 s; board 0136, 2026-10-16):
    the replay records the trial's video, and with the earlier 900 s most failed episodes ended without `replay.mp4`.
    A lower value trades the video of long failed episodes for verifier time, never the grade;
  - 5,400 s overall: a live success without a replay verdict by then is `infra_error = 1`.

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
| freeze (`freeze.sh`, eai-libero-max:0.1.0), 64 cases | not solved at the start 64/64; reference succeeds at its last step 64/64 (66–409 steps; the event fires 64/64, at step 5–101); two fresh-process replays = live hash and event step 64/64 |
| same cases frozen twice (the candidate run and the final run, separate containers) | identical initial and final hashes 64/64 |
| `harbor run -a oracle`, privileged | 64/64 reward 1 (deterministic, event fired, no errors) |
| `harbor run -a oracle`, standard (one case per event; 5 of the 8 turn a stove knob or close a drawer) | 8/8 reward 1 (live = replay, deterministic) |
| `harbor run -a nop` | 4/4 privileged and 4/4 standard reward 0 |
| scripted cheat attempts (patched tooling and success check, forged reward files, `sitecustomize.py`, tampered instance copy; hidden endpoints, wrong action type and `dt`, NaN rows, forged `final.json`), on the first 48-case revision (graders and service unchanged since; the tool only gained `state()["articulations"]`) | privileged 0, standard 0; hidden endpoints 404, malformed submits 400 |
| `generate.py --check`, `task_conventions.py --check`, `ci_checks/run_all.sh` | clean; no LIBERO-MAX warnings |
| verdict before video (2026-10-10), stubbed simulator: the real `rcb_service` + `server.py` with a fake replay process; `lmx_tool._ReplayVideo` with the real encoder | encoder open / append / close and render failures, a crash and a hang after the verdict: verdict intact, one replay, `video = false`; verdict on disk before the video is finished; a 1 s budget at 30 ms per frame holds (34 frames, 168 skipped, spread); 9,000 steps → stride 8, 1,126 frames |
| the same, real simulator (visual_theme_switch, 66 steps; a 2-CPU container on a host at load 44): `lmx_tool.py --replay` with a video; and two standard trials without Harbor (service, the reference through the client, `finalize.sh`, `grade.py`), one of them with a broken encoder | replay: final state hash = `report.json`'s, event at the recorded step, 34 frames; both trials reward 1 with that hash, one replay each: verdict on disk 66 s after the hook started and `finalized` (with the video) 3 s later; with the broken encoder verdict after 53 s, `video = false` |
| graders (2026-10-10), synthetic | standard: 10 `final.json` cases (missing, unreadable, verdict without `finalized`, ...) write the same 21 fields, `deterministic` among them; privileged: replay exit code 3 → `infra_error = 1`, any other failure → `grader_error = 1` only |
| `rebuild_check.sh` (start hash; reference replayed to the recorded final hash, event step and success), 64 instances | 0.1.0 on Intel Xeon 8488C (AWS rcb-cpu): 0/64, OpenBLAS Prescott kernels, 3 references fail; 0.1.1 on the 8488C: 64/64; 0.1.1 on AMD 7950X: 64/64 |
| `rebuild_check.sh`, 0.1.1, AWS AMD EPYC 7R13 (Zen 3, no AVX-512) | 10 of the first 24 instances rebuild: numpy's AVX-512 loops are missing (OpenBLAS runs Zen); not a supported host |
| kernel probes on the 7950X, 6 instances (one per 11 in sorted order) | OpenBLAS Prescott forced: 0/6; Haswell forced: 6/6; Zen with numpy's AVX-512 loops off: 3/6 |

Measured on the reference machine (AMD Ryzen 9 7950X): about 20 ms of physics per control step, about 70 ms per
256×256 camera image (OSMesa); a privileged oracle trial takes 2–3 min, most of it the verifier's two fresh replays.
Busy hosts are several times slower: see Collect budget.
