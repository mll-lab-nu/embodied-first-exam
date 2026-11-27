# Operations

How to set up a host to build and run the tasks: base images, files-only images, building task images, rootless
podman, and the usage gateway. The rules of a run are in [protocol/running.md](protocol/running.md).

## Base images

Every base image is a tag of one of two packages:

- `ghcr.io/mll-lab-nu/efe:<name>-<version>` (public);
- `ghcr.io/mll-lab-nu/efe-private:<name>-<version>` for an image with `images/<name>/BUILD_ONLY` (organization
  members only).

The version is `images/<name>/VERSION`. Every image has its own.

- `scripts/images.sh build` builds them all.
- `scripts/images.sh push` pushes all but the `BUILD_ONLY` ones. It needs `docker login ghcr.io` with a token that has
  `write:packages`. `RCB_PUSH_PRIVATE=1` also pushes the `BUILD_ONLY` ones to `efe-private`.

A new image is a new tag of `efe`, which is public, so nothing needs an admin to change a package's visibility. (A new
package would start private, and the API cannot change that.)

**Where an image is built from.** The context is the repository root, unless:

- `images/<name>/.build-context-self` builds with the image directory as context (`images/mujoco/` copies its asset
  tree `rcb_mj/`; run `prepare_assets.sh` first);
- `images/<name>/BUILD_CONTEXT` names a context directory a script prepares. The image is skipped while it is
  missing.

A subdirectory `images/<name>/<sub>/` with its own `Dockerfile` and `VERSION` is a second image,
`<package>:<name>-<sub>-<version>`, built after `<name>` with itself as context (e.g. `images/ikea-mujoco/sim/`).

**Private images.** An image with `images/<name>/BUILD_ONLY` may not be redistributed: Isaac Sim's licence, assets
without a licence for a public copy, or data behind a token. The marker file says which, and how to build it. It is
never public. Every host can build it, and maintainers may keep a private package for organization members.

- A task on such an image starts its Dockerfile with the image's recipe (the stage between
  `# >>> images/<name>/Dockerfile` and `# <<< images/<name>/Dockerfile`) and names the private image as
  `build.cache_from`. The README's "Before you run" says so.
- A runner without access to the private package gets an authorization warning from BuildKit and builds the recipe
  from public sources.
- Every recipe pins its inputs: base images by digest, system packages from a dated snapshot, repositories by commit,
  files by sha256. It pins every Python package it installs at the tested image's version (a lock or `==` list in
  `images/<name>/` or in the recipe). Most recipes also compare the installed package lists with the tested image's,
  and stop when they differ.
- A build from source therefore gives the private image's package versions, or it fails. It never runs a task on
  other versions. A failure there (a release withdrawn from an index, a mirror serving other files) is a fault of the
  recipe: report it with the step's output.

## Files-only images

Files that many task directories would each carry a copy of live once, in a small pinned image built from their one
source directory in this repository. `images/<name>/FILES.json` describes it: the pinned image reference, the source
directory, and the sha256 of every file. A task's Dockerfile takes the files with `COPY --from=<tag>@sha256:<digest>`,
so the task's container gets the same file at the same path. A sidecar's own Dockerfile (`environment/sim/`) does the
same, under `/srv`.

`standard-files` carries what every standard and realtime task shares: the shared layer (`rcb_limited.py`,
`rcb_client.py`, `rcb1.py`, `run.sh`), the operations layer, the sidecar service `rcb_service.py`, the realtime layer,
`live_video.py`, the agent-end layer and the MCP server. Tasks carry no copies of these files
([embodied_first_exam/standard/README.md](../embodied_first_exam/standard/README.md)).

A files-only image is no docker build. `scripts/files_image.py build <name>` writes it byte for byte from the
repository: one uncompressed layer, sorted, with fixed owners, the checkout modes and the content-derived mtimes of
`scripts/stamp_mtimes.py`. So any checkout of the same sources builds the same digest as the pinned image, and a user
can build a private files-only image instead of pulling it.

```bash
python3 scripts/files_image.py check [name ...]       # the sources still hash to FILES.json (no docker)
python3 scripts/files_image.py digest [name ...]      # the digest a build gives, against the pinned one (no docker)
python3 scripts/files_image.py build <name>           # build <tag>@<digest> and docker load it
python3 scripts/files_image.py push <name> <user>     # push those same bytes (the token on stdin)
python3 scripts/files_image.py pin <name> <digest>    # after the push: check the pushed image, then pin it
python3 scripts/files_image.py fetch [name ...]       # sources kept in a Hugging Face dataset ("hf" in FILES.json)
```

