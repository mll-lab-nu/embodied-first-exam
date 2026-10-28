# HumanCLAW experiment runs on Klone

This guide covers HumanCLAW experiments on Klone, including the native Codex
and Pi rollout preparation. LIBERO-Pro remains deferred. The original single
episode batch template does not install software, download assets, start a VLM
server, or provision resources beyond its explicit Slurm request.

## Deployment progress, 2026-10-13

Code and all nine verified motion checkpoints are deployed. CPU setup job
`41851784` completed successfully: Python 3.11.17, PyTorch 2.6.0+cu124,
the pinned Habitat-Sim source with the HumanCLAW patch, and Magnum bindings.
Habitat imports with Bullet enabled. The initial project suite reported 224
passed, 1 skipped; the package snapshot is
`/gscratch/stf/hengyil6/outputs/environment-41851784.txt`.

The authorized HSSD supplement is installed and verified. All 10,545 required
public HSSD files (3.58 GB) passed local checks and have been transferred to
Klone. CPU scene-assembly job `41853305` completed: all hashes were checked on
the server, the 41-scene dataset was published, and the updated project suite
reported **234 passed, 1 skipped**. The prepared dataset contains 14,537 object
instances and 12,112 mesh links, including all 1,693 supplemental assets.

GPU validation job `41853308` on an RTX 2080 Ti passed CUDA motion generation
and the Half-Physics controller contract, then failed at EGL initialization.
Klone's GLVND module searches `/usr/local` vendor directories by default, while
the NVIDIA driver JSON is under `/usr/share/glvnd/egl_vendor.d`. The environment
script now includes the system vendor directories, preserving explicit user
overrides. This follows GLVND's documented
[vendor discovery settings](https://github.com/NVIDIA/libglvnd/blob/master/src/EGL/icd_enumeration.md).
Graphics diagnostic `41853965` and complete runtime recheck `41853996` both
finished with Slurm `COMPLETED`, exit `0:0`. The latter ran on `g3027`, using
an RTX 2080 Ti, NVIDIA driver 580.178.04, two CPUs and 16 GB host memory under
`ckpt-stf` / `ckpt-all` / `ckpt-gpu`. It completed in 1 minute 37 seconds:

- All eight motion skills loaded; a finite 15 × 75 motion chunk was generated.
- The Half-Physics controller contract passed.
- HSSD scene `102343992` loaded and produced 26 frames per ego/exo video view.
- Physics replay reproduced 25 frames and 120 dynamic objects with zero measured
  discrepancy in the checked body poses and object transforms.
- Saved-pose rendering produced both video views from all 25 recorded frames.

The final report is
`/gscratch/stf/hengyil6/outputs/runtime-smoke-41853996-readiness.json`.
The report, source trajectory, replay reports and four short videos are also
saved locally under `outputs/klone-validation/`. The failed run and its logs are
retained. These checks establish simulator readiness for this scene; the
remaining 40 scenes have passed asset validation, not individual runtime tests.

This is environment validation, not a benchmark rollout. The report records
`model_api_calls: 0` and `benchmark_result: false`; its synthetic planner usage
must not be included in experiment statistics. No server model call or benchmark
episode was part of that environment check.

## First online episode, 2026-10-14

The user subsequently authorized uploading the Azure key and running one full
HumanCLAW episode with deployment `gpt-6-astra`. Only `AZURE_OPENAI_API_KEY` was
transferred over SSH into the server project's `.env`, with permissions `0600`;
the HF token remains local. The server's image/JSON API check passed, reporting
78 tokens and 50.635 seconds. Its report is
`/gscratch/stf/hengyil6/outputs/azure-api-check-phHlzRQA.json`; its usage is separate
from the benchmark episode.

The episode uses `humanclaw_psv`, seed 0, the full profile's 100-step budget and
one worker. `HC_SAVE_VIDEO=1` enables online ego/exo video.
`HC_VALIDATE_REPLAY=1` runs `tools/validate_episode_run.py` after the episode,
inside the same GPU allocation. It validates the trace and referenced assets,
records token/cost/latency and tool/module coverage, decodes the saved videos,
then runs full log, physics and saved-pose render replay. It writes
`validation/validation.json` and keeps independent replay reports; validation
never makes another model call. Task success is recorded separately from
whether the pipeline passed its checks. With no configured Azure price card,
currency cost remains unknown rather than being reported as zero.

Each submitted episode also writes `slurm_environment.json` with the actual
GPU, driver and allocation. This first run validates the pipeline; comparisons
of harness latency must use a consistent hardware and video configuration.

After the user enabled Full Access, Slurm accepted job **41874913**. It requests
one RTX 2080 Ti through `ckpt-stf` / `ckpt-all` / `ckpt-gpu`, eight CPU cores,
32 GB host memory and at most three hours. This is a single full episode with
the post-run validation above, not a batch benchmark. The actual allocation
is recorded in the run's `slurm_environment.json`.

- Output: `/gscratch/stf/hengyil6/outputs/one-humanclaw_psv-41874913/`
- Slurm logs: `/gscratch/stf/hengyil6/outputs/slurm-41874913.out` and `.err`
- Final pipeline report: `validation/validation.json` under the output directory.

Job **41874913 completed with exit `0:0` at 11:16:33 PDT on 2026-10-14**,
on `g3015` with an RTX 2080 Ti and NVIDIA driver 580.178.04. Both the rollout
step and the post-run validator completed successfully. The final pipeline
report is `passed`, with no errors:

- Scene `102343992`, episode `0`, target `bed`: all 100 decision steps ran.
  The embodied task failed: no successful find/navigation/sit, no sit action,
  and final body-to-target AABB distance 1.558958 m. This is one completed
  unsuccessful episode, not a benchmark-suite success-rate estimate.
- All 169 recorded model calls completed. Exact provider usage was 437,472
  input tokens plus 40,363 output tokens, totaling **477,835**. Output includes
  8,387 reasoning tokens; they are not added again. Currency cost is unknown.
- The trace has no errors, warnings, or open spans. It records 100 planner
  calls, 69 verifier calls, and 100 each of history updates, motion generation,
  decision metrics, and motion metrics. Executed actions were 58 forward
  walks, 30 turns, four side walks, and eight upward steps.
- Both original video views decode completely: 1,501 frames each at 30 fps,
  including the reset frame.
- Full physics replay checked all 100 motion chunks, 1,500 frames, and 120
  dynamic objects. All checked body-pose and object-transform maximum errors
  were zero at the unchanged default tolerances.
- Saved-pose rendering produced both views from all 1,500 frames. Both videos
  passed decoding and frame-count checks. Validation made zero model calls.

The recorded episode took **53 minutes 38 seconds**, including shared-storage
stalls; model calls occupied 25 minutes 33 seconds. The entire Slurm allocation
took **1 hour 7 minutes 37 seconds**, including setup and 6 minutes 42 seconds
of post-run validation. These timings are not clean hardware/harness comparison
measurements because the GPFS stalls were observed during trajectory writes.

The complete trace, metrics, trajectory archives, reports, Slurm logs and four
videos are also saved locally under `outputs/klone-rollout-41874913/`, with a
readable `STATUS.md`. The earlier synthetic-image API check remains separate
from this episode's token accounting.

## Full baseline suite, 2026-10-14

The user authorized all **1,218 fullval episodes**, using `humanclaw_psv` with
Azure deployment `gpt-6-astra`, with **no API budget cap**. The suite preserves
seed 0, the 100-step profile, trace, metrics and online video. The previously
completed single episode remains a separate framework validation attempt.

The suite is prepared in its own directory under
`/gscratch/stf/hengyil6/experiments/`, with a frozen `source/`, hashed source and
episode-selection manifests, and independent `results/`, `logs/` and
`allocations/` directories. Runtime imports explicitly use the frozen source;
changes to the development checkout do not enter queued episodes. Credentials
are not in the snapshot archive: its `.env` link reads the already authorized
private server credential file. Scene data and verified weights are shared.
Keep `/gscratch/stf/hengyil6/envs/humanclaw` stable during this evaluation;
install future harness dependencies in a separate environment.

`tools/klone_fullval.sbatch` runs up to four episodes per array task, for
**305 shards and at most four simultaneous GPUs**, using the validated RTX
2080 Ti type, eight CPUs and 32 GB memory per task, with an eight-hour limit.
The array permits Slurm requeue after preemption. `--resume` skips only complete,
valid, configuration-matching episodes; interrupted episodes restart from the
beginning and retain their previous trace attempts. This is not a per-step
agent checkpoint. Failed task outcomes are valid completed episodes and are
not retried simply to improve success rate.

Every allocation/restart writes a separate status record before simulator
initialization, so a failure before trace creation remains visible. Abrupt
SIGKILL can leave that record nonterminal; retain Slurm accounting alongside it.
`tools/klone_fullval_report.sbatch` runs after the array ends, including failures,
and builds `suite_summary.json` without model calls. Its `outcomes` section
uses the fixed 1,218-episode denominator; `all_attempts` includes tokens, cost,
latency and capability usage from interrupted attempts as well. Multiple
completed attempts for one identity are flagged as ambiguous, not cherry-picked.
Paper metrics from existing `metrics.json` files remain a separate view with
their recorded-file coverage. Prices remain unknown without an explicit rate
card. Full physics/render replay is available on saved runs but is not repeated
automatically for every baseline episode.

Submission receipts, array IDs and final report dependency belong in the suite
directory; preparing these files alone does not mean the jobs were submitted.
The suite manifest and launch records are authoritative for actual queue state.

## Recovery and submission, 2026-10-15

SSH access was restored. The previously prepared fullval archive was uploaded
and verified against SHA256
`62cb74cf68f07ced2660333b1aeb753d149c8db5258b0cb0eb0d465ba308947c`.
Its 14,917 frozen source files and all 305 episode selections passed validation.
No new credential transfer was needed. At 21:28 PDT Slurm accepted array
**41900792** and its after-any report job **41900793**. The baseline retains
1,218 episodes, `humanclaw_psv`, `gpt-6-astra`, seed 0, at most four concurrent
RTX 2080 Ti GPUs, and the previously authorized absence of an API budget cap.

The server suite is
`/gscratch/stf/hengyil6/experiments/humanclaw-psv-astra-fullval-20261014`.
Its `deployment_receipt.json` and `submission.json` were copied to the local
directory `outputs/humanclaw-psv-astra-fullval-20261014/`. The initial observed
array state was `PENDING (Priority)`; submission is not evidence that episodes
have begun or completed.

The native harness preparation uses separate runtime and source directories:

- `/gscratch/stf/hengyil6/native-harnesses/20261015` for Codex 0.145.0, Node
  26.0.0, Pi source/dependencies and the filesystem-isolation launcher.
- `/gscratch/stf/hengyil6/native-experiments/20261015` for the HumanCLAW native
  integration snapshot and server harness configuration.
- `/gscratch/stf/hengyil6/outputs/native-20261015` for installation, API checks,
  mock checks, native episode outputs and Slurm logs. Deployment scripts and
  fetched receipts are retained locally in `outputs/klone-native-20261015/`.

The Azure Responses preflight passed both flat and namespaced function tools:
an initial synthetic image, a tool call, a changed image in the tool result,
and continuation. All four streaming requests completed, using **481 tokens**
in total. Raw requests, responses, usage and latency are retained under
`api-preflight/`; no API authorization header is recorded. These paid transport
checks are separate from benchmark scores and episode usage.

The L40S readiness job **41901086** was submitted with `gpu-l40s-stf`, partition
`gpu-l40s`, two CPUs and one L40S. Although the account showed four unused GPU
slots, its CPU allocation was exhausted; Slurm reported `AssocGrpCpuLimit`.
It was later cancelled at the user's request, as recorded below.

Native setup job **41901088** failed before model calls because Node required
`libatomic.so.1`. The revised setup **41901156** supplies the GCC runtime
libraries in the private native runtime directory, without changing the
baseline Python environment. It passed the restricted-filesystem check, then
stopped because the Linux Codex package uses `vendor/.../bin/codex` rather than
the initially assumed path. Setup **41901236** corrects that path and repeats
both actual native processes' synthetic rollout tests. These setup attempts
make no paid model calls.

Native episode array **41901244** contains one Codex and one Pi episode,
dependent on successful native setup and L40S readiness. Each requests one
L40S, eight CPUs, 32 GB host memory and three hours. Each uses the full 100-step
episode budget and runs log/video/physics/render validation afterward. These
are pipeline-validation episodes, not full native-harness benchmark suites.
The earlier dependent array **41901209** was cancelled while still pending and
replaced after the launcher correction; none of its episodes had started.
Queue receipts and subsequent reports, not this submission description, are
authoritative for their execution and completion.

### Alternative GPU request, 2026-10-15 21:40 PDT

The user asked to stop waiting for L40S and use other available nodes. Resource
inspection found H200 nodes with jointly free GPUs, CPUs and memory. The pending
L40S readiness job `41901086` and native array `41901244` were cancelled before
execution. H200 readiness job **41901299** now gates both evaluation paths.

Native setup **41901236 completed successfully** on `n3492`, exit `0:0` in
2 minutes 35 seconds. Both native processes passed the isolated Linux mock
rollout: four synthetic model responses, two environment actions, one native
shell call, exact-once usage accounting, valid unified traces and matching mock
replay. No paid model calls were made by these mock runs. Their saved reports
are under `mock-codex-41901236/` and `mock-pi-41901236/` in the native output
directory. The shallow Git metadata index was subsequently initialized without
changing source files, so live source-diff identity does not report an empty
index as deleted source.

The 21:40 submission receipts superseded the initial GPU choices:

| Purpose | Job ID | Dependency / resources |
| --- | --- | --- |
| H200 environment readiness | **41901299** | 1 H200, 2 CPUs, 16 GB, 15 minutes |
| HumanCLAW fullval | **41901345** | after-ok readiness; 305 shards, at most 4 H200 GPUs, 8 CPUs / 32 GB per task |
| Fullval aggregate report | **41901346** | after-any fullval array |
| Codex / Pi single-episode validation | **41901308** | after-ok setup and readiness; 1 H200, 8 CPUs / 32 GB per task |

The original fullval array `41900792` and report `41900793` were still pending
when cancelled; no fullval episode had begun. The frozen source, episode list,
model configuration, seed and metrics remain unchanged. The resource change
is recorded separately in `scheduler_amendment.json`; the previous receipt is
retained as `submission-2080ti-superseded.json`. Use that amendment together
with the original suite manifest when interpreting the intended hardware.
At that point all new fullval and native runs requested the same H200 type. The earlier
RTX 2080 Ti validation episode remains separate. Requested or scheduled GPUs
are not proof of allocation: consult Slurm and each run's hardware record.

### Broader GPU allocation, 2026-10-15 21:58 PDT

The user asked to find GPUs that could start sooner. A bounded immediate
allocation probe initially returned busy. Inspection of the completed episode
showed about 3 GiB peak process RSS and 8 minutes 38 seconds of total CPU time
over 57 minutes 46 seconds. The pending H200-only arrays were replaced with
requests accepting RTX 2080 Ti, RTX 6000, A40 or L40, with 16 GiB host memory.
L40S is excluded. Model, seed, episode selection and frozen benchmark code are
unchanged. All replaced arrays were still pending; they had no episode results.

Each allocation now runs CUDA/motion, controller, scene/video, and physics/render
replay checks before model calls, using the same frozen source as its episode.
Its checks use separate diagnostic directories and no paid model calls. This
removes the global dependency on one GPU type while validating each actual
allocated device. Requeue attempts use separate diagnostic output paths.

At 21:58 PDT Slurm had allocated all four baseline workers and both native
pilot workers:

| Work | Current job / task | Allocated node and GPU | CPUs / host memory |
| --- | --- | --- | --- |
| Standalone readiness | 41901299 | g3045, A40 | 2 / 12 GiB |
| Fullval shard 0 | 41901577_0 | g3033, RTX 6000 | 4 / 16 GiB |
| Fullval shard 1 | 41901577_1 | g3036, RTX 6000 | 4 / 16 GiB |
| Fullval shard 2 | 41901577_2 | g3037, RTX 6000 | 4 / 16 GiB |
| Fullval shard 3 | 41901577_3 | g3046, A40 | 2 / 16 GiB |
| Codex pilot | 41901578_0 | g3057, A40 | 2 / 16 GiB |
| Pi pilot | 41901578_1 | g3035, RTX 6000 | 2 / 16 GiB |
| Fullval report | 41901579 | CPU job after-any 41901577 | 2 / 8 GiB |

The first three fullval workers started while CPU requests were being reduced;
their running allocations remain at four CPUs. Pending fullval tasks and native
pilots request two CPUs. Record actual GPU, CPU and memory for each allocation;
compare latency within matching hardware/resource groups rather than treating
these timings as a controlled hardware comparison. The earlier H200 arrays
41901345 / 41901308 and report 41901346 were cancelled before execution.

At this snapshot the GPU jobs were in startup checks, not completed episodes.
Live Slurm and trace events determine when actual model calls begin. The suite's
`submission.json` and `scheduler_amendment.json` identify the current jobs and
resource updates; historical H200 receipts are preserved. Operational launchers
and `anygpu_submission.json`, `cpu_request_update.json`, and `anygpu_status.json`
are retained under `/gscratch/stf/hengyil6/outputs/native-20261015/`, with copies
under local `outputs/klone-native-20261015/`.

### Live rollout audit, 2026-10-15 22:13 PDT

All six allocated episode jobs passed their own motion, simulator, video and
physics/render replay checks. The four HumanCLAW workers and Codex entered live
Azure calls and environment actions. Read-only trace validation passed for all
six attempts, including the failed Pi attempt; active runs have expected open
spans and no terminal event yet. The audit preserves provider usage categories,
capability counts, failure records and validation diagnostics in
`outputs/klone-native-20261015/rollout_audit_20261015.json`.

At that snapshot the four HumanCLAW workers had completed 21, 32, 23 and 19
decision steps respectively. Codex had completed 16 steps. Its Responses stream
contained two Azure `server_error` failures followed by successful subsequent
requests/actions. Failed calls without provider usage remain unknown in token
totals; available usage is reported as a known subtotal, not a complete total.

Pi job `41901578_1` failed before its first model request: environment-tool
discovery exceeded the hard-coded 30-second startup deadline. Its zero-step
attempt, raw log, failure event and summary are retained. A separate source
snapshot at `/gscratch/stf/hengyil6/native-experiments/20261015-pi-startupfix`
adds configurable `startup_timeout_seconds`, set to 180 for the Pi retry and
bounded by the unchanged overall episode deadline. It distinguishes discovery
timeouts from episode timeouts. Local native/integration tests passed (42 tests).
The baseline and running Codex source snapshots were not changed. CPU mock job
`41902561` gates Pi-only retry `41902562`; their receipt is
`outputs/klone-native-20261015/pi_retry_submission.json`.

The CPU check completed successfully (37 seconds, exit `0:0`) and the Pi retry
ran on an RTX 2080 Ti at `g3004`. Its GPU checks passed. Real tool discovery
took **30.56 seconds**, confirming that the previous 30-second threshold was
too short for this startup. By 22:23 PDT the retry had completed three actions
and four successful Azure calls (13,766 tokens); its trace validation passed.
Codex had reached 35 actions with three recorded Azure server errors and
continued processing. Fullval had completed its first episode successfully:
20 steps, 32 model calls and 85,764 tokens, with a clean final trace. The shard
automatically started its next episode. These are progress snapshots, not a
completed-suite success rate. See `rollout_progress_latest.json` and
`pi_retry_live_confirmation.json` in the local native-output directory.

There is no automatic server-to-laptop rollout synchronization. Complete events,
native session files, trajectories and videos stay on Klone. The local audit
retrieves small status/validation reports only. At this check, the local native
preparation directory occupied about 65 MiB, the frozen fullval preparation
directory 86 MiB, and the previous complete single-episode validation 250 MiB.
Downloading more complete runs would consume additional local storage; these
server jobs themselves do not continuously grow local rollout directories.

## Verified preflight, 2026-10-13

A read-only check used the existing SSH control connection for
`hengyil6@klone.hyak.uw.edu`. No files were uploaded, packages installed, assets
downloaded or jobs submitted during this check.

| Item | Observed state |
|---|---|
| Login host | `klone-login03` |
| Running/queued jobs for the user | None returned by `squeue` |
| Project directories | `/gscratch/stf/hengyil6/{HumanCLAW,envs,data,outputs}` exist and are empty |
| Access permissions | User-private directories (`drwx--S---`, owned by `hengyil6`, group `stf`) |
| Default Python | `/usr/bin/python3`, version 3.6.8; below the project's Python 3.10 requirement |
| Other default runtime commands | `/usr/local/bin/uv`; no `python` or `conda` on the default PATH |
| Home storage | 10 GB quota |
| STF shared storage | `hyakstorage` reported 60,414 / 61,440 GB used and 53,160,692 / 60,000,000 files; this is a shared allocation, not a personal reservation |
| GPU account associations | `gpu-l40-stf`, `gpu-l40s-stf`, both with `normal` QoS |
| Corresponding partitions | `gpu-l40`, `gpu-l40s`, both up |
| Checkpoint association | `ckpt-stf`, with `ckpt`, `ckpt-gpu`, `ckpt-scav` QoS available; exact job policy must be checked before using it |

These are a dated readiness snapshot. A visible partition does not guarantee
immediate allocation, and no GPU application or driver compatibility was tested.
STF storage is nearly full; recheck `hyakstorage` before staging large assets.

## Remaining prerequisites

The table above records the state before deployment. A real episode requires
all of the following, including successful native-runtime and GPU checks:

1. A checkout containing this pipeline under `/gscratch/stf/hengyil6/HumanCLAW`.
2. A Python 3.10+ environment under `/gscratch/stf/hengyil6/envs/`, with the
   project's rollout dependencies and the pinned, patched Habitat-Sim build.
   Follow the [installation instructions](../README.md#install) and
   [Habitat-Sim patch guide](../patches/habitat-sim/README.md). Choose the PyTorch
   CUDA build after checking the driver within an allocated GPU job; the
   release's A100/CUDA 12.4 validation is not a Klone L40 validation.
3. Authorized HSSD-Hab inputs and the authorized HumanCLAW HSSD supplement,
   prepared under `/gscratch/stf/hengyil6/data/humanclaw-hssd-val41/`.
4. Motion checkpoints under the checkout's `weights/paper_fullval_v1/`, matching
   `resources/weights/paper_fullval_v1.json`. The run verifies checksums.
5. An explicit, working model configuration and a reachable model endpoint or
   queue worker. The model/deployment is not selected by this template. If using
   an external API, supply credentials through the configured environment variable,
   never as a command-line argument or in the tracked JSON file.

On 2026-10-13 the user authorized code upload and server environment preparation,
replacing the earlier instruction to defer uploads. The current working-tree
code, including the experiment pipeline, is now deployed at the project path.
The Python 3.11 environment is `/gscratch/stf/hengyil6/envs/humanclaw`; its native
dependency installation is a separate Slurm job. Use `tools/klone_setup.sbatch`
for that installation and source `tools/klone_env.sh` for its runtime modules.
Gated dataset access is still handled by the user's Hugging Face account.
Credentials are excluded from the code upload; remote credential provisioning
requires separate user authorization.

Public motion weights are installed under
`/gscratch/stf/hengyil6/data/weights/paper_fullval_v1/`, with `base` and `skills`
linked into the project. The public asset helper
`tools/klone_prepare_public_assets.py` verifies the archive and all nine weights.
It also fetches the 10,545 public HSSD files needed by the release (about 3.58 GB),
then checks the pinned per-file hashes. The manifest calls its source v0.2.5,
but the official v0.2.5 tag disagrees with 104 required file sizes; the helper uses
official revision `4369cb9876214c7fbebcf552eb532380e4d287e4`, whose metadata matches
the release requirements. It does not substitute mismatched assets or bypass
hash checks. The 79.8 MiB gated HumanCLAW supplement was downloaded using the
user's authorized local HF token, transferred as a data archive, then unpacked
and verified on Klone: all 1,693 assets passed. Its extracted directory is
`/gscratch/stf/hengyil6/data/datasets/supplements/humanclaw-hssd-val41-supplement-v1-fd3422b302fc`.

The anonymous public download encountered Hugging Face rate limits. Local
authenticated staging is supported with `--root /absolute/staging-directory
--repo /absolute/source-checkout --use-hf-token`; `--workers` controls bounded
concurrency. The helper uses exact filenames and verifies the pinned hashes.
The completed local staging used `HF_HUB_DISABLE_XET=1` for HTTP transfers.
`--use-hf-token` reads only `HF_TOKEN` from the current environment or the
specified checkout's `.env`; downloads never save the token. Transfer only the
dataset directory, excluding `.cache`, and let the server's `prepare-hssd`
check all hashes again. Respect the Hub's retry delays rather than repeatedly
restarting a rate-limited transfer.

The user initially deferred the Azure key upload, then authorized it on
2026-10-14 for the first online episode described above. Source-code transfers
still exclude `.env`; credential provisioning is a separate operation.

Do not change `HOME`. During future preparation, direct package/model caches to
the scratch storage paths used in the template. The existing `prepare-hssd`
archive extraction code uses `~/.cache/humanclaw-bench/assets` directly and does
not honor `XDG_CACHE_HOME`; use an already extracted, authorized supplement
directory on scratch via `--supplement /absolute/path/to/extracted-supplement`
to avoid that home-cache extraction path. Keep all required scene/mesh inputs
for later replay, including the targets of scene-data symlinks.

After the complete public dataset and extracted supplement are present, submit
`tools/klone_prepare_scenes.sbatch`. It assembles all 41 scenes, verifies their
required files, checks bundled assets and motion weights, and creates the
project's scene-data link. It preserves an existing prepared output rather than
overwriting it. Both this job and `tools/klone_setup.sbatch` use CPU allocations.
The scene job uses `prepare-hssd --workers 16` to avoid serial small-file I/O on
the shared filesystem. This parallelizes independent checks, copies and links;
all hashes are still verified and the completed output is published atomically.
The CLI default remains one worker. Tests compare the serial and parallel file
contents and links, reject corrupted meshes, and check cleanup after copy errors.
The scene job reruns the project suite after preparing the dataset.

After both jobs succeed, `tools/klone_runtime_check.sbatch` performs a short GPU
validation: load the eight motion skills and generate one motion chunk, check
the Half-Physics controller, record a 25-frame stationary scene test, then run
physics and saved-pose render replay. It makes zero VLM calls and writes a
`runtime-smoke-JOBID-readiness.json` only when all checks pass. Its synthetic
planner decisions and diagnostic metrics must not be counted as benchmark
results or actual API token usage. GPU allocation and driver compatibility are
not established by successful CPU compilation alone.

## GPU selection and waiting policy for self-tests

For future environment checks, inspect available resources across the user's
authorized GPU accounts and partitions, including L40, L40S and the shared
checkpoint GPU pool. Use another compatible GPU through Slurm when it can start
sooner; self-tests do not require the benchmark's intended GPU model. Record
the actual device and driver in the validation result. The RTX 2080 Ti used
above is one verified option.

If no suitable GPU is available, leave one self-test job queued and report its
job ID, pending reason and log paths. Finish other independent preparation and
return control to the user instead of remaining in a long polling loop. The
queued job will run when Slurm allocates resources. This is the user's standing
preference for self-tests; formal benchmark comparisons should still use the
chosen hardware configuration and record it with their latency measurements.

## Single-episode submission after setup

Run the following only after setup is complete and job submission is intended.
Use the actual prepared Python and model-config paths; the example names do not
imply those files exist. Environment variables already used by the adapter for
credentials may be inherited by Slurm; do not print or place their values in the
submission command. The script creates private cache/output files with `umask 077`.

```bash
cd /gscratch/stf/hengyil6/HumanCLAW
export HC_PYTHON=/gscratch/stf/hengyil6/envs/humanclaw/bin/python
export HC_MODEL_CONFIG=/gscratch/stf/hengyil6/data/configs/model.json
export HC_HARNESS=humanclaw_psv
export HC_SEED=0
sbatch tools/klone_experiment.sbatch
```

The verified default account/partition is `gpu-l40-stf` / `gpu-l40`, requesting
one L40, eight CPU cores, 32 GB host memory and one hour. This is an initial smoke
allocation, not a measured resource requirement. For the verified L40S account:

```bash
sbatch --account=gpu-l40s-stf --partition=gpu-l40s --gres=gpu:l40s:1 \
  tools/klone_experiment.sbatch
```

Slurm creates logs under the existing `/gscratch/stf/hengyil6/outputs/` directory.
The script writes a unique run directory containing the harness name and job ID,
refuses to reuse an existing output directory, and disables automatic requeue.
If a job is interrupted, retain its partial logs and submit a new run directory.
This template does not claim resume support.

Optional environment overrides are `HC_ROOT`, `HC_REPO`, `HC_SCENE_CONFIG`,
`HC_OUTPUT`, `HC_HARNESS`, `HC_SEED`, `HC_SAVE_VIDEO` and `HC_VALIDATE_REPLAY`.
The last two accept 0 or 1 and default to 0; full replay validation requires
both to be 1. Paths must be absolute. If changing the
root, also override Slurm's `--output` and `--error` paths at submission because
`#SBATCH` directives do not expand shell variables. Keep `HC_HARNESS` explicit
when switching between `humanclaw_psv` and `bare_api`; a run with the existing
planner/verifier is not the bare-API condition.

An endpoint at `127.0.0.1` is local to the allocated compute node, not the login
host or laptop. The template assumes an independently provisioned, reachable
VLM service. It allocates one GPU for evaluation and leaves `CUDA_VISIBLE_DEVICES`
as assigned by Slurm; model serving requires its own resource plan.

## Readiness and verification boundaries

The batch script checks Python version, CUDA availability, imports and asset
checksums inside the allocated GPU job before starting the episode. A successful
import alone does not prove the Habitat-Sim patch was applied correctly; the
first real episode remains the integration check. No rollout, GPU probe or
rendering workload should run on the login node.

After a run, inspect its recorded configuration, trace completeness, final status,
token accounting and benchmark metrics before treating it as an experiment
result. Missing endpoint usage must remain unknown or explicitly estimated,
not a zero-cost call. Keep an interrupted run separate from a completed
benchmark failure.

Trace inspection and metric aggregation can be performed without a GPU. Habitat
re-rendering and action re-execution require the prepared scene inputs, compatible
environment and an allocated GPU. Re-rendering the saved trajectory is a visual
inspection, not evidence that rerunning the model or physics will reproduce the
same result. See the [experiment pipeline guide](EXPERIMENTS.md) for the
implemented replay commands and their current guarantees.
