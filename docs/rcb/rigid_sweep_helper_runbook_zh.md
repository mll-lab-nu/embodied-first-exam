# Running our tasks for us and sending back the logs

For a helper who runs a batch of our tasks on their own GPU host and cannot reach our review site or our machines. You run the batch with our runner, check it for secrets, pack the job directories without changing their layout or names, and upload one archive. Our importer rebuilds every page from those files, so the layout is the contract.

> Release status: this frozen release is local and has not been pushed to GitHub. The clone command below works on the maintainer's machine. Before remote handoff, we must publish the release and replace that command with its accessible repository URL and commit. Review-site integration is deferred; the final site instructions describe the upstream receiving workflow.

## 1. What we send you first

| Item | Example | Why it matters |
| --- | --- | --- |
| Repository, branch and commit | Local release `topogym-rigid-solxh-jianwen-20261005-online-build01`, `main`, `0005191575a70a6d6a621b7cbdbb4a05dda92086` | The task directories come from this exact commit |
| Task list and modes | The 24 task bases below; privileged and standard; K=3 | One Harbor job per task and mode; three trials per job |
| Batch name | `topogym-rigid-solxh-jianwen-20261005` | Every job name starts with it; our site finds your run by it. Use it verbatim |
| Agent settings | `AGENT=codex MODEL=openai/gpt-6-sol EFFORT=xhigh`; helper-supplied API key | The run id is derived from them |
| Upload target | Private dataset `eai-v2-internal/helper-uploads`, folder `helpers/jianwen/topogym-rigid-solxh-jianwen-20261005/`, write token from us | Where the archive goes |

Do not invent your own batch name, change budgets, edit task directories or modify the runner. If something forces a change, ask us first.

This assignment contains eight rigid/articulated-rigid tasks at easy, medium and hard, using fixed oracle seed 0: 24 instances x 2 modes x 3 repetitions = 144 trials. Each trial has 12 hours, 150M input tokens and 10M output tokens. Token limits are checked after the run for scoring, not enforced as a live API spending cap. K=3 and both modes are already in the assignment.

## 2. What you need

- Linux host with an NVIDIA GPU (driver >= 580), Docker with the NVIDIA runtime, enough disk for the images (tens of GB).
- git, python3/pip and network access. This runner installs its pinned Harbor, Codex and HF tools automatically.
- The benchmark images named in the task directories. This release builds missing images automatically from its frozen materials before running trials.
- BEHAVIOR-1K tasks only: the licensed dataset on the host (RCB_BEHAVIOR_DATA). Never copy it into an image or an upload.
- Your own model credentials (an OpenAI API key for this batch). They stay on your host and never go into the upload. Save `OPENAI_API_KEY` and `OPENAI_BASE_URL=https://api.openai.com/v1` in the private file `$HOME/rcb.env`. Do not put subscription-auth settings or `HF_TOKEN` in that file.
- Save the HF write token we send you in `$HOME/.config/eai/helper-hf.token`. Keep both credential files outside the repository and readable only by you.

## 3. Run the batch