- `docker push` would recompress the layer and change the digest. Push with `files_image.py push`.
  `scripts/images.sh push` skips files-only images.
- A change to a source file needs a new image version (`VERSION`, build, push, pin) before the tasks take it.
  `ci_checks/check-tooling-identity.sh` fails until then.
- Docker's containerd image store (the default of Docker Engine 29 and Docker Desktop) resolves a digest reference to
  a locally built image, so a task builds without the registry. The classic store (overlay2) resolves a digest only
  for a pulled image.

## Building task images: stamp first

Docker's BuildKit keeps one synced copy of a build context per context directory name and client. Harbor's contexts
are always `environment/` and `tests/`. BuildKit re-sends a file only when its path, size, mode or mtime changed. A
task built from a tree whose files share mtimes (a git checkout, `git archive`, tar, `cp -r`, a sed loop) can
therefore get another task's equal-size file in its image, silently, with `--no-cache` too. Rootless podman builds
are not affected.

**Never build a task image from a tree without stamping it.** `scripts/stamp_mtimes.py` gives every file a mtime
derived from its content, so different files never share one. Content, modes and `DIGEST` are unchanged; git ignores
mtimes.

- `scripts/run_agent_batch.sh`, `/validate` and `scripts/task_seed.py materialize` build from stamped copies.
- `harbor run` with this repository's set flags (`-d embodied-first-exam`, `--core`, `--all`, a mode flag,
  `--benchmark`) stamps the task directories it runs, in place.
- For a bare `harbor run -p` or `harbor trial regrade`:

```bash
c=$(python3 scripts/stamp_mtimes.py stage tasks/<benchmark>/<task> "$(mktemp -d)") && harbor run -p "$c" -a oracle ...   # a stamped copy
python3 scripts/stamp_mtimes.py tasks           # or stamp the checkout in place (again after every pull: --check tells)
```

## Rootless podman

Harbor runs the tasks on podman with `-e podman`, through podman's Docker-compatible API and the docker-compose
plugin. This is tested with the oracle on cgroup v1 and v2 nodes (e.g. a Slurm cluster), without root, `/etc/subuid`
entries or a user systemd session. Run everything inside an allocation on the compute node. Put `HOME`,
`XDG_RUNTIME_DIR`, `XDG_CONFIG_HOME` and `TMPDIR` on node-local scratch: podman's storage does not work on most network
file systems.

1. **podman.** Use the cluster's, or a static build (github.com/mgoltzsche/podman-static; 5.8.x on cgroup v1, which
   6.x refuses). Put the docker-compose v2 binary in `~/.docker/cli-plugins/docker-compose`.
2. **`~/.config/containers/containers.conf`**, for a static build unpacked into `$P`:
   ```toml
   [engine]
   helper_binaries_dir = ["$P/usr/local/lib/podman"]
   conmon_path = ["$P/usr/local/lib/podman/conmon"]
   cgroup_manager = "cgroupfs"        # no user systemd session
   events_logger = "file"
   [engine.runtimes]
   crun = ["$P/usr/local/bin/crun"]
   [network]
   firewall_driver = "none"           # only on a node without iptables
   ```
   Add `policy.json` (the build's `etc/containers/policy.json`). Without `/etc/subuid` entries, add `storage.conf`
   with `[storage.options.overlay] ignore_chown_errors = "true"`.
3. **Short names.** Harbor's egress sidecar is built `FROM` a short image name, which podman's enforcing short-name
   mode refuses without a terminal. This repository's `harbor run` pulls it (and the allowlist probe's alpine) by its
   full `docker.io/` name first, so `registries.conf` needs no change.
4. **DNS.** Without a user systemd session, netavark cannot start aardvark-dns through `systemd-run`. A `systemd-run`
   early on `PATH` that drops its options and execs the command works.
5. **Start the API and run:**
   ```bash
   podman system service --time=0 &
   export DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
   harbor run -e podman -d embodied-first-exam@all -p tasks/<benchmark>/<task> -a oracle -y -o $PWD/jobs
   ```
