"""RoboOlympics match core (docs/framework_zh.md §5): hosts every match under one set of rules.

Flow (clock, slowdown, freeze and review, seats and turns), rules (formats, modes), records (episode log, replay,
metering) and judgement (outcome, validity). It names no sport and no harness (ci_checks/check-core-purity.sh), computes
no physics, and changes only in its own commits with a version bump (VERSION) and every sport's golden replay passing.
"""
VERSION = "0.2.34"   # 0.2.34: the skill in the loop served from the agent's own container (`game skill serve`,
# skilleval/skillhost.py serve --tcp --live; RCB_SKILL_INLOOP_<seat> = "tcp:127.0.0.1:PORT"): the simulator calls
# it over the loopback of the shared network namespace; it reloads the skill whenever its files change (the new
# version plays from the next call, its sha256 logged); a missing server is the player's error (the call lowers
# to the no-op); no agent code runs next to the simulator (hub H.3)
# 0.2.32: the skill upload (POST /<seat>/skill, an UploadHost running the skill in the sim's own jail): removed in
# robot_coding_bench's copy (robot_coding_bench (board 0152 decision 28, option c)): the skill runs only in the agent's own container
# (0.2.34's `game skill serve`); step() is one bounded synchronous call per due control step (skilleval/inloop.py
# timing "sync"); every version of the skill that played is an episode row skill_load.
# 0.2.31: built-in seats (RO_BUILTIN_SEATS, core/builtin_seat.py): a seat played by a built-in player in the
# service process through the same handlers, never served over HTTP; a player with uses_truth gets Match.builtin_truth
# (0.2.30 is taken by the fexam-vidfix branch)
# 0.2.33: model-API validity (api_errors.py): recovered transient errors are only recorded
# (final.json api_retries / api_wait_s / api_failure_reason per seat, reward <seat>_api_retries / _api_wait_s); a seat's
# API fails the trial on an unrecovered error, or above the sanity cap (> 50 transient errors, or >= 60 s and > 20% of
# its model session lost to errors); before, > 5 transient errors did (0.2.30-0.2.32 are taken by unmerged branches)
# 0.2.29: the replay video's frame rate from sport.toml [broadcast] fps (default 10) and
# event frames (Match.spectator_frames(), drawn before a step's regular frame; core/spectator.py), spectators only
# 0.2.28: a sport's own spectator scene for the replay video (Sport.spectator_scene(cfg) with
# Match.spectator_state(); core/spectator.py), never the players' images (0.2.27: the unmetered player mode, below)
# 0.2.27: player mode "unmetered" (PLAYER_MODE_<seat>: the runner meters the model; no proxy, no meter)
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
