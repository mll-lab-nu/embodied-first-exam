"""Trusted entrypoint; never import submitted code in this process."""

import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, "/opt/trusted")
from tools.fullsim.formal import evaluate

LOGS = Path("/logs/verifier")
# Harbor makes /logs/verifier world-writable: root only from here on (the policy runs as nobody).
LOGS.chmod(0o755)
for entry in LOGS.iterdir():
    if entry.lstat().st_uid != 0:
        shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
instance = json.loads(Path("/tests/match_instance.json").read_text())
result = evaluate(
    Path("/app/output/policy"),
    LOGS / "evaluation",
    sport=instance["sport"],
    level=instance["level"],
    seed=instance["seed"],
    dev_root=Path("/opt/dev"),
)
for name in ("reward.txt", "reward.json", "diagnostics.json"):
    target = LOGS / name
    if target.is_symlink() or target.exists():
        target.unlink()  # written fresh, never through a link someone else left
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write((LOGS / "evaluation" / name).read_bytes())
print(json.dumps(result))
