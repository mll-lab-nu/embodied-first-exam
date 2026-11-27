# HumanCLAW

## Overview

Find, navigate and interact with a simulated human body: in a furnished HSSD house, find an object of a category,
walk until the body touches it and, for a bed, couch or toilet, sit on it, using nothing but whole-body motion
skills. No arm, no gripper: the robot is an SMPL-X human body, moved by HumanCLAW's MotionDiT skill models under
Half-Physics. 55 frozen episodes in two modes: 110 task directories,
`tasks/humanclaw/humanclaw-{nav,sit}-<category>-i<NN>-privileged` and `-standard`.

| | |
|---|---|
| upstream | HumanCLAW (HumanClawBench, Siyao et al., 2026, [Human-CLAW/HumanCLAW](https://github.com/Human-CLAW/HumanCLAW)), a source snapshot at commit `fe3d376` (tree `f60d71a0` of `harnesses/humanclaw`); profile `paper_fullval_v1` (1,218 val episodes in 41 HSSD scenes) |
| simulator | Habitat-Sim `acbe6f4` with HumanCLAW's Half-Physics patch (Bullet `2c204c4`), MotionDiT flow-matching skills (30 NFE midpoint), GPU (EGL rendering, CUDA) |
| robot | `smplx-human`: HumanCLAW's SMPL-X neutral body, 8 motion skills (walk, turn, side step, step back, climb up / down a step, sit, stop) |
| score | HumanCLAW's own metric code, unchanged (`evaluation/metrics/episode.py`): NavSR@20cm (chair, TV) or InteractSR (bed, couch, toilet) |
| image | `ghcr.io/mll-lab-nu/efe-private:humanclaw-<VERSION>` (`images/humanclaw/`, BUILD_ONLY: see Others) |

| | privileged | standard |
|---|---|---|
| the agent has | the simulator (`hc_tools.Env`): the body's pose, the targets' boxes, the navmesh, free resets | a client: the head camera (448 x 448 RGB, 90° fov), actions used / left, the pelvis' height change |
| deliverable | `trajectory.npz` (`actions`, T <= 100 rows) | none: the sidecar records and grades the live episode |
| graded by | one fresh-process replay from the verifier's copy of the instance | the live episode (HumanCLAW's `finalize` at the stop, in the sidecar); nothing replayed |

## Upstream and license

| part | licence | in the image |
|---|---|---|
| HumanCLAW code (episode loader, Half-Physics env, skill runner, metrics) | Apache-2.0 | yes (LICENSE, NOTICE in `/opt/humanclaw`) |
| Habitat-Sim, its Half-Physics patch; Bullet | MIT; zlib | yes |
| HSSD scenes (`hssd/hssd-hab`) and HumanCLAW's val41 supplement (`HumanCLAW/HumanCLAW-HSSD`) | **CC BY-NC 4.0** (non-commercial), gated (terms accepted per user on Hugging Face) | yes: may be used, not redistributed |
| the body model (convex hulls and joint centres derived from SMPL-X / SMPL) | SMPL-X / SMPL model licences: **non-commercial research**, no redistribution | yes |
| MotionDiT `paper_fullval_v1` weights (`HumanCLAW/HumanCLAW`) | released with the code; trained on AMASS / BABEL (**non-commercial research**) | yes |

The image is private (BUILD_ONLY) and each user builds it under their own acceptance of these terms; the task
directories hold only the frozen episodes (scene ids, start poses, goal objects) and this repository's code. The
HumanCLAW source is fetched by commit from this repository's history (`fe3d376`, its `harnesses/humanclaw` tree hash
checked), without its docs, tools, harnesses, experiment configs and episode shards.

## Changes from upstream

- The motion model's noise is seeded at every reset (torch / numpy / random, seed 0). HumanCLAW never seeds it, so its
  rollouts of the same actions differ run to run; seeded, an episode is a function of the actions on a given GPU
  model, which a submitted trajectory and a crash-resume both need. Across GPU models the motion model's arithmetic
  differs in the last bits and the physics amplifies it, so the verifier replays on the machine the agent ran on.
- A reset rebuilds the simulator (HumanCLAW builds a fresh one per rollout too), so moved furniture comes back.
- The agent is not HumanCLAW's VLM pipeline (planner + verifier, history of 10): it calls the skills directly. Actions
  are mapped to HumanCLAW's skill calls by its own planner code (`_chooser_action`), so its clamps apply.
