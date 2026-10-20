#!/usr/bin/env bash
# ADVISORY (docs/protocol/README.md §1: images pinned for reproducibility; the frozen instance's hash check backs it up at run
# time): every FROM of a Dockerfile under environment/ or tests/ (every stage) is a registry image with an explicit,
# non-`latest` tag or digest, and so is every compose `image:` (environment/ and tests/); every `COPY --from=<image>`
# (files-only images, the monitor's code) names its image by digest. Moved here from
# check-verifier-isolation.sh: a pin is reproducibility, not the trust boundary.
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
for cf in (t / "environment/docker-compose.yaml", t / "tests/docker-compose.yaml"):
    if cf.is_file():
        for img in re.findall(r"^\s*image:\s*(\S+)", cf.read_text(), re.M):
            img = img.strip("'\"")
            if not (PINNED.match(img) and not img.endswith(":latest") and "$" not in img):
                fail(f"compose sidecar image {img!r} must be pinned")
sys.exit(rc)
PY
