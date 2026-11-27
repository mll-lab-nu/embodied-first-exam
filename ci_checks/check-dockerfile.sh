#!/usr/bin/env bash
# ADVISORY (docs/protocol/tasks.md: images pinned for reproducibility; the frozen instance's hash check backs it up at run
# time): every FROM of a Dockerfile under environment/ or tests/ (every stage) is a registry image with an explicit,
# non-`latest` tag or digest, and so is every compose `image:` (environment/ and tests/); every `COPY --from=<image>`
# (files-only images, the monitor's code) names its image by digest. Moved here from
# check-verifier-isolation.sh: a pin is reproducibility, not the trust boundary. Also: no image is built with the task's
# README.md and no container mounts it (no COPY / ADD of a README, no compose build context at the task directory).
t="$1"; python3 - "$t" <<'PY'
import pathlib, re, sys
t = pathlib.Path(sys.argv[1]); rc = 0
PINNED = re.compile(r"^[\w.\-]+(:\d+)?/.+[:@].+")
def fail(m):
    global rc; print(f"FAIL {t}: {m}"); rc = 1
for df in sorted(p for sub in ("environment", "tests") if (t / sub).is_dir() for p in (t / sub).rglob("Dockerfile")):
    rel = df.relative_to(t).as_posix()
    froms = re.findall(r"^FROM\s+(?:--\S+\s+)*(\S+)(?:\s+AS\s+(\S+))?", df.read_text(), re.M | re.I) or [("", "")]
    for k, (frm, _) in enumerate(froms):
        if frm in [a for _, a in froms[:k] if a]: continue     # an earlier stage of this file
        if not (PINNED.match(frm) and not frm.endswith(":latest") and "$" not in frm):
            fail(f"{rel} FROM {frm!r} must be a pinned registry image (<registry>/<image>:<tag> or @sha256, never :latest)")
    stages = {a for _, a in froms if a}
    for src in re.findall(r"^COPY\s+(?:--\S+\s+)*--from=(\S+)", df.read_text(), re.M | re.I):
        if src in stages or src.isdigit():
            continue                                          # an earlier stage of this file
        if not (PINNED.match(src) and "@sha256:" in src and "$" not in src):
            fail(f"{rel} COPY --from={src!r} must name a registry image by digest (<registry>/<image>:<tag>@sha256:<digest>)")
# The task's README.md is for people (its success criteria are exact): no image is built with it and no container mounts
# it. A Dockerfile never COPYs / ADDs a README.md from its build context (`COPY --from=<image>` takes another image's
# files: not the task's), and no compose build context reaches the task directory itself (environment/'s parent).
for df in sorted(p for sub in ("environment", "tests") if (t / sub).is_dir() for p in (t / sub).rglob("Dockerfile")):
    rel = df.relative_to(t).as_posix()
    for ln in re.findall(r"^\s*(?:COPY|ADD)\s+(.*)$", df.read_text(), re.M | re.I):
        if re.search(r"--from=", ln, re.I):
            continue
        srcs = [w for w in ln.split() if not w.startswith("--")][:-1]
        if any(re.search(r"(?:^|/)README(?:\.md)?$", w.strip("'\"[],"), re.I) for w in srcs):
            fail(f"{rel} copies a README into an image ({ln.strip()[:80]!r}): the task's README.md stays out of every image")
for cf in (t / "environment/docker-compose.yaml", t / "tests/docker-compose.yaml"):
    if cf.is_file():
        body = cf.read_text()
        for ctx in re.findall(r"^\s*context:\s*['\"]?([^'\"#\s]+)", body, re.M):
            if (cf.parent / ctx).resolve() in [t.resolve(), *t.resolve().parents]:
                fail(f"{cf.relative_to(t).as_posix()} build context {ctx!r} holds the task's README.md: build from a subdirectory")
        for ln in re.findall(r"^\s*-\s*(.*)$", body, re.M):     # a volume whose source is a README (not a ${VAR:?message})
            src = re.sub(r"\$\{[^}]*\}", "VAR", ln.strip().strip("'\"")).split(":", 1)[0]
            if not ln.lstrip().startswith("#") and re.search(r"(?:^|/)README(?:\.md)?$", src, re.I):
                fail(f"{cf.relative_to(t).as_posix()} mounts a README.md ({ln.strip()[:80]!r}): the task's README.md stays out of every container")
for cf in (t / "environment/docker-compose.yaml", t / "tests/docker-compose.yaml"):
    if cf.is_file():
        for img in re.findall(r"^\s*image:\s*(\S+)", cf.read_text(), re.M):
            img = img.strip("'\"")
            if not (PINNED.match(img) and not img.endswith(":latest") and "$" not in img):
                fail(f"compose sidecar image {img!r} must be pinned")
sys.exit(rc)
PY