- Videos are rendered after the verdict from the poses the episode recorded frame by frame (HumanCLAW's own delayed
  renderer), so the frames are the graded episode's, not a re-run. The live video writer stays off as in HumanCLAW's
  paper runs (its third-person sensor can change Bullet's contact cache).
- `view_points` in the frozen goals are cut to the 5 best per goal (HumanCLAW's loader needs one; nothing it scores
  reads them).
- HumanCLAW's instruction is kept word for word ("Find the chair and move until your body is touching the target,
  with zero distance to the target object.", plus "Finally, sit on the bed." for an interaction category), followed by
  the goal in plain words: stop within about 20 cm of a target, or stop while sitting on one. HumanCLAW's own words ask
  for zero distance; its success rule does not.

## Interface

An action is a row `[action_id, value]`:

| id | skill | value |
|---|---|---|
| 0 | walk forward | 0.2 / 0.4 / 0.6 m (HumanCLAW's slow / normal / fast stride) |
| 1 | stop | 0; ends the episode: the agent declares it is done |
| 2 | turn | signed degrees, + left, \|value\| clamped to [10, 120] |
| 3 | climb up a step | 0 |
| 4 | sit down | target pelvis height in m, clamped to [0.15, 0.85] |
| 5 | step back | m, clamped to [0.10, 0.60] |
| 6 | side step | signed m, + left, \|value\| clamped to [0.10, 0.50] |
| 7 | walk down a step | 0 |

Each of 0 and 2-7 is one 0.5 s motion chunk (15 frames at 30 Hz); the stop moves nothing. An episode allows 100
actions, the stop included; the 100th ends it whatever it is.

- **Privileged.** `hc_tools.Env` gives the body's pose, the targets' boxes, the navmesh and free resets; `Env.save()`
  writes the trajectory.
- **Standard.** The `sim` sidecar serves the head camera (448 x 448 RGB, 90° fov), the actions used and left, and the
  pelvis' height above its start, through `rcb_client.py` and the `efe-robot` MCP tools (wire protocol
  `eai-standard/3.0`). `POST /finish` is the stop: it runs the stop action as the episode's last step. A hold chunk
  adds idle control steps and uses no action. Not given: the body's position, the target's position, a map, the
  success signal.

Network: HumanCLAW's public repository holds recorded rollouts of these very episodes, so the agent reaches the model
APIs and the package registries only (`allowlist`), in both modes.

## Grading

- **Navigation** (chair, TV): NavSR@20cm. The episode ends with a stop, and the shortest distance from the body to
  the bounding box of a target object is at most 0.2 m.
- **Interaction** (bed, couch, toilet): InteractSR. The episode ends with a stop, it contains at least one sit, and
  the pelvis touches a target object's mesh on the last physics frame of the last motion.
- **Privileged.** `tests/grade.py` replays `trajectory.npz` once in a fresh process on the verifier's own copy of the
  instance and tools; a rebuilt start whose hash differs from `instance.json`'s `start_sha`, a replay that dies or
  times out, or a grader error is `grader_error` with `infra_error`. A missing or malformed file, an invalid row, or
  actions that end without a stop are the agent's 0.
- **Standard.** The sidecar judges the live episode at the stop. The end of the agent's session runs the stop first
  (reason `timeout`) and the episode is judged there; a non-stop 100th action fails (`step_limit`). No reset
  (`RCB_RESET_BUDGET=0`).

## Tasks

55 frozen episodes of HumanCLAW's full validation set, each in both modes: bed 22, couch 12, toilet 9, TV 11, chair 1,
in 23 of the 41 scenes. One task is one episode: the scene, the body's start pose (HumanCLAW's own spawn values), the
target category and its goal objects. Each episode keeps the number it has among all 1,218, so the numbers have gaps.

Selection rule: every one of the 1,218 validation episodes was attempted once in each mode by the same agent
configuration, and the 55 episodes that were not solved in either mode are the ones kept. Upstream episode ids are
kept outside the repository; no agent-readable file names them.

## Others

**Building the image.** The tasks' shared code (`embodied_first_exam/benchmarks/humanclaw/`: the privileged tools, the
sidecar service, the grader) comes from the public files-only image `images/humanclaw-files/` (`COPY --from`, pinned
by digest); only the simulator image is private. `images/humanclaw/` builds
`ghcr.io/mll-lab-nu/efe-private:humanclaw-<VERSION>` (21.8 GB): HumanCLAW's code, Habitat-Sim, the motion weights and
the 41 HSSD scenes. It is **BUILD_ONLY** (`images/humanclaw/BUILD_ONLY` has the licences and the full recipe notes).
A runner with access to the organization's packages pulls it. Anyone else builds it once, from the repository root:
1. On Hugging Face, request access to the gated dataset `HumanCLAW/HumanCLAW-HSSD` (approved automatically) and accept
   the terms of `hssd/hssd-hab`.
2. Make a read token and export it: `export HF_TOKEN=hf_...`
3. Build under the tag the tasks' `cache_from` names (the token goes in as a BuildKit secret, never into a layer):
   `docker buildx build --builder default --secret id=hf_token,env=HF_TOKEN -t ghcr.io/mll-lab-nu/efe-private:humanclaw-$(cat images/humanclaw/VERSION) images/humanclaw`
   It takes about 30 minutes on a 32-core host, no GPU, and about 40 GB of free disk under Docker's data root.
4. `harbor run -p tasks/humanclaw/<task> ...` then builds each task from the local build cache: no token, no download,
   seconds. Keep that cache (`docker builder prune` drops it).

Running needs an NVIDIA GPU (EGL rendering and the motion model on CUDA; compute capability 8.0 to 9.0). A privileged
trajectory replays bit for bit only on the GPU model it was made on.

**Reference solutions.** `solution/` holds a reference trajectory for 4 of the 55 episodes (`oracle = "full"`); the
others have none (`oracle = "none"`, said in their `oracle_evidence`). Because a trajectory replays exactly only on
the GPU model it was recorded on, `solve.sh` replays it first and, where it fails on the machine at hand, records it
again there.
