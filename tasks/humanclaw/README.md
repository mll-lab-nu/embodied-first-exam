# HumanCLAW

Find, navigate and interact with a simulated human body: in a furnished HSSD house, find an object of a category,
walk until the body touches it and, for a bed, couch or toilet, sit on it, using nothing but whole-body motion
skills. No arm, no gripper: the robot is an SMPL-X human body, moved by HumanCLAW's MotionDiT skill models under
Half-Physics.

| | |
|---|---|
| upstream | HumanCLAW (HumanClawBench, [Human-CLAW/HumanCLAW](https://github.com/Human-CLAW/HumanCLAW)), a source snapshot at commit `fe3d376` (tree `f60d71a0` of `harnesses/humanclaw`); profile `paper_fullval_v1` (1,218 val episodes in 41 HSSD scenes) |
| simulator | Habitat-Sim `acbe6f4` with HumanCLAW's Half-Physics patch (Bullet `2c204c4`), MotionDiT flow-matching skills (30 NFE midpoint), GPU (EGL rendering, CUDA) |
| robot | `smplx-human`: HumanCLAW's SMPL-X neutral body, 8 motion skills (walk, turn, side step, step back, climb up / down a step, sit, stop) |
| score | HumanCLAW's own metric code, unchanged (`evaluation/metrics/episode.py`): NavSR@20cm (chair, potted plant, TV) or InteractSR (bed, couch, toilet) |
| tasks | all 1,218 frozen episodes x 2 modes (2,436 task dirs): `tasks/humanclaw/humanclaw-{nav,sit}-<category>-i<NN>-privileged` and `-standard` (`eai-standard/2.1`) |
| image | `ghcr.io/mll-lab-nu/efe-private:humanclaw-<VERSION>` (`images/humanclaw/`, BUILD_ONLY: without access to the organization's packages, build it once yourself, Before you run below) |

## The task
One task = one frozen episode of HumanCLAW's full validation set: the scene, the body's start pose (HumanCLAW's own
spawn values), the target category and its goal objects, HumanCLAW's instruction word for word ("Find the chair and
move until your body is touching the target, with zero distance to the target object.", plus "Finally, sit on the
bed." for an interaction category). An action is a row `[action_id, value]`, one motion skill of 0.5 s (15 frames at
30 Hz), mapped to HumanCLAW's skill calls by its own planner code (`_chooser_action`, so its clamps apply). An episode
allows 100 actions, the stop included, and has no reset; success needs an explicit stop (HumanCLAW's active stop).

| | privileged | standard |
|---|---|---|
| the agent has | the simulator (`hc_tools.Env`): the body's pose, the targets' boxes, the navmesh, free resets | a client: the head camera (448 x 448 RGB, 90° fov), actions used / left, the pelvis' height change |
| deliverable | `trajectory.npz` (`actions`, T <= 100 rows) | none: the sidecar records and grades the live episode |
| graded by | two fresh-process replays from the verifier's copy of the instance: both succeed, equal final state hashes | the live episode (HumanCLAW's `finalize` at the stop, in the sidecar); nothing replayed |
| video | the first replay's recorded poses, rendered after the verdict | the live episode's recorded poses, rendered after the verdict |
| time cutoff | 3600 s | 3600 s |

What differs from HumanCLAW's own evaluator:
- The motion model's noise is seeded at every reset (torch / numpy / random, seed 0). HumanCLAW never seeds it, so its
  rollouts of the same actions differ run to run; seeded, an episode is a function of the actions on a given GPU
  model, which a submitted trajectory and a crash-resume both need. Across GPU models the motion model's arithmetic
  differs in the last bits and the physics amplifies it, so the verifier replays on the machine the agent ran on.
- A reset rebuilds the simulator (HumanCLAW builds a fresh one per rollout too), so moved furniture comes back.
- The agent is not HumanCLAW's VLM pipeline (planner + verifier, history of 10): it is whatever the harness runs, and
  it calls the skills directly.
- Videos are rendered after the verdict from the poses the episode recorded frame by frame (HumanCLAW's own delayed
  renderer: it restores each recorded post-physics pose and renders; simulation never advances), so the frames are the
  graded episode's, not a re-run. The live video writer stays off as in HumanCLAW's paper runs (its third-person sensor
  can change Bullet's contact cache).
- `view_points` in the frozen goals are cut to the 5 best per goal (HumanCLAW's loader needs one; nothing it scores
  reads them).

Network: HumanCLAW's public repository holds recorded rollouts of these very episodes (its docs/analysis has
action chains), so the agent reaches the model APIs and the package registries only (`allowlist`), in both modes.

## Selection (model-calibrated with Codex + GPT-6 Astra r3)
The 100 episodes were chosen from HumanCLAW's own full-validation runs of Codex + GPT-6 Astra, condition `codex_r3`
(Codex CLI 0.145 with HumanCLAW's own Codex wrapper, reasoning effort max, an image window of 50; 64.2 % of the 1,218
episodes), using that run's per-episode outcome only:
- two halves of 50, each 25 navigation (chair 9, potted plant 8, TV 8) + 25 interaction (bed 9, couch 8, toilet 8):
  one at r3 success 15 / 50 = **30 %** (chair 3, potted plant 2, TV 3, bed 3, couch 2, toilet 2), the other at
  30 / 50 = **60 %** (5 per category); so the whole set (all 100) is at 45 % under r3;
- within a (category, r3 outcome) cell: fewest picks from the same scene first (at most 3 episodes per scene; 41 scenes),
  then outcomes that HumanCLAW's other runs on the same model agree with (no flukes), then a fixed random order.
The calibration run is not an EFE run: HumanCLAW's wrapper and VLM loop, an older Codex CLI, effort max, and no
privileged mode. None of the 100 is in the core set yet: an EFE run over the tasks comes first.

The other 1,118 canonical episodes are here too, not chosen by calibration: the 20 reserves of the selection share the
first numbers of their category (up to `i22`) with the 100, the rest follow in (scene, episode) order. Upstream episode ids and the
per-episode outcomes are kept as trusted provenance outside the repository; no agent-readable file names them.

## Before you run
The tasks' shared code (this repository's `embodied_first_exam/benchmarks/humanclaw/`: the privileged tools, the
sidecar service, the grader) comes from the public files-only image `images/humanclaw-files/` (`COPY --from`, pinned by
digest); only the simulator image is private.

`images/humanclaw/` builds `ghcr.io/mll-lab-nu/efe-private:humanclaw-<VERSION>` (21.8 GB): HumanCLAW's code, Habitat-Sim,
the motion weights and the 41 HSSD scenes. It holds data that may not be redistributed, so it is **BUILD_ONLY**
(`images/humanclaw/BUILD_ONLY` has the licences and the full recipe notes). A runner with access to the organization's
packages pulls it. Anyone else builds it once, from the repository root:
1. On Hugging Face, request access to the gated dataset `HumanCLAW/HumanCLAW-HSSD` (approved automatically) and accept
   the terms of `hssd/hssd-hab`.
2. Make a read token and export it: `export HF_TOKEN=hf_...`
3. Build under the tag the tasks' `cache_from` names (the token goes in as a BuildKit secret, never into a layer):
   `docker buildx build --builder default --secret id=hf_token,env=HF_TOKEN -t ghcr.io/mll-lab-nu/efe-private:humanclaw-$(cat images/humanclaw/VERSION) images/humanclaw`
   It takes about 30 minutes on a 32-core host (Habitat-Sim's compile and the HSSD download), no GPU, and about
   40 GB of free disk under Docker's data root.
4. `harbor run -p tasks/humanclaw/<task> ...` then builds each task from the local build cache: no token, no download,
   seconds (the failed cache import from the private package is only logged). Keep that cache (`docker builder
   prune` drops it).

Running needs an NVIDIA GPU (EGL rendering and the motion model on CUDA; compute capability 8.0 to 9.0). A
privileged trajectory replays bit for bit only on the GPU model it was made on (The task, above).

## Licences
| part | licence | in the image |
|---|---|---|
| HumanCLAW code (episode loader, Half-Physics env, skill runner, metrics) | Apache-2.0 | yes (LICENSE, NOTICE in `/opt/humanclaw`) |
| Habitat-Sim, its Half-Physics patch; Bullet | MIT; zlib | yes |
| HSSD scenes (`hssd/hssd-hab`) and HumanCLAW's val41 supplement (`HumanCLAW/HumanCLAW-HSSD`) | CC BY-NC 4.0, gated (terms accepted per user on Hugging Face) | yes: may be used, not redistributed |
| the body model (convex hulls and joint centres derived from SMPL-X / SMPL) | SMPL-X / SMPL model licences: non-commercial research, no redistribution | yes |
| MotionDiT `paper_fullval_v1` weights (`HumanCLAW/HumanCLAW`) | released with the code; trained on AMASS / BABEL (non-commercial research) | yes |

So the image is private (BUILD_ONLY) and each user builds it under their own acceptance of these terms; the task
directories hold only the frozen episodes (scene ids, start poses, goal objects) and this repository's code.

## Reference solution
A navmesh oracle with the privileged tools (`solution/oracle.py`): Habitat's shortest path (on a navmesh for a wider
body) to the nearest goal viewpoint or to a reachable point beside a target box, turn-and-walk along it, close in with
short strides, then, for an interaction episode, HumanCLAW's own sitting recipe (turn the back to the target, step
back, sit at the category's height until the pelvis touches it), then stop; it tries a few variants with free resets.
It solves 84 of the 100 episodes (39 / 50 in the 30 % half, 45 / 50 in the 60 % half) and 15 of the 20 reserves; the
failures have no reference solution (`oracle = "none"`): targets behind furniture or up a step, and seats the body does
not land on. Of the other 1,098 episodes, 11 were searched so far (9 solved); the rest have
`oracle = "none"` until the search reaches them (their `oracle_evidence` says so).
- privileged: `solution/actions.json` is the oracle's trajectory, replayed twice in fresh processes to success with
  equal final hashes on the GPU model named in `oracle_evidence`. The physics amplifies the last-bit differences of the
  motion model between GPU models (an RTX 4090 and an L40S agree on the start hash, never on the final one, and on
  about 1 trajectory in 10 not even on the verdict), so `solve.sh` replays it first and, where it fails on the
  machine at hand, runs the oracle again closed loop there.
- standard: the same actions streamed as `skill` rows through the client (open loop, so they hold on the GPU model
  named in the evidence).
