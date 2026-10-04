"""Versioned, allowlisted difficulty exports and resumable HF dataset commits.

No simulator or model imports. The Hub SDK runs in owned, bounded subprocesses;
offline export needs only the Python standard library.
"""
from __future__ import annotations

from contextlib import contextmanager
import csv
import datetime as dt
import fcntl
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import re
import shlex
import shutil
import tempfile
import threading
import time
from urllib.parse import quote
import uuid

from difficulty_hf_auth import HFError, error_from_exception
from collect_batch_results import ARTIFACT_CONTRACT_VERSION, OPTIONAL_DIAGNOSTICS, result_artifacts
from helper_assignment import planned_trials

SCHEMA = 1
COMPLETE = {"solved", "unsolved", "not_evaluable", "invalid_submission"}
STATUSES = COMPLETE | {"pending", "blocked_preflight", "interrupted", "infra_failed", "invalid_job", "identity_mismatch"}
ROW_FIELDS = ("task_id", "difficulty", "sample_id", "scene_seed", "mode", "trial", "attempt", "status", "success",
              "evaluable_for_task_success", "tokens_in", "tokens_out", "cost_usd_api_price", "exception")


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def encoded(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n").encode()


def digest(value):
    # Same canonical identity used by sample_difficulty_instances.digest.
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".hf-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def json_file(path):
    try:
        with Path(path).open() as stream:
            return json.load(stream)
    except (OSError, ValueError):
        raise HFError("invalid_results", "cannot read required result JSON") from None


def safe_file(root, path, *, required=True):
    root, path = Path(root).absolute(), Path(path).absolute()
    try:
        rel = path.relative_to(root)
    except ValueError:
        raise HFError("invalid_results", "result path escapes run directory") from None
    if ".." in rel.parts or root.is_symlink():
        raise HFError("invalid_results", "unsafe result directory")
    cursor = root
    for part in rel.parts:
        cursor /= part
        if cursor.is_symlink():
            raise HFError("invalid_results", "symlinks are not exported")
    if not path.exists() and not required:
        return None
    if not path.is_file():
        raise HFError("invalid_results", "required result file missing or not regular")
    return path


def component(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,100}", value):
        raise HFError("invalid_results", "invalid result identity component")
    return value


def file_identity(path, guard=lambda: None):
    size = path.stat().st_size
    sha, git = hashlib.sha256(), hashlib.sha1(b"blob " + str(size).encode() + b"\0")
    read = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            guard()
            read += len(block)
            sha.update(block)
            git.update(block)
    if read != size:
        raise HFError("invalid_results", "file changed while exporting")
    return dict(size=size, sha256=sha.hexdigest(), git_blob_sha1=git.hexdigest())


class Scrubber:
    def __init__(self, secrets=()):
        self.secrets = tuple(str(s) for s in secrets if s)

    def text(self, value):
        value = str(value)
        for secret in self.secrets:
            value = value.replace(secret, "[REDACTED]")
        value = re.sub(r"(?:hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{8,})", "[REDACTED]", value)
        value = re.sub(r"https?://[^\s\"<>]*\?[^\s\"<>]*", "[REDACTED_URL]", value)
        return "".join(c if c.isprintable() else " " for c in value)

    def data(self, value):
        if isinstance(value, dict):
            return {self.text(k): self.data(v) for k, v in value.items() if not re.search(
                r"(?i)(?:password|secret|credential|authorization|api[_-]?key|access[_-]?token|refresh[_-]?token|^token$)", k)
                    and k not in ("job", "harbor_trial", "snapshot", "workspace", "owner")}
        if isinstance(value, list):
            return [self.data(v) for v in value]
        if isinstance(value, str):
            value = self.text(value)
            if value.startswith(("/", "~/")) or re.match(r"^[A-Za-z]:[\\/]", value):
                return "[LOCAL_PATH]/" + value.replace("\\", "/").rsplit("/", 1)[-1]
            return value
        if isinstance(value, float) and not math.isfinite(value):
            raise HFError("invalid_results", "non-finite metric in results")
        return value


class UploadLog:
    def __init__(self, run, secrets=(), heartbeat_s=15):
        self.root = Path(run) / "hf_upload"
        self.root.mkdir(parents=True, exist_ok=True)
        self.run_id, self.invocation = Path(run).name, uuid.uuid4().hex
        self.scrub = Scrubber(secrets)
        self.started = time.monotonic()
        self.heartbeat_s = heartbeat_s
        self.stage, self.lock, self.disk_warning = "starting", threading.Lock(), False

    def emit(self, event, message, level="INFO", **fields):
        with self.lock:
            record = dict(timestamp=utc(), level=level, event=event, run_id=self.run_id,
                          invocation_id=self.invocation, stage=self.stage, batch=None, file_count=None,
                          logical_bytes=None, elapsed_s=round(time.monotonic() - self.started, 2),
                          retry_count=None, error_code=None)
            record.update(fields)
            record = self.scrub.data(record)
            message = self.scrub.text(message)
            line = f"[{record['timestamp']}] [hf-upload] {level} {message}"
            print(line, flush=True)
            try:
                with (self.root / "upload.log").open("a") as stream:
                    stream.write(line + "\n")
                with (self.root / "events.jsonl").open("ab") as stream:
                    stream.write(encoded(dict(record, message=message)))
            except OSError:
                if not self.disk_warning:
                    print("[hf-upload] WARN Cannot write upload logs; terminal output remains available", flush=True)
                    self.disk_warning = True

    @contextmanager
    def activity(self, stage, message):
        self.stage = stage
        self.emit(stage, message)
        stop = threading.Event()
        def heartbeat():
            while not stop.wait(self.heartbeat_s):
                self.emit("heartbeat", f"{message} | elapsed={time.monotonic()-self.started:.0f}s | transfer_rate=unavailable | ETA=unavailable")
        thread = threading.Thread(target=heartbeat, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stop.set()
            thread.join(timeout=2)


def load_results(run):
    run = Path(run)
    manifest = json_file(safe_file(run, run / "manifest.lock.json"))
    if manifest.get("schema_version") not in (1, 2) or manifest.get("manifest_sha256") != digest(
            {k: v for k, v in manifest.items() if k != "manifest_sha256"}):
        raise HFError("invalid_results", "manifest identity check failed")
    source = json_file(safe_file(run, run / "source_identity.json"))
    if source.get("sha256") != manifest.get("source_sha256") or digest(source.get("files", {})) != source.get("sha256"):
        raise HFError("invalid_results", "source identity check failed")
    samples = {}
    for sample in manifest["instances"]:
        task, difficulty, sid = (component(sample[k]) for k in ("task_id", "difficulty", "sample_id"))
        if difficulty not in ("easy", "medium", "hard") or type(sample["scene_seed"]) is not int or not 0 <= sample["scene_seed"] < 2**32:
            raise HFError("invalid_results", "invalid sample identity")
        if sample.get("sample_sha256") != digest({k: v for k, v in sample.items() if k != "sample_sha256"}):
            raise HFError("invalid_results", "sample identity check failed")
        if (task, difficulty, sid) in samples:
            raise HFError("invalid_results", "duplicate sample")
        samples[task, difficulty, sid] = sample
    seen, rows, seeds = set(), [], set()
    for sample in samples.values():
        key = sample["task_id"], sample["difficulty"], sample["scene_seed"]
        if key in seeds:
            raise HFError("invalid_results", "duplicate scene seed in a task/difficulty")
        seeds.add(key)
    try:
        with safe_file(run, run / "trials.jsonl").open() as stream:
            for line in stream:
                row = json.loads(line)
                key = tuple(row[k] for k in ("task_id", "difficulty", "sample_id"))
                sample = samples.get(key)
                if (not sample or row["scene_seed"] != sample["scene_seed"] or row["mode"] not in ("limited", "unlimited")
                        or row["status"] not in STATUSES or row["trial"] != 1 or type(row["attempt"]) is not int
                        or not 1 <= row["attempt"] <= 999 or row["evaluable_for_task_success"] != sample["evaluable_for_task_success"]):
                    raise HFError("invalid_results", "trial does not match manifest")
                full = (*key, row["mode"], row["attempt"])
                if full in seen:
                    raise HFError("invalid_results", "duplicate trial attempt")
                seen.add(full)
                rows.append(row)
    except (ValueError, KeyError, TypeError) as error:
        if isinstance(error, HFError):
            raise
        raise HFError("invalid_results", "invalid trials.jsonl; collect results before uploading") from None
    planned = {(sample['task_id'], sample['difficulty'], sample['sample_id'], mode)
               for sample, mode in planned_trials(manifest)}
    if not planned or {key[:-1] for key in seen} != planned or manifest["trial_count"] != len(planned):
        raise HFError("invalid_results", "collected results must include every planned trial")
    return manifest, source, samples, sorted(rows, key=lambda r: tuple(r[k] for k in ("task_id", "difficulty", "sample_id", "mode", "attempt")))


def publication_identity(run, args, manifest):
    path = run / "hf_publication.lock.json"
    expected = dict(schema_version=SCHEMA, repo_id=args.hf_repo_id, run_id=args.run_id,
                    manifest_sha256=manifest["manifest_sha256"], artifacts=args.hf_artifacts)
    if path.exists():
        got = json_file(safe_file(run, path))
        if any(got.get(k) != v for k, v in expected.items()) or (args.hf_exp_date and got["exp_date"] != args.hf_exp_date):
            raise HFError("identity_conflict", "HF publication identity changed; use its original options")
        if str(uuid.UUID(got["run_uuid"])) != got["run_uuid"]:
            raise HFError("identity_conflict")
        if dt.date.fromisoformat(got["exp_date"]).isoformat() != got["exp_date"]:
            raise HFError("identity_conflict")
        if got["prefix"] != f"{got['exp_date']}/{component(args.run_id)}--{got['run_uuid']}":
            raise HFError("identity_conflict")
        return got
    created = json_file(safe_file(run, run / "run-created.json")) if (run / "run-created.json").exists() else {}
    date = args.hf_exp_date or created.get("created_at", utc())[:10]
    if dt.date.fromisoformat(date).isoformat() != date:
        raise HFError("identity_conflict")
    identity = dict(expected, run_uuid=str(uuid.uuid4()), exp_date=date,
                    exp_date_source="explicit" if args.hf_exp_date else ("run_created" if created else "first_export"))
    identity["prefix"] = f"{date}/{component(args.run_id)}--{identity['run_uuid']}"
    atomic_json(path, identity)
    return identity


def export_snapshot(run, args, log, guard=lambda: None):
    """Caller holds the evaluation run lock. Never imports the frozen collector."""
    run = Path(run)
    manifest, source, samples, rows = load_results(run)
    identity = publication_identity(run, args, manifest)
    state_path = safe_file(run, run / "hf_upload/state.json", required=False)
    state = json_file(state_path) if state_path else {}
    if args.phase == "upload" and not args.hf_dry_run and state.get("upload_status") in ("uploading", "failed") and state.get("snapshot_sha256"):
        previous_sha = state["snapshot_sha256"]
        if not re.fullmatch(r"[a-f0-9]{64}", previous_sha):
            raise HFError("invalid_results", "invalid saved upload snapshot")
        previous = run / "hf_upload/staging" / previous_sha
        descriptor = json_file(safe_file(run, previous / "_run/upload_manifest.json"))
        if (descriptor.get("identity") != identity or descriptor.get("snapshot_sha256") != previous_sha
                or digest({k: v for k, v in descriptor.items() if k != "snapshot_sha256"}) != previous_sha):
            raise HFError("identity_conflict", "saved upload snapshot identity changed")
        with log.activity("resume", "Resuming frozen upload snapshot; later result changes can be published in a subsequent invocation"):
            for rel, expected in descriptor["files"].items():
                if file_identity(safe_file(run, previous / rel), guard) != expected:
                    raise HFError("invalid_results", "saved upload snapshot changed")
        return previous, descriptor
    base = run / "hf_upload/staging"
    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".preparing-", dir=base))
    inventory, terminal, exported, latest = {}, {}, [], {}
    scrub = log.scrub
    execution_path = safe_file(run, run / "execution.lock.json", required=False)
    execution = json_file(execution_path) if execution_path else {}
    execution = {k: execution[k] for k in ("auth", "provider", "agent", "model", "agent_args") if k in execution}
    def record(rel):
        inventory[rel] = file_identity(staging / rel, guard)
    def put(rel, value):
        guard()
        atomic_json(staging / rel, scrub.data(value))
        record(rel)
    try:
        with log.activity("export", "Preparing upload snapshot"):
            for row in rows:
                guard()
                sample = samples[row["task_id"], row["difficulty"], row["sample_id"]]
                rel = f"{row['task_id']}/{row['difficulty']}/seed_{row['scene_seed']}/{row['mode']}/trial_01/attempt_{row['attempt']:03d}"
                origin = run / "results" / row["task_id"] / row["difficulty"] / row["sample_id"] / row["mode"] / "trial_01" / f"attempt_{row['attempt']:03d}"
                item = {k: row.get(k) for k in ROW_FIELDS}
                item.update(schema_version=SCHEMA, artifact_contract_version=ARTIFACT_CONTRACT_VERSION,
                            run_uuid=identity["run_uuid"], run_id=args.run_id,
                            exp_date=identity["exp_date"], sample_sha256=sample["sample_sha256"],
                            source_sha256=manifest["source_sha256"], manifest_sha256=manifest["manifest_sha256"],
                            artifacts={}, missing_files=[])
                item.update(execution)
                item["agent_wall_clock_s"] = manifest["settings"].get("agent_wall_clock_s")
                for name in result_artifacts(row["mode"], media=args.hf_artifacts == "standard"):
                    src = safe_file(run, origin / name, required=False)
                    dst = staging / rel / name
                    if src is None:
                        if name not in OPTIONAL_DIAGNOSTICS:
                            item["missing_files"].append(name)
                        continue
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    source_sha = None
                    if name.endswith((".json", ".jsonl")):
                        source_sha = file_identity(src, guard)["sha256"]
                    if name.endswith(".json"):
                        value = json_file(src)
                        if name == "replay.recording_manifest.json":
                            # Point at the exported bytes, retaining original file
                            # identity in result.json rather than forging raw evidence.
                            for ref in [value.get("frame_map"), *(value.get("videos") or {}).values()]:
                                if isinstance(ref, dict) and ref.get("path") in item["artifacts"]:
                                    ref["sha256"] = item["artifacts"][ref["path"]]["sha256"]
                        put(f"{rel}/{name}", value)
                    elif name.endswith(".jsonl"):
                        with src.open() as inp, dst.open("wb") as out:
                            for line in inp:
                                guard()
                                out.write(encoded(scrub.data(json.loads(line))))
                        record(f"{rel}/{name}")
                    else:
                        with src.open("rb") as inp, dst.open("wb") as out:
                            while block := inp.read(1024 * 1024):
                                guard()
                                out.write(block)
                        record(f"{rel}/{name}")
                    item["artifacts"][name] = dict(inventory[f"{rel}/{name}"], path=f"{identity['prefix']}/{rel}/{name}")
                    if source_sha is not None:
                        item["artifacts"][name]["source_sha256"] = source_sha
                put(f"{rel}/result.json", item)
                if row["status"] in COMPLETE:
                    terminal[rel] = {p: h["sha256"] for p, h in inventory.items() if p.startswith(rel + "/")}
                exported.append(scrub.data(item))
                latest[row["task_id"], row["difficulty"], row["sample_id"], row["mode"]] = row
            put("_run/manifest.export.json", {k: manifest[k] for k in (
                "schema_version", "manifest_sha256", "source_sha256", "settings", "instances", "instance_count", "trial_count")})
            put("_run/source_identity.export.json", {k: source[k] for k in ("git_head", "files", "sha256", "release_id") if k in source})
            put("_run/execution.export.json", execution)
            provenance = {}
            for name, keys in (("cuda-profile.json", ("cuda_flavor",)), ("controller.json", ("release_id", "image_id"))):
                path = safe_file(run, run / name, required=False)
                if path:
                    data = json_file(path)
                    provenance[name] = {k: data[k] for k in keys if k in data}
            summary = dict(planned_trials=manifest["trial_count"], observed_attempts=len(rows),
                           completed_trials=sum(r["status"] in COMPLETE for r in latest.values()),
                           evaluable_trials=sum(r["status"] in {"solved", "unsolved"} for r in latest.values()),
                           solved_trials=sum(r["status"] == "solved" for r in latest.values()))
            summary["evaluation_complete"] = summary["completed_trials"] == summary["planned_trials"]
            summary["incomplete_trials"] = summary["planned_trials"] - summary["completed_trials"]
            put("_run/metadata.json", dict(identity, **summary, provenance=provenance,
                artifact_contract_version=ARTIFACT_CONTRACT_VERSION,
                input_sha256={name: file_identity(run / name, guard)["sha256"] for name in ("manifest.lock.json", "source_identity.json", "trials.jsonl")},
                exporter_sha256=file_identity(Path(__file__), guard)["sha256"]))
            (staging / "_run/trials.jsonl").write_bytes(b"".join(encoded(row) for row in exported))
            record("_run/trials.jsonl")
            with (staging / "_run/summary.csv").open("w", newline="") as stream:
                fields = ("run_uuid", *ROW_FIELDS)
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(exported)
            record("_run/summary.csv")
            lines = ["# Difficulty evaluation", "", f"Evaluable completed trials (latest attempt each): {summary['solved_trials']}/{summary['evaluable_trials']} solved.", "",
                     "Not-evaluable, invalid submissions and infrastructure failures are excluded from this denominator.", "",
                     "| task | difficulty | sample | mode | attempt | status |", "| --- | --- | --- | --- | --- | --- |"]
            lines += ["| " + " | ".join(str(row[k]) for k in ("task_id", "difficulty", "sample_id", "mode", "attempt", "status")) + " |" for row in exported]
            (staging / "_run/summary.md").write_text("\n".join(lines) + "\n")
            record("_run/summary.md")
            descriptor = dict(schema_version=SCHEMA, identity=identity, files=inventory, terminal=terminal, **summary)
            snapshot = digest(descriptor)
            descriptor["snapshot_sha256"] = snapshot
            atomic_json(staging / "_run/upload_manifest.json", descriptor)
            target = base / snapshot
            if target.exists():
                # Revalidate below; never silently trust a cached staging directory.
                shutil.rmtree(staging)
            else:
                staging.rename(target)
            for rel, expected in inventory.items():
                if file_identity(safe_file(run, target / rel), guard) != expected:
                    raise HFError("invalid_results", "staging snapshot changed")
            if json_file(target / "_run/upload_manifest.json") != descriptor:
                raise HFError("invalid_results", "staging manifest changed")
            log.emit("snapshot_ready", f"Snapshot ready | files={len(inventory)} | logical_size={sum(x['size'] for x in inventory.values()) / 2**20:.1f} MiB | missing_evidence={sum(len(r['missing_files']) for r in exported)}",
                     file_count=len(inventory), logical_bytes=sum(x["size"] for x in inventory.values()))
            return target, descriptor
    except BaseException:
        # Failed staging is retained for diagnosis; never remove experiment evidence.
        raise


