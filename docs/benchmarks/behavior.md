# BEHAVIOR-1K

BEHAVIOR-1K v3.9.2 (OmniGibson 3.9.2 on Isaac Sim 5.1, the stack the 2026 BEHAVIOR Challenge pins): household tasks for
the R1Pro mobile manipulator. `simulator = "behavior"`, `robot = "r1pro"`. 11 challenge tasks, each as a privileged task
`behavior-<family>-i00-privileged` and its standard twin `behavior-<family>-i00-standard`, on the 2026 challenge's
public_test instance 301. The generator knows 38 more challenge tasks; they stay out of the benchmark until one has a reference
solution or a positive example (below).

## Prerequisites (every BEHAVIOR run)
- **The image**, built on the host: `ghcr.io/embodied-agent-interface-v2-internal/eai-behavior:<images/behavior/VERSION>`
  is the official `stanfordvl/behavior:3.9.2` **by digest** plus a snapshot-pinned ffmpeg layer. It contains NVIDIA
  Isaac Sim and Omniverse Kit (no redistribution) and a 13.7 GB layer above ghcr.io's per-layer limit: **BUILD_ONLY**,
  never pushed. `images/behavior/BUILD_ONLY` has the build command, the licences and the data it needs.
- **The licensed dataset**, `RCB_BEHAVIOR_DATA`: the host directory with the BEHAVIOR Data Bundle
  (`omnigibson-robot-assets/`, `behavior-1k-assets/`, `2026-challenge-task-instances/`, `omnigibson.key`), downloaded after
  accepting its licence, which forbids redistribution. It is never in an image: every compose service that runs the
  simulator (privileged `main` and verifier, standard `sim`) mounts it read-only at `/data` as
  `${RCB_BEHAVIOR_DATA:?…}`, so `docker compose` refuses to start a BEHAVIOR task without it. Export it before
  `harbor run`.
- **One RTX-class NVIDIA GPU per Isaac process** (Isaac needs one even headless; PhysX runs on the CPU). The compose files
  reserve `count: 1` (PROTOCOL §2.4), which Docker serves with the host's first GPU (GPU 0).
- About 13-16 GB of RAM per Isaac process: one Isaac simulator at a time on a 32 GB host. torch / OpenMP pools are capped
  at 8 threads in every compose service that runs the simulator (uncapped they span every core of a large host and run up
  to 15× slower).

## Tasks and generator
- `scripts/behavior/mk_tasks.py` generates every task from the template twins `tasks/behavior-picking-up-trash-i00-privileged`
  and `-standard` (maintained by hand), `scripts/behavior/families.json` (the texts of each family: goal, success conditions,
  difficulty, the standard goal in words; the oracle level and the cited positive; `"include"`), the BDDL problems
  `scripts/behavior/bddl/` (BEHAVIOR-1K's `bddl` package, MIT: `/behavior-src/bddl3/bddl/activity_definitions/<task>/problem0.bddl`
  in the image), the frozen instances `scripts/behavior/instances/` and the reference solutions
  `scripts/behavior/solutions/`, plus the eai-standard/2.2 layer from `scripts/eai_standard/`. A rerun reproduces the
  committed tasks; `mk_tasks.py --check` regenerates into a temporary tree and diffs. It writes every README in the
  protocol's layout and ends each task with `scripts/task_conventions.py`'s `normalize()`, like every generator.
  `scripts/behavior/goal.py` words each BDDL predicate a goal uses, with OmniGibson's thresholds. Agent results are not
  in the repository (PROTOCOL D3): the positives are cited by trial id, results-site log and Hugging Face replay.
- The predicate is the task's official BDDL goal (OmniGibson object states), checked at every control step; the episode
  ends the moment it holds. The challenge's timeout is lifted to a runaway guard (time is the budget, not steps).
- Frozen instance: the full simulator state after the challenge's own instance load (`Evaluator.load_task_instance`) and
  its hash, in `environment/`, `tests/` and the standard sidecar. Another host may rebuild it within the pose tolerance but
  not bit-exactly (`instance_exact = 0`, `instance_ok = 1`); grading needs `instance_ok`.

