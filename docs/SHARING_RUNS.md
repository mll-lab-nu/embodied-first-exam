# Running our tasks for us and sending back the logs

For a helper who runs a batch of our tasks on their own GPU host and cannot reach our review site or our machines.
You run the batch with our runner, check it for secrets, pack the job directories **without changing their layout or
names**, and upload one archive with its checksum and a manifest. Our importer rebuilds every page from those files, so
the layout is the contract.

This is the only helper manual, for every benchmark (TopoGym included). Jianwen's
`docs/rcb/helper_delivery_engineering_plan_zh.md` on `dev/jianwen` is the engineering plan for TopoGym's sampled
difficulty trials (a maintainer-frozen assignment, a bundle with a file inventory, a fail-closed scan, an importer); as
its parts are implemented, their commands go into this file (§3b), not into a second manual.
This file exists word for word in two places: `docs/SHARING_RUNS.md` on `dev/qineng` and `docs/rcb/SHARING_RUNS.md`
on `dev/jianwen` (where TopoGym helpers start). Change both together.

Names: the project is Embodied Agent Interface v2 (EAI). A few code identifiers still carry the old name RCB
(`RCB_BEHAVIOR_DATA`, TopoGym's image `rcb-topogym` and its `docs/rcb/`); use them exactly as written here.

## 1. What we send you first (the assignment)

| Item | Example | Why it matters |
|---|---|---|
| Repository, branch and commit | `JamesKrW/robot_coding_bench`, `dev/qineng`, `64a998287` (TopoGym: `dev/jianwen` at the release commit) | The task directories and the runner come from this exact commit |
| Task list and modes | `robowits-stack-cubes-i00`, … (task bases; both modes unless we say otherwise) | One Harbor job per task and mode |
| **Batch name** | `robowits-lunaxh-alice-1004` | Every job name starts with it; our site finds your run by it. Use it verbatim |
| Agent settings | `AGENT=codex MODEL=openai/gpt-6-luna EFFORT=xhigh` | The run id is derived from them |
| Release (TopoGym only) | `merged-v16`, image `rcb-topogym:0.2.14-dev-cu128` | The runner only runs the active release's frozen packages |
| Upload target | our private Hugging Face dataset `eai-v2-internal/helper-uploads` and a write token for it, or a shared-folder link | Where the archive goes |

Do not invent your own batch name, change budgets, seeds, models or efforts, edit task directories or modify the runner.
If something forces a change, ask us first. Only we decide reruns (§3).

## 2. Prerequisites
- Linux host with an NVIDIA GPU (driver >= 580), Docker with the NVIDIA runtime, enough disk for the images (tens of GB).
- `harbor` on `PATH`, `git`, `python3`.
- The benchmark images named in the task directories (build or pull them as the repository's `images/<sim>/` explains).
- BEHAVIOR-1K tasks only: the licensed dataset on the host (`RCB_BEHAVIOR_DATA`). Never copy it into an image or an upload.
- TopoGym only: the runner takes its tasks from the active release (`scripts/topogym_versions.py tasks-root`) and runs
  only packages bound to an image on your host, so build that release's candidate on your host first (README "Run" on
  `dev/jianwen`: `scripts/topogym_merge_candidate.py`, its `build_image.sh`, `scripts/topogym_candidate_pipeline.py
  --phase all`; hours of GPU time). blanket_flatten's packaged cloth states restore only on the GPU profile they were
  prepared on (RTX PRO 6000 class, sm_120); on another GPU, leave blanket out and tell us.
- Your own model credentials (ChatGPT login, API key, …). They stay on your host and never go into the upload. How
  Harbor reads them: `docs/RUNNING.md` on `main` (TopoGym: `docs/rcb/RUNNING.md`).

## 3. Run the batch
### 3a. Task batches (every benchmark)
```bash
git clone git@github.com:JamesKrW/robot_coding_bench.git && cd robot_coding_bench && git checkout <commit>
export JOBS=$PWD/jobs/agents                 # keep the default layout: jobs/agents/<batch>-<mode>-<task>/
B=<batch name we sent>
AGENT=codex MODEL=openai/gpt-6-luna EFFORT=xhigh ENV_FILE=$HOME/eai.env \
  nohup scripts/run_agent_batch.sh "$B" <task-base> [<task-base> ...] > "run_$B.out" 2>&1 &
```
- The variables above are those of `main`'s runner (and TopoGym's). The runner in your checkout lists its own in its
  header (`sed -n 2,45p scripts/run_agent_batch.sh`). If they differ, set our agent settings in its terms.