6. **GPU tasks.** podman ignores compose's `driver: nvidia` device request, and the task's processes then find no
   driver (`Found no NVIDIA driver`, `libnvidia-ml.so.1: cannot open shared object file`). Generate a CDI spec for
   the allocation's GPUs (`nvidia-ctk cdi generate --output=<dir>/nvidia.yaml`, and `cdi_spec_dirs = ["<dir>"]` under
   `[engine]`). `harbor run -e podman` with this repository's set flags then runs each GPU task from a stamped copy
   whose compose files ask for the CDI device `nvidia.com/gpu=all` instead, and removes the copies after the job.
   `EFE_PODMAN_GPUS` names another device, e.g. `nvidia.com/gpu=0` on a node with several GPUs for RoboARC, whose
   renderer needs exactly one. For a bare `harbor run -p`, make that copy yourself:
   ```bash
   c=$(python3 scripts/stamp_mtimes.py stage tasks/<benchmark>/<task> "$(mktemp -d)")
   find "$c" -name docker-compose.yaml -exec sed -i -e 's/- driver: nvidia/- driver: cdi/' \
     -e 's/^\( *\)count: 1$/\1device_ids: ["nvidia.com\/gpu=all"]/' {} +
   python3 scripts/stamp_mtimes.py "$c"
   harbor run -e podman -p "$c" -a oracle -y -o $PWD/jobs
   ```
