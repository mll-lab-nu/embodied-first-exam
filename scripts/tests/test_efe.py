#!/usr/bin/env python3
"""scripts/efe.py prepull (standard library only, no docker, no Harbor needed):

- qualified() gives a Docker Hub short name its registry and leaves a ref that names one alone;
- engine_of() reads -e / --env: docker by default, podman, None for any other environment;
- prepull() asks the engine for each ref, pulls only the missing ones by that name, reports a failed pull, and does
  nothing for an environment that is not docker or podman;
- podman_copies() copies a GPU task with its compose files' NVIDIA device requests in CDI form, stamped, leaves the
  task in the repository and a task without a GPU request alone, and config_file() points at the copy."""
import contextlib
import io
import json
import os
import tempfile
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import efe  # noqa: E402

fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


A = "alpine:3.23.4@sha256:" + "5" * 64
G = "gogost/gost:3.2.7@sha256:" + "a" * 64
check(efe.qualified(A) == "docker.io/library/" + A, efe.qualified(A))
check(efe.qualified(G) == "docker.io/" + G, efe.qualified(G))
for ref in ("ghcr.io/mll-lab-nu/efe:monitor-0.2.0", "docker.io/library/python:3.12-slim", "localhost/x:1",
            "registry:5000/x/y:1"):
    check(efe.qualified(ref) == ref, f"{ref} -> {efe.qualified(ref)}")

check(efe.engine_of(["-a", "oracle"]) == "docker", "no -e: docker")
check(efe.engine_of(["-e", "podman", "-a", "oracle"]) == "podman", "-e podman")
check(efe.engine_of(["--env=podman"]) == "podman", "--env=podman")
check(efe.engine_of(["--env", "docker"]) == "docker", "--env docker")
check(efe.engine_of(["-e", "modal"]) is None, "-e modal: no local engine")


class Engine:
    """A fake `docker` / `podman`: `image inspect` succeeds for the refs in `have`, `pull` for those not in `bad`."""
    def __init__(self, have=(), bad=()):
        self.have, self.bad, self.calls = set(have), set(bad), []

    def __call__(self, cmd, **kw):
        self.calls.append(cmd[1:])
        if cmd[1:3] == ["image", "inspect"]:
            rc = 0 if cmd[3] in self.have else 1
        elif cmd[1] == "pull":
            rc = 1 if cmd[-1] in self.bad else 0
        else:
            rc = 2
        return subprocess.CompletedProcess(cmd, rc, b"", b"")


qa, qg = efe.qualified(A), efe.qualified(G)
real_which = efe.shutil.which
efe.shutil.which = lambda name: "/usr/bin/" + name
err = io.StringIO()
try:
    e = Engine(have={qa})
    with contextlib.redirect_stderr(err):
        check(efe.prepull("podman", [qa, qg], run=e) == [], "a pull that works is no failure")
    check(e.calls == [["image", "inspect", qa], ["image", "inspect", qg], ["pull", "-q", qg]],
          f"present refs are not pulled again, missing ones by their full name: {e.calls}")
    e = Engine(bad={qg})
    with contextlib.redirect_stderr(err):
        check(efe.prepull("docker", [qg], run=e) == [qg], "a failed pull is reported")
    check("could not pull " + qg in err.getvalue(), "a failed pull is reported on stderr")
    e = Engine()
    check(efe.prepull(None, [qa], run=e) == [] and not e.calls, "no local engine: nothing runs")
finally:
    efe.shutil.which = real_which
efe.shutil.which = lambda name: None
try:
    e = Engine()
    check(efe.prepull("podman", [qa], run=e) == [] and not e.calls, "engine not installed: nothing runs")
finally:
    efe.shutil.which = real_which

try:   # with Harbor installed: the probe image on docker, the probe image and the sidecar's base on podman
    import harbor  # noqa: F401
    d, p = efe.short_name_images("docker"), efe.short_name_images("podman")
    check(len(d) == 1 and d[0].startswith("docker.io/library/alpine"), f"docker: {d}")
    check(len(p) == 2 and p[0] == d[0] and p[1].startswith("docker.io/"), f"podman: {p}")
except ImportError:
    print("note: Harbor is not installed; short_name_images() not checked")

GPU = "robotwin_2_0_stack_blocks_two-privileged"
CPU = next(t.name for t in efe.tc.iter_tasks() if not any(
    "driver: nvidia" in f.read_text() for f in t.rglob("docker-compose*.yaml")))
src = efe.tc.task_dir(GPU)
before = {f: f.read_bytes() for f in src.rglob("docker-compose*.yaml")}
check(before and all(b"driver: nvidia" in b for b in before.values()), f"{GPU}: requests an NVIDIA GPU")
with tempfile.TemporaryDirectory() as out:
    os.environ["EFE_PODMAN_GPUS"] = "nvidia.com/gpu=0"
    where = efe.podman_copies([GPU, CPU], out)
    check(set(where) == {GPU}, f"only the GPU task is copied: {where}")
    dst = Path(where.get(GPU, out))
    check(dst.parent.name == src.parent.name, f"the copy is under its benchmark folder: {dst}")
    for f, b in before.items():
        c = (dst / f.relative_to(src)).read_text()
        check("driver: nvidia" not in c and "- driver: cdi" in c and '["nvidia.com/gpu=0"]' in c and "count:" not in c,
              f"{f.relative_to(src)}: CDI request in the copy")
        check(f.read_bytes() == b, f"{f}: the task in the repository is unchanged")
    import stamp_mtimes
    check(stamp_mtimes.stamp_tree(str(dst), check=True)["bad"] == 0, "the copy is stamped after the rewrite")
    cfg = efe.config_file([GPU, CPU], where)
    ds = {d["path"]: d["task_names"] for d in json.load(open(cfg))["datasets"]}
    os.unlink(cfg)
    check(ds.get(str(dst.parent)) == [GPU] and ds.get(str(efe.tc.task_dir(CPU).parent)) == [CPU], f"datasets: {ds}")

if fails:
    print("FAIL test_efe.py:\n  " + "\n  ".join(fails))
    sys.exit(1)
print("ok test_efe.py")
