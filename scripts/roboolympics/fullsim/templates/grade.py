"""Trusted entrypoint; never import submitted code in this process."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/opt/trusted")
from tools.tt_fullsim.formal import evaluate

LOGS = Path("/logs/verifier")
# Harbor makes /logs/verifier world-writable: root only from here on (the policy runs as nobody).
LOGS.chmod(0o755)
for entry in LOGS.iterdir():
    if entry.lstat().st_uid != 0:
        shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
instance = json.loads(Path("/tests/match_instance.json").read_text())
try:
    result = evaluate(
        Path("/app/output/policy"),
        LOGS / "evaluation",
        level=instance["level"],
        seed=instance["seed"],
        slowdown=instance["slowdown"],
        wall_limit=instance["wall_limit_s"],
        dev_root=Path("/opt/dev"),
    )
    files = {name: (LOGS / "evaluation" / name).read_bytes() for name in ("reward.txt", "reward.json", "diagnostics.json")}
except Exception as exc:  # noqa: BLE001 -- never end without a reward (#282 review, H.1): an infra error, success 0
    result = {"success": 0, "valid": 0, "infra_error": 1, "grader_error": 1}
    files = {"reward.txt": b"0\n", "reward.json": json.dumps(result).encode(),
             "diagnostics.json": json.dumps({"grader_error": f"{type(exc).__name__}: {exc}"[:2000]}).encode()}
for name, data in files.items():
    target = LOGS / name
    if target.is_symlink() or target.exists():
        target.unlink()  # written fresh, never through a link someone else left
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
print(json.dumps(result))

# Replay video, for spectators only (the owner's rule of 2026-10-16: every trial has a video; PROTOCOL §4). It runs after
# the verdict above is written and nothing reads it back: any failure only leaves no replay.mp4 (video.json says why).
# A fresh process replays the formal match's record (evaluation/match/episode.jsonl) on the trusted simulator and draws
# it as the standard-realtime twin's service does: spectator/sport_video.py when the simulator has it (badminton: the
# players' cameras), else core.spectator (the sport's spectator camera). VIDEO_TIMEOUT_S is part of the verifier's
# timeout (the generator adds it).
VIDEO_TIMEOUT_S = 1800


def write_new(target, data):
    if target.is_symlink() or target.exists():
        target.unlink()
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def replay_video(match):
    trusted = Path("/opt/trusted")
    plugins = sorted((trusted / "sports").glob("*/plugin.py"))
    try:
        if len(plugins) != 1 or not (match / "episode.jsonl").is_file():
            raise FileNotFoundError("no record of a formal match to replay")
        own = trusted / "spectator" / "sport_video.py"
        cmd = [sys.executable, "-B", str(own)] if own.is_file() else [sys.executable, "-B", "-m", "core.spectator"]
        env = {k: os.environ[k] for k in ("PATH", "LANG", "LC_ALL", "LD_LIBRARY_PATH") if k in os.environ}
        env.update(PYTHONPATH=str(trusted), HOME="/tmp", MUJOCO_GL="osmesa", PYOPENGL_PLATFORM="osmesa",
                   RO_RENDERER="mujoco", RO_VIDEO_RENDERER="", OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
        for stale in ("replay.mp4", "replay.part.mp4", "video.json"):
            (match / stale).unlink(missing_ok=True)
        run = subprocess.run(cmd + [str(plugins[0]), str(match)], cwd=trusted, env=env, timeout=VIDEO_TIMEOUT_S,
                             stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, check=False)
        if run.returncode != 0 or not (match / "replay.mp4").is_file():
            raise RuntimeError(f"renderer exit {run.returncode}: {run.stderr[-300:]}")
        info = json.loads((match / "video.json").read_text())
        write_new(LOGS / "replay.mp4", (match / "replay.mp4").read_bytes())
    except Exception as exc:  # noqa: BLE001 -- spectators only: never the verdict
        info = {"video": False, "why": f"{type(exc).__name__}: {exc}"[:400]}
    write_new(LOGS / "video.json", json.dumps(info).encode())
    return info


replay_video(LOGS / "evaluation" / "match")