7. **Tasks that build a private image's recipe** (AM-Bench, AutoBio, BEHAVIOR-1K, HumanCLAW, iSpatialGym, LabUtopia,
   ManiGuard, RoboDojo, RoboLab, VLABench, YAMLab; [Base images](#base-images)). Docker's BuildKit takes the image's
   layers from `build.cache_from`. podman ignores `cache_from` and would build the whole recipe on every host (20-90
   min, up to 150 GB). So `harbor run -e podman` with this repository's set flags asks podman for the image first
   (`podman image inspect`, else `podman pull`, once per image and job). The private images need `podman login
   ghcr.io` with a token that can read the organization's packages. When podman has the image, the task runs from a
   stamped copy whose `environment/Dockerfile`, `environment/sim/Dockerfile` and `tests/Dockerfile` say
   `FROM <the image> AS <the stage>` instead of the recipe. When the pull fails it says so, and the task builds the
   recipe from source. `EFE_PODMAN_BUILD_FROM_SOURCE=1` always builds the recipe. For a bare `harbor run -p`, make the
   same copy by hand: `podman pull` the image, stage a copy as in step 6, replace the block with that `FROM` line and
   stamp the copy again.
8. **No cgroup per container.** Where podman cannot give each container a cgroup of its own (cgroup v1, or a cgroup v2
   node whose cgroup is not delegated to your user, e.g. a Slurm job step), podman applies none of the caps. With
   `RCB_LIMITS_ENFORCE=1` the monitor's backstop does ([protocol/resources.md](protocol/resources.md#who-enforces-a-cap)).
   podman also cannot stop the `rcb_monitor` sidecar, which shares the host's PID namespace (podman stops such a
   container by signalling its cgroup's processes). The monitor then ends itself once its record is sealed.
9. **The `cpu` controller.** On cgroup v2 the containers' CPU caps need the `cpu` controller delegated to your user.
   When `/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/cgroup.controllers` lacks `cpu` (some
   distributions delegate only `memory pids` by default), every container fails to start with
   ``crun: controller `cpu` is not available``. An administrator enables it (systemd
   `Delegate=cpu cpuset io memory pids` for `user@.service`); a user cannot.

## The usage gateway

Off by default: the agent calls its API directly, as Harbor runs it. Official runs use it
([protocol/running.md](protocol/running.md#official-runs)).

With `GATEWAY=1`, `scripts/run_agent_batch.sh` starts `scripts/usage_gateway/gateway.py` on the docker bridge
(`GATEWAY_BIND`, 172.17.0.1). It points the agent's base URL at it (`--ae ANTHROPIC_BASE_URL` / `OPENAI_BASE_URL`, and
a copy of `AGENT_CONFIG` with its provider `base_url`s rewritten and `supports_websockets = false`). The agent is still
Harbor's own `codex` or `claude-code` with its own credentials. The gateway forwards model requests unchanged to the
same API and never stores a key.

### Model-API calls only

The gateway forwards only the requests listed per provider in `scripts/usage_gateway/api_paths.json`: responses,
messages, token counting, the model list. Chat completions go only to a self-hosted upstream. Official runs do not
use them, and at the providers that API serves models that search the web without any tool declaration. Anything else
gets a 403 without being forwarded: connectors and apps, plugins, files, conversations, web search.

A model request is forwarded as it is or not at all.

- Its body must be one JSON object the gateway can read: one Content-Length of at most 256 MiB, at most one
  Content-Encoding.
- Every tool it declares (top-level `tools`, and the `tools` of an `input` item, where Codex declares its own) must be
  one the agent runs itself: `client_tool_types` in the same file (no type, `function`, `custom`, `namespace`). That
  is everything Codex and Claude Code declared in the recorded runs.
- Any other tool type is the provider's (web search or fetch, image generation, remote MCP, file search, a hosted
  shell or code interpreter), and the request is refused.
- Also refused: a provider-side search, MCP or stored-prompt field (`provider_side_fields`), an OpenRouter `:online`
  model, and an image, document or file given as an http(s) address for the provider to fetch (`data:` URLs are
  fine).

What the gateway does not judge: which model a request names. A provider's model that searches by itself on a
forwarded path would pass, so give a run a key that can call only its model.

Codex compresses its ChatGPT-login requests with zstd. The gateway reads them with the `zstandard` module or the
`zstd` program. A host with neither forwards such a body unchecked, marks it `body_unchecked` and says so in the
gateway's start-up log.

**Refusals** are in `<trial>/gateway/usage.jsonl` (`refused`: `path_not_allowed`, `host_not_allowed`, `server_tool` or
`body_unreadable`, with method and path, never a body). They are counted in `totals.json` (`refused_paths`,
`refused_hosts`, `refused_server_tools`, `refused_bodies`), and the batch summary shows `REFUSED n` in the gateway
column. A refusal marks the trial as one to look at, and that is all. It does not void a trial, and nothing tells the
agent that trying is forbidden. What a harness sends by itself at start-up without being a model call
(`harness_probes` in `api_paths.json`: Claude Code's `HEAD /api/hello`, in every trial) is refused but neither
recorded nor counted.

To add a provider, a path or a client tool type, edit `api_paths.json` (default deny; a host without a provider there
gets nothing forwarded). A new harness version that declares another tool type is refused until it is listed.

**One resend.** ChatGPT's `POST /backend-api/codex/responses` answers a small share of well-formed requests with an
HTTP 400, mostly zstd bodies just over a multiple of 128 KiB, and Codex ends its turn on a 400. The gateway sends such
a request once more without the compression: the same JSON bytes the agent compressed, the same headers without
`Content-Encoding` and with their `Content-Length`. A body that was not zstd, or that the gateway cannot decode, goes
again with the same bytes and headers. The agent gets the second answer as it is, or the first 400 if the resend gets
none. Both attempts are in `usage.jsonl` (`"retried": true, "attempt": 1`, then `"attempt": 2`, both with
`"retry_mode": "uncompressed"` or `"identical"`), and `totals.json` counts `retried_400`. `--no-retry-400` turns it
off.

### The only way out

The model APIs' hosts also serve everything the gateway refuses. So with the gateway on, each job runs from its own
copy of the task (`$JOBS/.tasks/<job>/`, removed afterwards) whose egress allowlist is the gateway's address and the
package registries (`scripts/set_agent_egress.py only <GATEWAY_BIND>,<PACKAGE_HOSTS>`). Harbor's
`--allow-agent-host` can add a host, not remove one. `GATEWAY_EGRESS=task` keeps the task's own allowlist, with the
hosts reachable directly; it is not for official runs.

Harbor's allowlist names addresses, not ports. Every TCP service that listens on the gateway's address (the docker
bridge) of the runner host is reachable from a trial. Bind the host's other services to 127.0.0.1, or firewall the
bridge.

**Codex with a ChatGPT login** is the one exception. Before its first model call, Codex 0.160.1 asks
`chatgpt.com/backend-api/wham/accounts/check` for the account's workspace. It asks at `chatgpt_base_url`, not at the
model's base URL, and accepts only an HTTPS origin there, which the plain-HTTP gateway is not. Through the gateway the
lookup succeeds and Codex then stops with "workspace backend must use an HTTPS origin"; without it, "workspace
routing discovery failed". Such a run keeps `chatgpt.com` (that one host) on the copy's allowlist beside the gateway.
That backend's other paths then stay reachable directly, and the account's connectors are off by the harness's
configuration alone. Closing this needs a gateway that speaks HTTPS with a certificate the harness trusts. Until then,
prefer API keys, which have no connectors, and keep the evaluation accounts' connectors disconnected. A Codex API
key, a Claude subscription token and a self-hosted endpoint work with the gateway and the package registries as the
only addresses.

### Health and failures

- The runner waits `GATEWAY_START_WAIT` seconds (10) for the gateway to come up. Raise it on busy shared nodes.
- Before each job it checks that the gateway still runs and answers `/_gateway/health`. A dead gateway is restarted
  on its port (the agents' base URLs keep working), and the lane stops if that fails. A job during which the gateway
  died gets `<job>/gateway_down.json`.
- A model call that fails on the way is recorded as `upstream_failure` in `usage.jsonl`: the upstream unreachable (the
  gateway answers 502), the provider's stream broken off, or a provider 5xx. It is counted in `totals.json`
  (`upstream_failures`; `failures_in_a_row` up to the latest call).
- A trial that ends on such failures, or whose job has `gateway_down.json`, is an infrastructure failure.
  `write_task_results.py` publishes it as "not a result", never the agent's 0. Three or more failed calls in a row at
  its end stop the lane like an account failure (`scripts/account_failure_check.py`).

### What it records

Per trial, next to Harbor's `agent/` and `verifier/` (outside the agent's mounts):

```
<trial>/gateway/usage.jsonl     one line per request: time, duration, host, path, status, model, input / cached / output tokens
<trial>/gateway/totals.json     running totals, rewritten after every request
<trial>/gateway/raw.jsonl.xz    every request and response body (GATEWAY_RAW=1, the default with the gateway on; headers without credentials)
```

- **Token counts.** Input counts what the model read (Anthropic: input + cache read + cache creation; OpenAI:
  `input_tokens`, cached included). Output includes reasoning. This is the same convention as Harbor's
  `n_input_tokens` / `n_output_tokens`, which the batch summary shows side by side. They agree exactly when the agent
  ends by itself. When it is stopped at its time limit, the gateway is higher by the requests the provider completed
  (and billed) after Harbor's cut-off, or that the agent was killed before logging.
- **Token budget.** With the gateway on, a trial that reaches `TOKEN_BUDGET_IN` input or `TOKEN_BUDGET_OUT` output
  tokens (default 10B / 10B; 0 = no limit) gets every further model request refused (HTTP 400, "token budget
  exceeded"), so the agent stops. `totals.json` records `over_token_budget = 1` and, from the first refused request,
  `budget_stop` (`limit` input|output, `first_refused_at` / `last_refused_at`, the input / cached / output counts at
  the stop, `refused`). A runner records such a trial as `TokenBudgetExceeded`, not as the harness's own exception
  (which reads as a network or API error: Codex `NetworkConnectionError` / `NonZeroAgentExitCodeError`, Claude Code
  `UnknownApiError`). Codex ends its turn on the first refusal, without retrying.
- **The raw log** stores each conversation item once, and a request as references to the items it resends, like
  Codex's and Claude Code's own session files. It is lossless: `scripts/usage_gateway/rawlog.py cat <trial>/gateway`
  prints every request and response in full. The gateway appends to `raw.jsonl.gz` while the trial runs. After each
  job the runner compacts it to `raw.jsonl.xz`.
- **Switches.** `GATEWAY=1` records usage and, by default, raw bodies. `GATEWAY_RAW=0` records usage only. Raw bodies
  are private: they hold the whole conversation.
- **Matching.** A request is matched to its trial by its source address, looked up among the containers of the
  runner's own running trials only (the runner hands the gateway its job names, `--own-jobs`), never every container
  on the engine. Requests no trial can be matched to go to `<jobs>/.gateway/unattributed.jsonl`.
- **Known limits.** No WebSocket: Codex's built-in provider falls back to HTTPS after a few refused attempts. On a
  runner host without the `zstandard` module or the `zstd` program, Codex's zstd-compressed request bodies are stored
  as base64, and so not deduplicated. OpenAI reasoning arrives encrypted.