- One runner is one lane (one trial at a time). Start the same command again to add a lane; every job is claimed by
  exactly one runner.
- Progress: `$JOBS/$B.log`; the summary table: `$JOBS/$B.summary.md`. TopoGym's runner also freezes the batch's package
  selection in `$JOBS/$B.release.json`; keep it.
- Never delete or move a job directory, including failed or interrupted ones. They are part of the record.
- A trial that crashed for an infrastructure reason (host OOM, GPU lost, network outage): leave it in place, note it in
  the manifest, and rerun it only if we ask, with the list of jobs we send. Reruns go into the batch `<batch>-rerun`.

When the batch is done, every job has a verdict. This lists the ones that do not:
```bash
for d in "$JOBS"/"$B"-*/; do ls "$d"*/verifier/reward.json >/dev/null 2>&1 || echo "no verdict: $d"; done
```

### 3b. TopoGym difficulty trials (sampled instances)
Not for helpers yet. They run through `bash_scripts/run_difficulty_trials.sh`, whose helper mode (an `assignment.json` we
freeze and send, reruns only by our retry plan, `helper export` / `upload` / `import`) is still being implemented on
`dev/jianwen` (the engineering plan above). Its commands will appear here once it has passed a delivery rehearsal.

## 4. Check for secrets (mandatory)
The runner already scans and redacts each job. Scan once more over everything you will send:
```bash
python3 scripts/scan_secrets.py "$JOBS" --env-file "$HOME/eai.env" --codex-auth "$HOME/.codex/auth.json" --redact
python3 scripts/scan_secrets.py "$JOBS" --env-file "$HOME/eai.env" --codex-auth "$HOME/.codex/auth.json"   # must find none
```
- "Must find none": TopoGym's scanner (`dev/jianwen`) exits 0 and prints `"clean": true`; it exits 1 when a secret is
  left and 2 when the scan was incomplete (an unreadable file, no credential loaded): both block the upload. The scanner
  on `dev/qineng` ends with `...: 0 contain one`.
- Add `--var NAME` for any other credential variable you used. With a ChatGPT login, the agent logs may show your account
  id or email. We redact those before anything becomes public. Tell us if you mind them being in the private upload.

## 5. Pack it, keeping the layout
```bash
H=<your name, lowercase>; ID=$(date -u +%Y%m%dT%H%MZ)      # one bundle id per delivery: a later one never overwrites
cd "$(dirname "$JOBS")"                      # the directory that contains agents/
find agents/"$B"-* agents/"$B".* $(ls -d agents_mirror/"$B"-* 2>/dev/null) -type f -print0 | sort -z \
  | xargs -0 sha256sum > "INVENTORY_${B}__${H}__${ID}.sha256"
tar -czf "${B}__${H}__${ID}.tar.gz" agents/"$B"-* agents/"$B".* $(ls -d agents_mirror/"$B"-* 2>/dev/null) \
    "INVENTORY_${B}__${H}__${ID}.sha256"
sha256sum "${B}__${H}__${ID}.tar.gz" > "${B}__${H}__${ID}.tar.gz.sha256"
```
- `agents/<batch>-*` also picks up `<batch>-rerun-*` jobs; `agents/<batch>.*` the log, the summary and TopoGym's
  `.release.json`. Keep them.
- `agents_mirror/` is the runner's append-only copy of every agent record (root-owned). If `find` or `tar` cannot read it,
  rerun those two commands with `sudo`, or leave it out and say so in the manifest.
