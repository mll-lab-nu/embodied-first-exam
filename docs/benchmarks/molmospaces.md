# MolmoSpaces

[Ai2 MolmoSpaces](https://github.com/allenai/molmospaces) (molmo-spaces 0.2.9, Apache-2.0) on MuJoCo 3.5.0: the
benchmark episodes Ai2 uses to evaluate robot policies zero-shot in unseen houses. `simulator = "molmospaces"`, robots
`franka-robotiq-2f85` (Franka FR3 + Robotiq 2F-85, the DROID setup) and `rainbow-rby1`. 8 families, one frozen episode
each, as `molmospaces-<family>-i00-privileged` and its standard twin `-standard` (`eai-standard/2.2`): 16 tasks.

| family | upstream package (molmospaces-bench-v2/20260415) | robot, control period | variants | kept episode (shipped as i00) | horizon |
|---|---|---|---|---|---|
| pick | `procthor-objaverse/FrankaPickHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #12: a pestle against a wall | 303 steps (20 s) |
| pick-and-place | `procthor-objaverse/FrankaPickandPlaceHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #0: a GPS into a wooden bowl | 606 (40 s) |
| pick-and-place-next-to | `procthor-objaverse/FrankaPickandPlaceNextToHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #5: a flat moth beside bread | 455 (30 s) |
| pick-and-place-color | `procthor-objaverse/FrankaPickandPlaceColorHardBench` | Franka, 66 ms | AI2-THOR / Objaverse object | #52: a soap bottle into the light green bowl | 606 (40 s) |
| open | `ithor/FrankaOpenHardBench` | Franka, 66 ms | drawer / hinged door | #1427: a drawer | 455 (30 s) |
| close | `ithor/FrankaCloseHardBench` | Franka, 66 ms | drawer / hinged door | #327: a drawer | 455 (30 s) |
| navigate-to | `holodeck-objaverse/NavToObjDataGenConfig` | RB-Y1, 200 ms | one target / several (nearest counts) | #94: a bed two rooms away | 500 (100 s) |
| open-door | `procthor-10k/rby1_benchmarks/door_opening_benchmark` | RB-Y1 (RBY1M), 100 ms | push / pull | #0: a door to pull | 400 (40 s) |

## Upstream code decides the outcome
- `scripts/molmospaces/shared/rcb_molmospaces.py`, copied unchanged into every task (privileged `environment/` and
  `tests/`, standard `environment/sim/`), loads the frozen episode through upstream's JSON-evaluation path
  (`create_eval_config` → `JsonEvalRunner` → `JsonEvalTaskSampler` → `setup_policy` → `task.reset`; action noise off,
  as upstream's evaluation sets it). One control step = one upstream `Task.step` with the targets of every controlled
  move group; the episode ends at upstream's `is_done()` (the episode's `task_horizon_sec`) or at the agent's end;
  success = upstream's `judge_success()` on the final state. Physics, controllers, kinematics (`/kinematics`, the
  privileged `s.kinematics`) and the success checks are upstream's; the tooling adds no physics.
- Success semantics: upstream's evaluation default, **at the end** (`terminate_upon_success = False`; `eval_to_csv`
  reports at-end by default; the papers also report success at any step). The agent ends the episode itself: in standard
  mode with the `done` action type (`r.submit("done", [])`, upstream's `"done": True`), in privileged mode where its
  trajectory ends. Rates: `policy_dt_ms` of upstream's evaluation config for the Franka (66 ms); its data-generation
  configs for the RB-Y1 (navigation 200 ms, door 100 ms; upstream has no RB-Y1 evaluation config).
- Every upstream `Task.step` also polls the sensors (all of the episode's cameras): pick-and-place success depends on that
  history (it remembers poses in which the receptacle supported the object), so steps are never batched without it.

## Instances (`scripts/molmospaces/make_instances.py`)
Per family, the package is walked in its order and three candidates are taken among the episodes that pass the
filters: the first that shows each of the family's two variants and the next one of either, each in a different house.
The benchmark ships one of them as `<family>-i00` (`keep` in `families.json`, its upstream episode index): the hardest
and most representative in GPT-6 Luna's runs of all 24 candidates in both modes (standard failed on it, for a reason at
the core of the family; the episode is well-posed and privileged mode has completed it). Filters: the
house has no public MolmoBot trajectory (`allenai/molmobot-data`, val split); upstream builds the episode with every
object it lists; the task is not done at t = 0; the target and the receptacle have no identical copy in the episode (the
text could not tell them apart); navigation: every candidate target has the target's WordNet synset
(upstream keeps the candidates of the target's category, and an Objaverse object's category is its library, `obja`, so
an Objaverse target would make every Objaverse object in the house a target). Difficulty, measurable and the same for
every model:

| families | rule |
|---|---|
| pick, pick-and-place(-next-to, -color) | at least 3 other objects within 30 cm of the target (the episode's object poses) |
| open, close | upstream's Hard packages (`FrankaOpenHardBench` / `FrankaCloseHardBench` configs): arm start posture randomised (±0.26 rad per joint, wrist ±90°), base placed up to ±30° off facing the fixture, the randomised 5-camera system of the pick families |
| navigate-to | the nearest target at least 5 m from the base and out of `head_camera`'s view at t = 0 (upstream's own checks) |
| open-door | none beyond the package |

The instance is the upstream episode unchanged except `source`
(its expert trajectory's path) removed; navigation's text, wrong in this package ("pick up the black television."), is
upstream `NavToObjTask`'s own description. `--refresh` rewrites the quoted facts and the t = 0 hash.
- Objaverse assets: version `20251016_from_20250610`, the one the benchmark was made with (0.2.9 defaults to `20260131`:
  of these episodes' Objaverse objects installed in both, 10 of 112 have different textures), pinned with upstream's
  `MLSPACES_PINNED_ASSETS_FILE` (`images/molmospaces/pinned_assets.json`). Object metadata stays `20260129`: 0.2.9
  cannot read the `20251117` file.
- Navigation uses the Holodeck package: the ProcTHOR-10k one was built on scene version 20251121 and 0.2.9 loads 20251217,
  so its episodes miss objects (upstream notes it in `molmo_spaces_constants.py`).
- One loader change: `JsonEvalTaskSampler.set_joint_values` raises unless the target articulated object has a grasp file
  (it only checks existence; the joint comes from the episode). Grasp files are not shipped, so the check is answered
  "exists" while the episode is built.

## Generator, image, host
- `python3 scripts/molmospaces/mk_tasks.py [--check]` writes every task dir from `families.json` (packages, rates,
  variants, the kept episode, the success rule in words, the difficulty, robots), `instances/`, `template/<mode>/`,
  `shared/` and `scripts/eai_standard/`, then `task_conventions.normalize()`. Re-running leaves `git diff tasks/` empty.
- `images/molmospaces/` → `ghcr.io/mll-lab-nu/eai-molmospaces:<VERSION>`. Run `images/molmospaces/prepare_assets.sh`
  first (as for eai-mujoco): it builds the `base` stage (the measured Python environment from `requirements.txt` with
  `--no-deps`, upstream's experts replaced by raising stubs in the same layer (`scrub_experts.py`: upstream's configs
  import them by name), WordNet), and in a container of it `install_assets.py install` downloads what the instances use
  with upstream's resource manager into `$MS_ASSETS_WORK` (default `/data/$USER/...`, ~6 GB), traces a run-time build of
  every instance under `strace -y`, deletes every file it did not open (~1.9 GB stay, 1.1 GB of it the object-metadata LMDB; no grasp file) and checks
  the hashes; the result is staged in `images/molmospaces/build/` (not committed). The image build copies it and checks
  every instance's t = 0 hash again. Code Apache-2.0; assets CC BY 4.0 / ODC-BY 1.0 (a few Objaverse objects CC BY-NC):
  publishable.
- A GPU renders (EGL; OSMesa without one is ~15× slower); physics is on the CPU. `environment/docker-compose.yaml` (and the
  privileged `tests/`) pass one through.

## Modes
- Privileged: `Session` with full state (`s.state()`, `s.model` / `s.data`), unlimited resets, any camera, upstream's
  kinematics. Upstream's reward and success code stay installed (PROTOCOL: privileged mode is not hidden); its experts,
  grasp files and the public trajectories are not reachable (agent egress: the model APIs only).
- Standard: the 2.2 layer plus `environment/sim/server.py`. `joint_position` (the controller targets, Franka 8 / RB-Y1 25)
  and `done`; the episode's robot cameras (not upstream's third-person follower); proprioception; `/kinematics`; no
  reset (D1 default). World-frame information (D7, `ci_checks/check-limited-texts.sh`): the texts name objects and the
  goal only; the robot's own pose and the camera calibration come from the service, object poses never.

## Grading and determinism
MuJoCo on the CPU: a fresh process repeats a trajectory bit for bit. Privileged: `tests/grade.py` replays
`/app/output/trajectory.npz` in two fresh processes; success = both succeed and their final hashes agree. Standard: the
service records every executed row; `environment/sim/finalize.sh` replays them in two fresh processes; success = live ∧
replay ∧ deterministic. Crash recovery: resume class `exact`. Budget: 3600 s (D8 default), no step limit beyond the
benchmark's own horizon.
