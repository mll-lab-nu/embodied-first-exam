"""Robot epee fencing (sports/fencing, fencing-7: the phrase-level sport): the privileged twin of the exported
turn-based bout embodied-olympics-match-fencing-bout-i02-standard (level 2, seed 35, chess clock 3600 s, cutoff 7200 s).

The twin's rules, referee, scripted fencer, phrase table and chess clock are unchanged; only the information (the
full state instead of the observation's phrase record and images) and the development rights (the full simulator,
whole-bout reset) differ. The twin is a turn sport (core TurnService): the formal bout runs in the task's own
tools/fullsim/turn.py, on that service; nothing of sports/fencing changes (PROTOCOL H.7).
"""

from __future__ import annotations

import json

SPORT = "fencing"
FORMAT = "bout"                          # the twin's RO_FORMAT
SEATS = ("A",)
ACTION_LEVEL = "low"                     # the twin's RCB_ACTION_LEVEL (fencing-7 has the low level only)
LEVELS = (1, 2)                          # opponent.LEVELS
SOURCE_TASK = "fencing-bout-wallclock-program-standard"
FAMILY = "fencing-bout"
ROBOT = "unitree-g1"                     # the twin's [metadata] robot
METADATA_FAMILY = "fencing_bout"         # the twin's [metadata] family
INSTANCES = {"i02": {"level": 2, "seed": 35}}   # the twin's RO_LEVEL / RO_SEED
SLOWDOWN = None                          # a turn sport has no slowdown
CLOCK_S = 3600                          # the twin's CLOCK_S: the seat's chess clock (runs on its turn only)
CUTOFF_S = 7200                         # the twin's [agent] timeout_sec
READY_TIMEOUT_S = 300                    # the twin's READY_TIMEOUT_S
REPLAY_TIMEOUT_S = 600                   # the twin's RO_REPLAY_TIMEOUT_S
VIDEO_TIMEOUT_S = 900                    # the twin's RCB_VIDEO_TIMEOUT_S
MATCH_WALL_S = 4200                      # the chess clock plus the service's own time
IMAGE = "ghcr.io/mll-lab-nu/efe:embodied-olympics-match-0.1.0@sha256:99255569bf68bcf27f4e4867b58bad55c1d54fe73281920882e97c310836b6c7"
RESOURCES = {"min_cpus": 2.0, "min_memory_gb": 4.0, "verifier_min_cpus": 2.0, "verifier_min_memory_gb": 4.0}
DESCRIPTION = "robot epee fencing, one FIE direct-elimination bout phrase by phrase against the scripted fencer"
TRUTH_DOC = '`view["truth"]` is the state of the bout at the decision (nothing of the coming phrase):\n\n- `bout`: the referee\'s whole state (`score`, fencing time `t`, the minute\'s start, `extra` minute, `priority`,\n  `p_calls`, `winner`, `how`, and `log`: every phrase so far with both intentions, both start delays, the ends of the\n  piste, the result and the score after it); `phrase` (the next phrase\'s number), `time_left_s`, `no_hit_s`;\n- `opponent`: the scripted fencer\'s whole state (`level`, its history `hist` of what it has seen, and its random\n  generator\'s state `rng`): with the simulator (`sports/fencing/opponent.py`) its next choice can be computed;\n- `table_sha256`: the phrase table\'s digest (`sports/fencing/phrases/table.json`, the 2916 measured phrases).'
NOTES_DOC = 'A turn sport: there is no world between decisions. Each of your actions is your intention for the next phrase\n(`{"type": "phrase", "intention": ...}`, the nine intentions of `Session.spec()`); the scripted fencer chooses its own\nfrom what it has seen of the bout (never from your choice for this phrase), and the phrase is played from the measured\ntable with this phrase\'s start delays and ends, drawn from the seed (`sports/fencing/phrases.py` `play`), then judged\n(`sports/fencing/bout.py`). The rules (FIE direct elimination: 15 touches or 9 minutes of fencing time, the extra\nminute, unwillingness to fight) and the table: `Session.spec()` and `sports/fencing/sport.toml`.'


def _plain(v):
    return json.loads(json.dumps(v, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)))


def truth(match):
    b = match.bout
    return {
        "bout": _plain(b.state()),
        "phrase": len(b.log) + 1,
        "time_left_s": b.time_left_s(),
        "no_hit_s": b.no_hit_s(),
        "opponent": _plain(match.opp.state()) if match.opp is not None else None,
        "table_sha256": match.table.sha,
    }