```bash
git clone /home/jianwen/helper-releases/topogym-rigid-solxh-jianwen-20261005-online-build01 /home/jianwen/helper-checkouts/topogym-rigid-solxh-jianwen-20261005-formal && cd /home/jianwen/helper-checkouts/topogym-rigid-solxh-jianwen-20261005-formal && git checkout 0005191575a70a6d6a621b7cbdbb4a05dda92086
REPO=$PWD
export JOBS=$PWD/jobs/agents                 # keep the default layout: jobs/agents/<batch>-<mode>-<task>/
B=topogym-rigid-solxh-jianwen-20261005
AGENT=codex MODEL=openai/gpt-6-sol EFFORT=xhigh ENV_FILE=$HOME/rcb.env \
CODEX_FORCE_AUTH_JSON=0 CODEX_AUTH_JSON_PATH= \
  nohup scripts/run_agent_batch.sh "$B" \
  topogym-interlocked-claws-easy-o00 \
  topogym-interlocked-claws-medium-o00 \
  topogym-interlocked-claws-hard-o00 \
  topogym-lock-picking-easy-o00 \
  topogym-lock-picking-medium-o00 \
  topogym-lock-picking-hard-o00 \
  topogym-hedgehog-in-cage-easy-o00 \
  topogym-hedgehog-in-cage-medium-o00 \
  topogym-hedgehog-in-cage-hard-o00 \
  topogym-fiber-bundling-easy-o00 \
  topogym-fiber-bundling-medium-o00 \
  topogym-fiber-bundling-hard-o00 \
  topogym-horseshoe-ring-easy-o00 \
  topogym-horseshoe-ring-medium-o00 \
  topogym-horseshoe-ring-hard-o00 \
  topogym-cast-coil-easy-o00 \
  topogym-cast-coil-medium-o00 \
  topogym-cast-coil-hard-o00 \
  topogym-cast-keyhole-easy-o00 \
  topogym-cast-keyhole-medium-o00 \
  topogym-cast-keyhole-hard-o00 \
  topogym-buzz-wire-3d-easy-o00 \
  topogym-buzz-wire-3d-medium-o00 \
  topogym-buzz-wire-3d-hard-o00 \
  > "run_$B.out" 2>&1 &
```

- The variables above are those of main's runner. The runner in your checkout lists its own in its header (sed -n 2,45p scripts/run_agent_batch.sh). If they differ, set our agent settings in its terms.
- One runner is one lane (one trial at a time). Start the same command again to add a lane; every job is claimed by exactly one runner. The command defaults to GPU 0; coordinate GPU allocation before adding lanes.
- Progress: $JOBS/$B.log; the summary table: $JOBS/$B.summary.md. During initial setup, see `run_$B.out`. The summary is refreshed after each job, so it may be absent or out of date while that job runs.
- Never delete or move a job directory, including failed or interrupted ones. They are part of the record.
- A trial that crashed for an infrastructure reason (host OOM, GPU lost, network outage): leave it in place, note it in the manifest, and rerun it only if we ask. Reruns go into the batch `topogym-rigid-solxh-jianwen-20261005-rerun`.

When the batch is done, every job has a verdict. This lists the ones that do not:

```bash
for d in "$JOBS"/"$B"-*/; do ls "$d"*/verifier/reward.json >/dev/null 2>&1 || echo "no verdict: $d"; done
```

Wait for the background runner to finish before continuing. The loop checks for at least one verdict per job; for K=3, also check that the summary reports 144 observed trials, evaluation complete and delivery complete. Completion does not mean every task was solved or that it has been uploaded.

## 4. Check for secrets

The runner already scans and redacts each job. Scan once more over everything you will send:

```bash
python3 scripts/scan_secrets.py "$JOBS" --env-file "$HOME/rcb.env" --codex-auth "$HOME/.codex/auth.json" --redact
python3 scripts/scan_secrets.py "$JOBS" --env-file "$HOME/rcb.env" --codex-auth "$HOME/.codex/auth.json"   # must find none
```

Add --var NAME for any other credential variable you used. With a ChatGPT login, the agent logs may show your account id or email. We redact those before anything becomes public. Tell us if you mind them being in the private upload. For this API-key batch, `~/.codex/auth.json` may be absent; the scanner accepts that conventional missing path.

## 5. Pack the jobs without changing their layout

```bash
H=jianwen
cd "$(dirname "$JOBS")"                      # the directory that contains agents/
tar -czf "${B}__${H}.tar.gz" agents/"$B"-* agents/"$B".log agents/"$B".summary.md \
    $(ls -d agents_mirror/"$B"-* 2>/dev/null)
sha256sum "${B}__${H}.tar.gz" > "${B}__${H}.tar.gz.sha256"
```

- `agents/<batch>-*` also picks up `<batch>-rerun-*` jobs. Keep them.
- agents_mirror/ is the runner's append-only copy of every agent record (root-owned). If tar cannot read it, rerun that command with sudo. This assignment requires the mirror for complete acceptance; if it cannot be included, say so in the manifest and report an incomplete delivery.
- Do not rename, flatten, re-encode or prune anything inside the jobs.

## 6. Write MANIFEST.md

