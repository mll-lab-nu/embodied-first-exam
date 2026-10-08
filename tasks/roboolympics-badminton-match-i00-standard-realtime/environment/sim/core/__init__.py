"""RoboOlympics match core (docs/framework_zh.md §5): hosts every match under one set of rules.

Flow (clock, slowdown, freeze and review, seats and turns), rules (formats, modes), records (episode log, replay,
metering) and judgement (outcome, validity). It names no sport and no harness (ci_checks/check-core-purity.sh), computes
no physics, and changes only in its own commits with a version bump (VERSION) and every sport's golden replay passing.
"""
VERSION = "0.2.13"
PROTOCOLS = {"realtime": "eai-standard-realtime/1.0", "turn": "eai-standard-turn/1.0"}