| family | oracle | evidence (PROTOCOL §2.7) |
|---|---|---|
| picking_up_trash, putting_shoes_on_rack | `partial` | human-written reference solutions on the frozen task-level primitives `solution/rcb_behavior_ref.py`; the standard oracle streams the privileged oracle's joint targets through the client. They scored 1 on earlier versions (`oracle_evidence` cites the runs; picking_up_trash privileged 1 of 3), and the standard twins' service, collect hook, grader and oracle client changed since (crash recovery): not re-run on this version, hence not `full` |
| clean_up_broken_glass, collecting_aluminum_cans, composting_waste, dispose_of_glass, hiding_Easter_eggs, installing_a_scanner, stacking_wood, tidying_bedroom, turning_on_radio | `none` | a privileged model trial graded 1 by the separate verifier on a pre-v1.0 version (trial id, agent log and replay in `oracle_evidence` and the README); human review per family |

The labels follow one rule: `full` only when a recorded oracle run scored 1 on a byte-identical grader, frozen instance and
oracle code, with every tooling change since shown to be off the oracle and replay path. This version was validated
statically (CI, the generator's `--check`), not re-run.

**Loose official goals** (reported, the official judgement is kept): `stacking_wood` only needs every log to touch
another log (no stack; its positive pushed the logs together with the robot body); `hiding_Easter_eggs` only needs the
eggs on the lawn next to one tree and out of the basket (nothing is hidden). Of the families kept out,
`laying_tile_floors` is loose too (tiles on the floor, each `nextto` another).

## Time budget (D8)
14400 s (the protocol maximum) for every task of both modes, the same in the whole benchmark:
- every Python process pays an Isaac launch and scene load: about 2-3 minutes with a warm Kit cache, and the first launch
  of a trial adds about 4 minutes to compile shaders into the trial's own cache (below);
- the simulator runs 7-18 control steps/s depending on the host (30 Hz control), and these tasks take thousands of
  steps: the 9 positives are 1,374-7,200 control steps long, the challenge's teleoperators averaged 531 s (15,939 steps)
  for stacking_wood alone;
- measured: the 9 positives used 2,251-12,791 s of agent time (median 7,917 s); 8 of the 9 would not have finished in
  the 3600 s default.

The standard collect hook may take up to 6 h for the two replays of a long episode (`[[verifier.collect]] timeout_sec`).

## Kit cache: one per trial
Isaac keeps shaders and generated Python in its Kit cache (`/cache`). Every compose file names its cache volume without a
fixed `name:` (`rcb_behavior_cache` for the agent, `rcb_behavior_cache_trusted` for the verifier and the standard
sidecar): compose prefixes it with the trial's project name, side-by-side trials never share it, and Harbor's teardown
(`compose down --volumes`) deletes it. Measured on ws: a scene load takes 359 s on a cold cache and 110 s on a warm one,
so each container pays about 4 minutes once (the agent's first `Session`, the sidecar's start, the verifier's first
replay; the second replay reuses the cache). That is under 2 % of the agent budget, and it removes a global volume that
agents of different trials could write and that a concurrent trial's teardown could delete. A read-only shared cache
was the alternative: Kit writes to its cache at run time, so it would need a host-prepared cache plus a writable copy per
container, outside Harbor's lifecycle. A cache can reach ~10 GB (one probe volume: 9.8 GB); it lives as long as the trial.

## Host notes (host-local, never committed)
- **GPU pin.** `count: 1` always gives GPU 0. A host whose BEHAVIOR GPU is another one (lab) pins it at run time with a
  host-local compose override (`device_ids` on `main` / `sim`, like lab's verifier-subnet patch), applied to its own copy
  of the tasks and written down in that host's notes, never committed: a committed `device_ids` is a MUST NOT
  (PROTOCOL §2.4).
- **Docker address pools.** A host with exhausted pools (lab) gives each trial explicit subnets (its agent environment
  through an extra compose file, its separate verifier through a patch of its copy of `tests/docker-compose.yaml`). The
  standard verifier needs no network (`no-network`).
- **Privileged verifier network.** The privileged verifier keeps Harbor's default network instead of `no-network` (a
  SHOULD, PROTOCOL §2.6): it starts Isaac Sim, and an Isaac / Omniverse Kit start without any network has not been
  tested. It downloads nothing: the dataset is mounted and the image is complete.

## Grading and determinism
- Privileged: the verifier replays `trajectory.npz` from the frozen instance in **two fresh processes** (an in-process
  reset is approximate; the first replay in a fresh process reproduces a live run bit for bit) and needs the goal after
  both, equal final-state hashes and `instance_ok`.
- Standard: the service dumps the episode (artifacts under `/out`, since `/data` is the dataset) and exits on the collect
  hook's signal; the hook replays it in two fresh processes (`environment/sim/finalize.sh`); `success = live ∧ replay ∧
  deterministic`, `live_matches_replay` reported separately. OmniGibson declares rollouts nondeterministic; measured so
  far, a live run and its fresh replay agree.

## Standard mode (eai-standard/2.2)
`joint_position` (25: base per-step targets in the robot frame, trunk, arms, grippers; base and grippers switch at the
row) and `ee_pose` (16, left first, xyzw, cuRobo IK for both end effectors per row, base still); the head camera and two
wrist cameras (link-mounted, 224×224); OmniGibson `depth_linear`; `/kinematics` on a numpy model of the articulation
(trunk + arms, cuRobo fallback; base frame unless `base_pose` is given); 121 proprio columns. STANDARD_MODE_2_2.md §16.

Crash recovery (STANDARD_MODE_2_2.md §13): the adapter `environment/sim/server.py` journals every executed control step
(`journal.f64`), checkpoints every completed call with the full simulator state hash (`og.sim.dump_state`) and the robot's
proprio row, and resumes the same episode after compose's `restart: on-failure:6`. Resume class **`approx`**: a hash
mismatch after the journal replay is recorded (`resume_state_mismatch`) and the episode continues unless a TCP is more
than 0.05 m from its checkpoint. `RCB_STARTUP_TIMEOUT_S` = 1800 s: scene builds measured 130-404 s on a warm cache
(laptop trials) and 433-519 s cold on a loaded lab, plus the trial's cold-cache shader compile (~4 min); 1800 s is at
least twice every measured build. A resume replays the episode at ~14-20 steps/s (a 50k-step episode: 45-60 min of
downtime on the agent's wall clock). Artifacts: `final.json`, `episode.jsonl`, `trajectory.npz`, `journal.f64`,
`startups.jsonl`, `server.log`, the replays' logs and video.

## Tooling (file names)
| main's convention | BEHAVIOR-1K |
|---|---|
| `environment/rcb_traj.py` (privileged tooling, `Session`) | `environment/rcb_behavior.py` (`Session`: the frozen instance, thin primitives, the robot's cameras, recording, replay) |
| `tests/rcb_traj.py` | `tests/rcb_behavior.py` |
| standard sidecar | `environment/sim/server.py` (2.2 adapter), `finalize.sh`, `rcb_behavior.py`, the robot config; `rcb_limited.py`, `rcb1.py`, `run.sh` from `scripts/eai_standard/` |
| reference tooling | `solution/rcb_behavior_ref.py` (frozen; the oracle agent only) |
| `rcb_client.py`, `rcb1.py` | the same names (`scripts/eai_standard/`); the agent container and the verifier are FROM the shared digest-pinned client image (`scripts/eai_standard/client.env`), the agent's pip pins are `environment/client-requirements.txt` |

The tooling records 25-D actions (base + trunk + arms + grippers) at 30 Hz. Every copy of the tooling and of the standard
sidecar files is byte-identical across the benchmark (`check-tooling-identity.sh`).

## Declarations
- **Tooling: thin wrappers only.** Joint moves, a straight-line base drive, cuRobo IK moves, gripper commands and the
  robot's cameras. Task-level skills (grasp, place, navigate) are never added to the agent's tooling; the reference
  solutions keep theirs in `solution/rcb_behavior_ref.py`.
- **World-frame information (D7).** Standard tasks never say where things are in the world (STANDARD_MODE_2_2.md §10,
  `check-limited-texts.sh`); the convention that the floor is the plane z = 0 defines the world frame and is given.
  Privileged tasks give the privileged state through the tooling.

## Licences
BEHAVIOR-1K code (including the BDDL activity definitions): MIT; the BEHAVIOR Data Bundle: no redistribution (mounted,
never copied); Isaac Sim 5.1 and Omniverse Kit: NVIDIA proprietary (no redistribution), hence BUILD_ONLY.

## Known issues
- While the robot moves, a frame shows the scene 2 control steps before its `frame_step` (renderer latency).
- The per-call state hash (`og.sim.dump_state`, read-only) is new with crash recovery: the validation re-checks that
  `live_matches_replay` stays 1 on the standard oracles.
- `turning_on_radio`: the radio shows no visual change when it is on, so a standard-mode agent cannot see its success.
