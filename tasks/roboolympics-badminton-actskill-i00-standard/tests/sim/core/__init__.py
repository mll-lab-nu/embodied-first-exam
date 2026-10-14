"""RoboOlympics match core (docs/framework_zh.md §5): hosts every match under one set of rules.

Flow (clock, slowdown, freeze and review, seats and turns), rules (formats, modes), records (episode log, replay,
metering) and judgement (outcome, validity). It names no sport and no harness (ci_checks/check-core-purity.sh), computes
no physics, and changes only in its own commits with a version bump (VERSION) and every sport's golden replay passing.
"""
VERSION = "0.2.24"   # 0.2.24: player mode "unmetered" (PLAYER_MODE_<seat>: the runner meters the model; no proxy, no meter)
# 0.2.23: the reaction report (report only): final.json `reaction` per seat, acts within the
# declared reaction delay D (count, share) and the actual delay (median, p90, max); act rows log `seen`, the replay
# recomputes it (core/episode.reaction_report)
# 0.2.22: a seat's metering proxy holds no other seat's credentials (launch.seat_env), a ChatGPT-subscription seat no task-wide key
# 0.2.21: built-in players may talk on the team channel (message(view); core/client.py, core/local.py);
# a preview format ([formats.<f>] preview = true) is never an official configuration
# 0.2.20: the team channel is read with a read mark (seq, team_since, POST /team), never consumed
# 0.2.19: once frozen (hidden seeds registered) only a registered hidden seed is official, over the sport's own rule; 0.2.18: a declared reaction delay
PROTOCOLS = {"realtime": "eai-standard-realtime/1.0", "turn": "eai-standard-turn/1.0"}
