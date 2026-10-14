"""RoboOlympics match core (docs/framework_zh.md §5): hosts every match under one set of rules.

Flow (clock, slowdown, freeze and review, seats and turns), rules (formats, modes), records (episode log, replay,
metering) and judgement (outcome, validity). It names no sport and no harness (ci_checks/check-core-purity.sh), computes
no physics, and changes only in its own commits with a version bump (VERSION) and every sport's golden replay passing.
"""
VERSION = "0.2.27"   # 0.2.27: player mode "unmetered" (PLAYER_MODE_<seat>: the runner meters the model; no proxy, no meter)
# 0.2.26: after the end, observe / act answer 409 with the final state and draw nothing (realtime and
# turn); after finalization a late draw returns no images and a late failure is only logged, never an error
# 0.2.25: diagnostic records (information only, never replayed, in no hash; core/diaglog.py):
# observe rows carry k and view_steps (both protocols), act_received k / act_id / obs_id_last / seen, new rows effect,
# act_dropped, event (what Match.step() returns) and team_delivered; core/local.py writes the same; the post-match
# diagnosis python -m core.diagnose PLUGIN RUN_DIR (core/diagnose.py: load() -> rep with a replayed world(), the
# sport's diagnose.py). 0.2.24 is skipped
# 0.2.23: the reaction report (report only): final.json `reaction` per seat, acts within the
# declared reaction delay D (count, share) and the actual delay (median, p90, max); act rows log `seen`, the replay
# recomputes it (core/episode.reaction_report)
# 0.2.22: a seat's metering proxy holds no other seat's credentials (launch.seat_env), a ChatGPT-subscription seat no task-wide key
# 0.2.21: built-in players may talk on the team channel (message(view); core/client.py, core/local.py);
# a preview format ([formats.<f>] preview = true) is never an official configuration
# 0.2.20: the team channel is read with a read mark (seq, team_since, POST /team), never consumed
# 0.2.19: once frozen (hidden seeds registered) only a registered hidden seed is official, over the sport's own rule; 0.2.18: a declared reaction delay
PROTOCOLS = {"realtime": "eai-standard-realtime/1.0", "turn": "eai-standard-turn/1.0"}
