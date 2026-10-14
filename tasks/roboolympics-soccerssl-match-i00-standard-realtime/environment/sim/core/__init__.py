"""RoboOlympics match core (docs/framework_zh.md §5): hosts every match under one set of rules.

Flow (clock, slowdown, freeze and review, seats and turns), rules (formats, modes), records (episode log, replay,
metering) and judgement (outcome, validity). It names no sport and no harness (ci_checks/check-core-purity.sh), computes
no physics, and changes only in its own commits with a version bump (VERSION) and every sport's golden replay passing.
"""
VERSION = "0.2.21"   # 0.2.21: player mode "unmetered" (PLAYER_MODE_<seat>: the runner meters the model); 0.2.19: once frozen (hidden seeds registered) only a registered hidden seed is official, over the sport's own rule; 0.2.18: a declared reaction delay (sport.toml [timing] reaction_delay_steps)
PROTOCOLS = {"realtime": "eai-standard-realtime/1.0", "turn": "eai-standard-turn/1.0"}
