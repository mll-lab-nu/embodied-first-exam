"""Trusted launcher: one metering proxy per seat (A on 18090, B on 18091) and the duel service; credentials and meters
remain in the simulator service."""
import os
import subprocess
import sys
import time
from pathlib import Path

if len(sys.argv) > 1:
    side = sys.argv[1]
    os.environ["THINK_CLIENT_HOST"] = "seat_" + side.lower()
    os.environ["THINK_USAGE_FILE"] = f"/data/think_usage_{side}.json"
    # per-seat route for OpenAI-style calls (THINK_OPENAI_ROUTE_A / _B), e.g. one Codex seat on Azure, one on OpenRouter
    if os.environ.get(f"THINK_OPENAI_ROUTE_{side}"):
        os.environ["THINK_OPENAI_ROUTE"] = os.environ[f"THINK_OPENAI_ROUTE_{side}"]
    # per-seat Claude subscription (CLAUDE_ACCOUNT_A / _B = 2: CLAUDE_CODE_OAUTH_TOKEN_2), e.g. one per Claude model
    if os.environ.get(f"CLAUDE_ACCOUNT_{side}") == "2" and os.environ.get("CLAUDE_CODE_OAUTH_TOKEN_2"):
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = os.environ["CLAUDE_CODE_OAUTH_TOKEN_2"]
    os.execv(sys.executable, [sys.executable, "/srv/think_proxy.py", "18090" if side == "A" else "18091"])

Path("/data").mkdir(exist_ok=True)
procs = []
try:
    for side in ("A", "B"):
        procs.append(subprocess.Popen([sys.executable, __file__, side]))
    procs.append(subprocess.Popen([sys.executable, "/srv/server_duel.py"]))
    while all(p.poll() is None for p in procs):
        time.sleep(.5)
    raise RuntimeError("a required service exited")
finally:
    for p in procs:
        if p.poll() is None:
            p.terminate()
    for p in procs:
        try:
            p.wait(timeout=3)
        except subprocess.TimeoutExpired:
            p.kill()
