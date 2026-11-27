"""eai-standard/2.x for Embodied Olympics - Match (docs/protocol/standard_mode.md Part 5, the match extension): the
standard endpoints (/spec /status /observe /submit) and the match's own calls as extension endpoints (/start /ready
/say /team), served next to the core's seat API (/<SEAT>/..., the `game` command) by the same process. A translation
layer only: it calls the match service's own methods (core/realtime.py, core/lockstep.py, core/turn.py, unchanged), so
the match, its clock, referee, record and grading are the core's. Nothing here is under core/ or sport/: the match's
source_sha does not change."""