@contextmanager
def publication_lock(run):
    path = Path(run) / "hf_upload"
    path.mkdir(parents=True, exist_ok=True)
    with (path / ".lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise HFError("identity_conflict", "another uploader owns this run") from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _sdk_worker(pipe, token, repo, cache, action, params):
    """One owned process per blocking SDK operation; errors cross as safe codes only."""
    try:
        os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        os.environ["HF_HUB_VERBOSITY"] = "error"
        os.environ["HF_HOME"] = str(Path(cache) / "sdk")
        os.environ.pop("HF_TOKEN_PATH", None)
        os.environ.pop("HF_TOKEN", None)
        # SDK and native transfer libraries must not bypass the public logger.
        with open(os.devnull, "w") as null:
            os.dup2(null.fileno(), 1)
            os.dup2(null.fileno(), 2)
        from huggingface_hub import HfApi, CommitOperationAdd
        api = HfApi(endpoint="https://huggingface.co", token=token)
        if action == "auth":
            api.auth_check(repo, repo_type="dataset", write=True)
            result = None
        elif action == "head":
            # An existing, newly created dataset may have no commits/main yet.
            result = api.repo_info(repo, repo_type="dataset").sha
        elif action == "read":
            infos = api.get_paths_info(repo, params["path"], revision=params["revision"], repo_type="dataset") if params["revision"] else []
            if not infos:
                result = None
            else:
                if infos[0].size > 64 * 1024 * 1024:
                    raise HFError("identity_conflict", "remote publication metadata exceeds limit")
                path = api.hf_hub_download(repo, params["path"], repo_type="dataset", revision=params["revision"], cache_dir=cache)
                result = json_file(path)
        elif action == "info":
            entries = api.get_paths_info(repo, params["paths"], revision=params["revision"], repo_type="dataset") if params["revision"] else []
            result = {entry.path: dict(size=entry.size, sha256=entry.lfs.sha256 if entry.lfs else None,
                                      git_blob_sha1=entry.blob_id) for entry in entries if hasattr(entry, "blob_id")}
        elif action == "commit":
            result = api.create_commit(repo, repo_type="dataset", revision="main", parent_commit=params["parent"],
                operations=[CommitOperationAdd(path_in_repo=rel, path_or_fileobj=Path(path)) for rel, path in params["files"]],
                commit_message=params["message"], num_threads=2).oid
        else:
            raise HFError("configuration")
        pipe.send((True, result))
    except BaseException as error:
        if isinstance(error, ImportError):
            error = HFError("missing_sdk", "install huggingface-hub==1.33.0 in the uploader Python environment")
        public = error if isinstance(error, HFError) else error_from_exception(error)
        pipe.send((False, (public.code, str(public), public.retryable)))
    finally:
        pipe.close()


class Hub:
    def __init__(self, token, repo, run, guard=lambda: None, timeout_s=1800):
        self.token, self.repo, self.cache = token, repo, str(Path(run) / "hf_upload/cache")
        self.guard, self.timeout_s = guard, timeout_s

    def call(self, action, **params):
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe(duplex=False)
        process = ctx.Process(target=_sdk_worker, args=(child, self.token, self.repo, self.cache, action, params))
        process.start()
        child.close()
        started = time.monotonic()
        try:
            while not parent.poll(0.25):
                self.guard()
                if not process.is_alive():
                    raise HFError("hub_worker_failed", retryable=True)
                if time.monotonic() - started > (self.timeout_s if action == "commit" else 120):
                    raise HFError("network_timeout", retryable=True)
            ok, value = parent.recv()
            if not ok:
                raise HFError(value[0], value[1], retryable=value[2])
            return value
        except EOFError:
            raise HFError("hub_worker_failed", retryable=True) from None
        finally:
            if process.is_alive():
                process.join(timeout=1)
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
            if process.is_alive():
                process.kill()
                process.join()
            parent.close()


class Publisher:
    def __init__(self, run, args, token, log, guard=lambda: None, hub=None, sleep=time.sleep):
        self.run, self.args, self.log, self.guard = Path(run), args, log, guard
        self.hub = hub or Hub(token, args.hf_repo_id, run, guard)
        self.sleep = sleep
        self.commits = []

    def retry(self, operation):
        for attempt in range(4):
            self.guard()
            try:
                return operation()
            except HFError as error:
                if not error.retryable or attempt == 3:
                    raise
                delay = min(5 * 2**attempt, 20)
                self.log.emit("retry", f"{error.code} | retry={attempt+1}/3 | retry_in={delay}s", "WARN",
                              retry_count=attempt+1, error_code=error.code)
                with self.log.activity("retry", "Checking remote commit before retry" if error.code == "commit_conflict" else "Waiting to retry; remote state will be checked"):
                    self.sleep(delay)

    def preflight(self, source):
        with self.log.activity("access", f"Checking Hugging Face access | repo={self.args.hf_repo_id} | credentials={source}"):
            self.retry(lambda: self.hub.call("auth"))
        self.log.emit("access_ok", "Hugging Face dataset write access verified")

    def state(self, status, **values):
        path = self.run / "hf_upload/state.json"
        previous = json_file(path) if path.is_file() else {}
        previous.update(upload_status=status, repo_id=self.args.hf_repo_id, invocation_id=self.log.invocation,
                        commits=list(dict.fromkeys([*previous.get("commits", []), *self.commits])), **values)
        atomic_json(path, previous)

    def publish(self, staging, descriptor):
        identity = descriptor["identity"]
        prefix, snapshot = identity["prefix"], descriptor["snapshot_sha256"]
        if digest({k: v for k, v in descriptor.items() if k != "snapshot_sha256"}) != snapshot:
            raise HFError("invalid_results", "upload snapshot digest mismatch")
        for rel, expected in descriptor["files"].items():
            if file_identity(safe_file(staging, staging / rel), self.guard) != expected:
                raise HFError("invalid_results", "staging snapshot changed before upload")
        claim_path, marker_path = prefix + "/_run/claim.json", prefix + "/_run/publication.json"
        manifest_path = prefix + "/_run/upload_manifest.json"
        claim = dict(identity=identity, snapshot_sha256=snapshot)
        self.state("uploading", snapshot_sha256=snapshot, prefix=prefix)
        claim_local = staging / "_run/claim.json"
        atomic_json(claim_local, claim)
        def read(path, head):
            return self.hub.call("read", path=path, revision=head)
        def inspect():
            head = self.hub.call("head")
            old_claim, marker = read(claim_path, head), read(marker_path, head)
            if old_claim and old_claim.get("identity") != identity:
                raise HFError("identity_conflict", "remote prefix belongs to another publication")
            return head, old_claim, marker
        def commit(files, head, title):
            oid = self.hub.call("commit", parent=head, files=files, message=title)
            self.commits.append(oid)
            self.state("uploading", snapshot_sha256=snapshot, prefix=prefix)
            return oid
        def reserve():
            head, old, marker = inspect()
            if old == claim:
                return
            if old and (not marker or marker.get("snapshot_sha256") != old.get("snapshot_sha256")):
                raise HFError("identity_conflict", "another snapshot is unfinished; finish that snapshot before exporting changed results")
            if old:
                previous = read(manifest_path, head)
                if not previous or previous.get("snapshot_sha256") != marker.get("snapshot_sha256"):
                    raise HFError("identity_conflict", "remote completed manifest is inconsistent")
                for rel, files in previous.get("terminal", {}).items():
                    if descriptor["terminal"].get(rel) != files:
                        raise HFError("identity_conflict", "completed attempt changed; preserve its original evidence")
            else:
                # A UUID collision or unknown pre-existing run must never be adopted.
                if read(manifest_path, head) or marker:
                    raise HFError("identity_conflict", "unowned remote publication prefix")
            commit([(claim_path, str(claim_local))], head, f"Reserve difficulty results {identity['run_id']}")
        self.log.emit("upload", f"Uploading results to Hugging Face | repo={self.args.hf_repo_id} | prefix={prefix} | mode={identity['artifacts']}")
        with self.log.activity("reserve", "Checking remote publication identity"):
            self.retry(reserve)
        inventory = dict(descriptor["files"])
        # Summary/manifest/marker are committed together only after evidence verification.
        payload = [p for p in inventory if not p.startswith("_run/")]
        metadata = [p for p in inventory if p.startswith("_run/")]
        def verified(files, head):
            remote = self.hub.call("info", paths=[prefix + "/" + p for p in files], revision=head)
            missing = []
            for rel in files:
                local, got = inventory[rel], remote.get(prefix + "/" + rel)
                matches = (got and got["size"] == local["size"] and
                           (got["sha256"] == local["sha256"] if got["sha256"] else got["git_blob_sha1"] == local["git_blob_sha1"]))
                if not matches:
                    missing.append(rel)
            return missing
        head, _, marker = self.retry(inspect)
        # Verify every file even if a completion receipt was found locally/remotely.
        pending = []
        with self.log.activity("compare", "Comparing remote files"):
            for offset in range(0, len(payload), 100):
                subset = payload[offset:offset+100]
                pending.extend(self.retry(lambda subset=subset: verified(subset, head)))
        self.log.emit("remote_check", f"Remote check complete | reusable={len(payload)-len(pending)} files | pending={len(pending)} files")
        batches = [pending[i:i+50] for i in range(0, len(pending), 50)]
        for index, batch in enumerate(batches, 1):
            def send_batch():
                current, current_claim, _ = inspect()
                if current_claim != claim:
                    raise HFError("identity_conflict", "remote upload ownership changed")
                missing = verified(batch, current)
                if missing:
                    self.log.emit("commit_batch", f"Committing batch {index}/{len(batches)} | files={len(missing)}", batch=index)
                    commit([(prefix + "/" + rel, str(staging / rel)) for rel in missing], current,
                           f"Difficulty results {identity['run_id']} batch {index}/{len(batches)}")
            with self.log.activity("transfer", f"Uploading batch {index}/{len(batches)}"):
                self.retry(send_batch)
        publication = dict(schema_version=SCHEMA, identity=identity, snapshot_sha256=snapshot,
                           upload_status="complete", evaluation_complete=descriptor["evaluation_complete"],
                           file_count=len(inventory), logical_bytes=sum(v["size"] for v in inventory.values()))
        marker_local = staging / "_run/publication.json"
        atomic_json(marker_local, publication)
        def finalize():
            current, current_claim, current_marker = inspect()
            if current_claim != claim:
                raise HFError("identity_conflict", "remote upload ownership changed")
            for offset in range(0, len(payload), 100):
                if verified(payload[offset:offset+100], current):
                    raise HFError("remote_incomplete", "remote evidence verification failed")
            if current_marker == publication and read(manifest_path, current) == descriptor and not verified(metadata, current):
                self.log.emit("already_uploaded", "Already uploaded; remote snapshot verified")
                return current
            files = [(prefix + "/" + rel, str(staging / rel)) for rel in metadata]
            files += [(manifest_path, str(staging / "_run/upload_manifest.json")), (marker_path, str(marker_local))]
            return commit(files, current, f"Publish difficulty results {identity['run_id']} {snapshot[:12]}")
        with self.log.activity("publish", "Publishing completion marker"):
            oid = self.retry(finalize)
        url = f"https://huggingface.co/datasets/{self.args.hf_repo_id}/tree/{oid}/{quote(prefix, safe='/')}"
        self.state("complete", snapshot_sha256=snapshot, prefix=prefix, commit=oid, url=url)
        self.log.emit("complete", f"Upload complete | files={len(inventory)} | logical_size={publication['logical_bytes']/2**20:.1f} MiB | commit={oid}",
                      file_count=len(inventory), logical_bytes=publication["logical_bytes"])
        self.log.emit("results", f"Results: {url}")
        self.log.emit("evaluation_status", f"evaluation_complete={str(descriptor['evaluation_complete']).lower()} | upload_status=complete | incomplete_trials={descriptor['incomplete_trials']}")
        self.log.emit("receipt", f"Receipt: {self.run / 'hf_upload/state.json'}")
        return oid


def recovery_command(args, work):
    """Use host launcher context, never the container's private token path."""
    context = {}
    launch = Path("/run/topogym-launch")
    if os.environ.get("TOPOGYM_CONTAINER") == "1":
        context["backend"] = "docker"
        for key, filename in (("launcher", "hf-host-launcher"), ("token_file", "hf-host-token-file"), ("token_env", "hf-host-token-env")):
            path = launch / filename
            if path.is_file():
                context[key] = path.read_text()
        # An env credential becomes a file inside the controller; retain host source.
        if "token_env" in context:
            context["token_file"] = None
    argv = ["bash", context.get("launcher", "bash_scripts/run_difficulty_trials.sh"), "--backend",
            context.get("backend", "local"), "--work-dir", str(work), "--phase", "upload", "--run-id", args.run_id,
            "--results_to_hf", "--hf-repo-id", args.hf_repo_id, "--hf-artifacts", args.hf_artifacts]
    token_file = context.get("token_file", str(args.hf_token_file) if args.hf_token_file else None)
    token_env = context.get("token_env", args.hf_token_env)
    if token_file:
        argv += ["--hf-token-file", token_file]
    elif token_env:
        argv += ["--hf-token-env", token_env]
    return shlex.join(argv)
