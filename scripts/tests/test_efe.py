#!/usr/bin/env python3
"""scripts/efe.py prepull (standard library only, no docker, no Harbor needed):

- qualified() gives a Docker Hub short name its registry and leaves a ref that names one alone;
- engine_of() reads -e / --env: docker by default, podman, None for any other environment;
- prepull() asks the engine for each ref, pulls only the missing ones by that name, reports a failed pull, and does
  nothing for an environment that is not docker or podman;
- podman_copies() copies a GPU task with its compose files' NVIDIA device requests in CDI form, stamped, leaves the
  task in the repository and a task without a GPU request alone, and config_file() points at the copy;
- from_prebuilt() replaces a base image's recipe stage with `FROM <the prebuilt image> AS <stage>`, and podman_copies()
  does that in the copy (environment/, environment/sim/, tests/) only when podman has or can pull the image, never with
  EFE_PODMAN_BUILD_FROM_SOURCE=1."""
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
    "driver: nvidia" in f.read_text() for f in t.rglob("docker-compose*.yaml"))
    and not any("# >>> images/" in f.read_text() for f in t.rglob("Dockerfile")))
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

# --- pull-first on podman: a base image's recipe stage becomes FROM the prebuilt image ---------------------------------
R = "ghcr.io/mll-lab-nu/efe-private:sim-0.1.0"
D = ("# head\n# >>> images/sim/Dockerfile\n# recipe\nFROM docker.io/library/debian:12 AS sim-base\nRUN make\n"
     "# <<< images/sim/Dockerfile\nFROM sim-base\nCOPY a /a\n")
out = efe.from_prebuilt(D, {"sim": R})
check(out.startswith("# head\n# images/sim/Dockerfile: the prebuilt image") and f"\nFROM {R} AS sim-base\nFROM sim-base\nCOPY a /a\n"
      in out and "RUN make" not in out and "# >>>" not in out, f"the stage is FROM the prebuilt image: {out!r}")
check(efe.from_prebuilt(D, {}) == D and efe.from_prebuilt(D, {"other": R}) == D, "no image for the stage: unchanged")
TWO = D.replace("RUN make\n", "RUN make\nFROM sim-base AS sim2-base\nRUN more\n").replace("FROM sim-base\nCOPY", "FROM sim2-base\nCOPY")
check(f"FROM {R} AS sim2-base\nFROM sim2-base\n" in efe.from_prebuilt(TWO, {"sim": R}), "two stages: FROM the image AS the last")
USED = TWO + "COPY --from=sim-base /x /x\n"
check(efe.from_prebuilt(USED, {"sim": R}) == USED, "an inner stage used later: the recipe is kept")

VLB = "vlabench-add-condiment-i00-privileged"
VLS = "vlabench-add-condiment-i00-standard"
ref = efe.cache_refs(efe.tc.task_dir(VLB)).get("vlabench", "")
check(ref.startswith("ghcr.io/mll-lab-nu/efe-private:vlabench-"), f"cache_refs: {ref}")
real_which = efe.shutil.which
efe.shutil.which = lambda name: "/usr/bin/" + name
srcs = {t: efe.tc.task_dir(t) for t in (VLB, VLS, GPU)}
before = {f: f.read_bytes() for d in srcs.values() for f in d.rglob("*") if f.is_file()}
try:
    with tempfile.TemporaryDirectory() as out, contextlib.redirect_stderr(io.StringIO()):
        e = Engine(have=(), bad=())
        where = efe.podman_copies([VLB, VLS, GPU], out, run=e)
        check(set(where) == {VLB, VLS, GPU}, f"pull works: the base-stage tasks are copied too: {sorted(where)}")
        check(e.calls == [["image", "inspect", ref], ["pull", "-q", ref]], f"one image, asked and pulled once: {e.calls}")
        for t, subs in ((VLB, ("environment/Dockerfile", "tests/Dockerfile")), (VLS, ("environment/sim/Dockerfile",))):
            for sub in subs:
                c = (Path(where.get(t, out)) / sub).read_text() if t in where else ""
                check(f"\nFROM {ref} AS vlabench-base\n" in c and "# >>> images/" not in c and "pip install" not in c,
                      f"{t}/{sub}: FROM the prebuilt image")
        check(stamp_mtimes.stamp_tree(where.get(VLB, out), check=True)["bad"] == 0, "the rewritten copy is stamped")
        g = (Path(where.get(GPU, out)) / "environment/Dockerfile").read_text() if GPU in where else ""
        check(g == (srcs[GPU] / "environment/Dockerfile").read_text(), "a task without a base stage: Dockerfile as is")
    with tempfile.TemporaryDirectory() as out, contextlib.redirect_stderr(err):
        e = Engine(bad={ref})
        where = efe.podman_copies([VLB, VLS, GPU], out, run=e)
        check(set(where) == {GPU}, f"pull fails: no copy for a CPU task, built from source: {sorted(where)}")
        check(e.calls == [["image", "inspect", ref], ["pull", "-q", ref]], f"a failed pull is not retried: {e.calls}")
        check("building its recipe from source" in err.getvalue(), "a failed pull says so")
    with tempfile.TemporaryDirectory() as out:
        e = Engine(have={ref})
        os.environ["EFE_PODMAN_BUILD_FROM_SOURCE"] = "1"
        try:
            where = efe.podman_copies([VLB, VLS, GPU], out, run=e)
        finally:
            del os.environ["EFE_PODMAN_BUILD_FROM_SOURCE"]
        check(set(where) == {GPU} and not e.calls, f"EFE_PODMAN_BUILD_FROM_SOURCE=1: no pull, no rewrite: {e.calls}")
    with tempfile.TemporaryDirectory() as out:
        where = efe.podman_copies([VLB], out, run=Engine(have={ref}))
        check(set(where) == {VLB}, "an image already present is used without a pull")
finally:
    efe.shutil.which = real_which
check(all(f.read_bytes() == b for f, b in before.items()), "the tasks in the repository are unchanged")

if fails:
    print("FAIL test_efe.py:\n  " + "\n  ".join(fails))
    sys.exit(1)
print("ok test_efe.py")
