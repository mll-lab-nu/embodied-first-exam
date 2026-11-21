"""The ablation switches of the EO Match services (docs/ablations.md), all off by default.

The sim service runs `python3 /srv/rcb_ablation/launch.py` instead of `/srv/core/launch.py` only in an ablation's task
dirs; with every switch off it serves exactly what the core serves. Each switch is read once, at import:

  RCB_HIDE_SUCCESS=1   no success signal: the score, the point and rally results and the verdict are left out of every
                       reply; POST /finish ends the agent's session (graded as the end of the session is graded)
  RCB_STATE_QUERY=1    GET /state/entities, POST /state/query: the simulator's state (read only, no clock effect)
  RCB_STATE_OPS=1      POST /reset, /save_state, /load_state; RCB_RESET_BUDGET resets (default 0)
"""
import os

HIDE = os.environ.get("RCB_HIDE_SUCCESS", "0") == "1"
QUERY = os.environ.get("RCB_STATE_QUERY", "0") == "1"
OPS = os.environ.get("RCB_STATE_OPS", "0") == "1"
try:
    BUDGET = max(0, int(os.environ.get("RCB_RESET_BUDGET", "0") or 0))
except ValueError:
    BUDGET = 0
try:
    MAX_HANDLES = max(1, int(os.environ.get("RCB_MAX_STATE_HANDLES", "32") or 32))
except ValueError:
    MAX_HANDLES = 32
ANY = HIDE or QUERY or OPS