```text
batch:            topogym-rigid-solxh-jianwen-20261005 (+ authorized rerun if any)
helper:           jianwen, contact supplied separately
repo:             <repository> <branch> <commit>
host:             <CPU>, <RAM GB>, <GPU model x N>, driver <version>, CUDA <version>
software:         docker <version>, harbor <version>
images:           <image> <RepoDigest or Id>        (one line per image used)
agent:            AGENT=codex, MODEL=openai/gpt-6-sol, EFFORT=xhigh, credentials: API key (no secrets)
lanes / GPUs:     <N runners>, GPUs <ids>
started/finished: <date time, timezone> / <date time, timezone>
unusual events:   crashes, OOM kills, outages, reruns, skipped jobs (job names + what happened)
```

These commands fill most of it:

```bash
git -C "$REPO" rev-parse HEAD
nvidia-smi --query-gpu=name,driver_version --format=csv
docker --version
"$REPO/.venv-agent-batch/bin/harbor" --version
docker image inspect --format '{{.Id}}' topogym-local/rcb-topogym-difficulty:e23ccbcabf43f733084c-cu128
cp "$JOBS/$B-MANIFEST.md" MANIFEST.md
```

The runner supplies the generated MANIFEST copied above, including actual image IDs and build verification. Locally built images may have no RepoDigest. If you write a separate human manifest instead, use the fields above and retain the original records inside `agents/`.

## 7. Send us the archive

Put the archive, its .sha256 and MANIFEST.md in one folder `upload_<batch>/`, then do one of:

- Hugging Face (private dataset, write token from us):

  ```bash
  mkdir -p "upload_$B"
  cp "${B}__${H}.tar.gz" "${B}__${H}.tar.gz.sha256" MANIFEST.md "upload_$B/"
  HF_TOKEN="$(cat "$HOME/.config/eai/helper-hf.token")" \
    "$REPO/.venv-agent-batch/bin/hf" upload eai-v2-internal/helper-uploads "upload_$B" "helpers/$H/$B" --repo-type dataset
  ```

  The runner already installed the pinned HF CLI. Do not run `pip install -U huggingface_hub` inside that environment.

- Shared folder: upload the three files to the link we sent.

Then message us the batch name, the archive name and its sha256.
Never upload credentials (~/.codex, .env, tokens), datasets, Docker images, or anything outside this batch's jobs.

## 8. What we do after receiving it

The commands below are for the receiver, after upload. The tool path is the existing installation on the maintainer's machine; the receiver uses its own HF read token.

```bash
B=topogym-rigid-solxh-jianwen-20261005
H=jianwen
HF_TOKEN="$(cat "$HOME/.config/eai/helper-hf.token")" \
  /home/jianwen/topogym/.venv-agent-batch/bin/hf download \
  eai-v2-internal/helper-uploads --repo-type dataset \
  --include "helpers/$H/$B/*" --local-dir "$HOME/rcb_helper_downloads"
cd "$HOME/rcb_helper_downloads/helpers/$H/$B"
sha256sum -c "${B}__${H}.tar.gz.sha256" &&
mkdir -p "$HOME/rcb_helper_runs/$H/jobs" &&
tar -xzf "${B}__${H}.tar.gz" -C "$HOME/rcb_helper_runs/$H/jobs"
```

Checksum verification and extraction do not replace comparison against our saved original assignment. Full offline acceptance is available through `bash_scripts/import_helper_results.sh` with `--require-complete`; it downloads and validates the batch independently. This is a receiver operation, not an extra helper step.

On the review site (receiver only; integration for this release is not yet connected):

1. Add `data/runs/hosts.jianwen.local.yml` containing
   `jianwen: {jobs: /home/jianwen/rcb_helper_runs/jianwen/jobs/agents}` (gitignored).
2. Register the batch in `state/runs/<benchmark>.yml` (batch / rerun_batches, and the extra modes' batches).
3. Run `make runs RUNS="--benchmark …"` with the benchmark supplied by the site maintainer.

The pages then show the helper's trials like our own (see docs/contributing/registering-runs.md there).

The site repository and benchmark are not available in this checkout; the website steps are deferred.
