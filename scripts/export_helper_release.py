#!/usr/bin/env python3
"""Export a helper release tree: frozen task packages + the image build context they are bound to + the upstream runner.

  .venv-gs121-nyx/bin/python scripts/export_helper_release.py --name merged-v18-rigid --source-commit 8d7d16489 \
      --tasks ~/helper-work/rigid-v18-validation-20261005/candidate/tasks --out ~/helper-releases/<new dir>

A helper clones the result and follows docs/rcb/SHARING_RUNS.md: builds the one image as images/topogym/BUILD_ONLY says,
then runs scripts/run_agent_batch.sh over tasks/. The tree holds
  - the image build context at --source-commit (the commit the packages' runtime binding was built from), without the
    directories prune.py drops from the image (no reference solutions);
  - the upstream runner (unchanged) and the tools it calls, BUILD_ONLY and the helper documents, from this checkout;
  - the packages under tasks/, byte for byte, and a README.
It fails, leaving the tree uncommitted, unless the context reproduces the source hash every package is bound to, all
packages share one runtime and one image, and no host path or token pattern is found. It never pushes."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from secret_scan import scan_tree
from topogym_versions import public_source

ROOT = Path(__file__).resolve().parents[1]
RUNNER_BLOB = "a74bf7cc16e35b3b86ae23595c3e0b63d6bff102"   # upstream e768a13a8 (docs/rcb/README.md, 2026-10-06 rollback)
CONTEXT = (".dockerignore", "images/topogym", "requirements", "assets/robots", "scripts/prepare_nyx_studio.py", "topogym")
OMIT = {"agents", "planning", "data", "deferred", "legacy", "redundants", "rollout_simulation", "__pycache__"}  # prune.py
CHECKOUT = ("scripts/run_agent_batch.sh", "scripts/log_mirror.py", "scripts/mem_guard.py", "scripts/scan_secrets.py",
            "scripts/secret_scan.py", "scripts/write_task_results.py", "scripts/task_names.py", "scripts/install.sh",
            "scripts/account_failure_check.py",
            "images/topogym/BUILD_ONLY", "docs/rcb/SHARING_RUNS.md", "docs/rcb/RUNNING.md")


def git(*args, **kw):
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, **kw).stdout


def export_context(commit, out):
    archive = git("archive", "--format=tar", commit, *CONTEXT)
    subprocess.run(["tar", "-x", "-C", str(out)], input=archive, check=True)
    for path in sorted((out / "topogym").rglob("*"), reverse=True):   # deepest first
        rel = path.relative_to(out / "topogym")
        if set(rel.parts) & OMIT or (path.is_file() and path.suffix == ".md"):
            shutil.rmtree(path) if path.is_dir() else path.unlink()


def check(out):
    """(runtime, image reference, task names) shared by every package; raises on any mismatch."""
    tasks = sorted(p.parent.name for p in (out / "tasks").glob("*/task.toml"))
    locks = sorted((out / "tasks").glob("*/**/runtime_binding.json"))
    if not tasks or not locks:
        raise SystemExit("no task packages or runtime bindings under tasks/")
    bound = {json.dumps([json.loads(p.read_text())[k] for k in ("runtime", "image")], sort_keys=True) for p in locks}
    if len(bound) != 1:
        raise SystemExit(f"packages are bound to {len(bound)} different runtimes/images")
    runtime, image = json.loads(bound.pop())
    if public_source(out) != runtime["source"]:
        raise SystemExit(f"exported topogym/ hashes to {public_source(out)}, packages are bound to {runtime['source']}")
    ref = image["reference"]
    for task in tasks:
        texts = [p.read_text() for p in (out / "tasks" / task).glob("**/*") if p.name in ("Dockerfile", "docker-compose.yaml")]
        if not any(ref in t for t in texts):
            raise SystemExit(f"{task} does not reference {ref}")
    # The image context is fixed by the binding (a few resource files record their provenance path); check the rest.
    home = str(Path.home()).encode()
    files = [*(out / "tasks").rglob("*"), *(out / rel for rel in CHECKOUT)]
    hits = [p for p in files if p.is_file() and home in p.read_bytes()]
    if hits:
        raise SystemExit(f"host path {home.decode()} in {[str(p.relative_to(out)) for p in hits[:5]]}")
    report = scan_tree(out, {}, allow_empty_secrets=True)
    if not report["clean"]:
        raise SystemExit(f"token patterns found: {report['findings'][:5]}")
    return runtime, ref, tasks


def readme(name, commit, runtime, ref, tasks):
    bases = sorted({t.rsplit("-", 1)[0] for t in tasks})
    lines = [f"# TopoGym helper release {name}", "",
             f"{len(tasks)} frozen Harbor task packages ({len(bases)} task bases x privileged/standard) under `tasks/`, "
             f"bound to image `{ref}`.",
             f"Image build context: TopoGym commit `{commit}`; simulator source `{runtime['source']['sha256']}` "
             f"({runtime['source']['files']} files).", "",
             "Follow [docs/rcb/SHARING_RUNS.md](docs/rcb/SHARING_RUNS.md). TopoGym specifics:", "",
             "1. Install Harbor once per host: `scripts/install.sh` (robot_coding_bench's host setup; Harbor pinned to 0.23.0, the "
             "version this release was tested with). It prints the Harbor version; a shell that does not find `harbor` "
             "afterwards: `export PATH=\"$HOME/.local/bin:$PATH\"`.",
             "2. Build the image once and check it: [images/topogym/BUILD_ONLY](images/topogym/BUILD_ONLY).",
             "3. Run `scripts/run_agent_batch.sh` with the batch name and agent settings we send (variables: "
             "`sed -n 2,45p scripts/run_agent_batch.sh`).",
             "4. Several GPUs: start each lane with its own GPU, e.g. `TOPOGYM_GPU_UUID=1 AGENT=... nohup "
             "scripts/run_agent_batch.sh ...`; the task containers use `${TOPOGYM_GPU_UUID:-0}` (an index or a GPU UUID "
             "from `nvidia-smi -L`), so lanes without it all share GPU 0. Docker Compose warnings about unset "
             "`TOPOGYM_BATCH` / `TOPOGYM_BATCH_OWNER` are harmless.", "",
             "Task bases:", "", *[f"- `{b}`" for b in bases], ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--name", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--tasks", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.expanduser().resolve()
    if out.exists():
        raise SystemExit(f"{out} exists; choose a new directory")
    if git("hash-object", "scripts/run_agent_batch.sh", text=True).strip() != RUNNER_BLOB:
        raise SystemExit("scripts/run_agent_batch.sh is not the upstream runner")
    commit = git("rev-parse", "--verify", args.source_commit + "^{commit}", text=True).strip()
    out.mkdir(parents=True)
    export_context(commit, out)
    for rel in CHECKOUT:
        (out / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, out / rel)
    shutil.copytree(args.tasks.expanduser(), out / "tasks", symlinks=True)
    runtime, ref, tasks = check(out)
    (out / "README.md").write_text(readme(args.name, commit, runtime, ref, tasks))
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"],
                ["commit", "-q", "-m", f"TopoGym helper release {args.name} (image context {commit[:9]})"]):
        subprocess.run(["git", "-C", str(out), *cmd], check=True)
    print(f"{out}: {len(tasks)} packages, image {ref}, source {runtime['source']['sha256'][:16]}; "
          f"commit {subprocess.run(['git', '-C', str(out), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()}")


if __name__ == "__main__":
    sys.exit(main())