- Do not rename, flatten, re-encode or prune anything inside the jobs. A partial delivery (the batch is not finished) is
  fine: say so in the manifest; the next delivery gets a new bundle id.

## 6. Write `MANIFEST.md` next to the archive
```text
batch:            <batch>   (+ <batch>-rerun if any)
bundle:           <bundle id>, partial: yes | no
helper:           <name, contact>
repo:             <repository> <branch> <commit>       (TopoGym: + release name and `scripts/topogym_versions.py identity`)
host:             <CPU>, <RAM GB>, <GPU model x N>, driver <version>, CUDA <version>
software:         docker <version>, harbor <version>
images:           <image> <RepoDigest or Id>        (one line per image used)
agent:            AGENT=..., MODEL=..., EFFORT=..., credentials: ChatGPT login | API key | ... (no secrets)
lanes / GPUs:     <N runners>, GPUs <ids>
trials:           planned <n>, with a verdict <n>, infrastructure failures <n>, not started <n>
started/finished: <date time, timezone> / <date time, timezone>
unusual events:   crashes, OOM kills, outages, reruns, skipped jobs (job names + what happened)
```
These commands fill most of it:
```bash
git rev-parse HEAD; nvidia-smi --query-gpu=name,driver_version --format=csv; docker --version; harbor --version
docker image inspect --format '{{index .RepoDigests 0}} {{.Id}}' <image>
```

## 7. Upload
Put the archive, its `.sha256` and `MANIFEST.md` in one folder `upload_<batch>/`, then do one of:
- **Hugging Face:** our private dataset `eai-v2-internal/helper-uploads`, with the token we sent you. The token can
  write to this one repository only, and we revoke it after your delivery. Keep it in a private file, never in a script,
  a repository or your shell history:
  ```bash
  pip install -U huggingface_hub
  install -m 600 /dev/null ~/.eai_hf_token        # then paste the token into this file with an editor
  HF_TOKEN=$(cat ~/.eai_hf_token) hf upload eai-v2-internal/helper-uploads "upload_$B" "helpers/$H/$B" --repo-type dataset
  ```
  The files land in `helpers/<your name>/<batch>/`; a later delivery has a new bundle id and never overwrites one.
- **Shared folder:** upload the three files to the link we sent.

Then message us the batch name, the archive name and its sha256.

Never upload credentials (`~/.codex`, `.env`, tokens), datasets, Docker images, source trees or anything outside this
batch's jobs.

## For us (receiving side)
```bash
hf download eai-v2-internal/helper-uploads --repo-type dataset --include "helpers/<helper>/<batch>/*" \
  --local-dir ~/eai_helper_runs/_downloads            # our own HF login (org members); then, in that batch folder:
sha256sum -c <batch>__<helper>__<id>.tar.gz.sha256
tar -tzf <batch>__<helper>__<id>.tar.gz | grep -Ev '^(agents|agents_mirror)/<batch>|^INVENTORY_' && echo "unexpected paths"
mkdir -p ~/eai_helper_runs/<helper>/jobs && tar -xzf <batch>__<helper>__<id>.tar.gz -C ~/eai_helper_runs/<helper>/jobs
(cd ~/eai_helper_runs/<helper>/jobs && sha256sum -c --quiet INVENTORY_<batch>__<helper>__<id>.sha256)
```
Never run anything from a bundle (agent code, scripts). On the review site:
1. Add `data/runs/hosts.<helper>.local.yml` containing
   `<helper>: {jobs: /home/<user>/eai_helper_runs/<helper>/jobs/agents}` (gitignored).
2. Register the batch in `state/runs/<benchmark>.yml` (`batch` / `rerun_batches`, and the extra modes' `batches`).
3. Run `make runs RUNS="--benchmark <benchmark>"`.

The pages then show the helper's trials like our own (see `docs/contributing/registering-runs.md` there). A later
bundle of the same batch is extracted next to the earlier one; the site counts every attempt.
