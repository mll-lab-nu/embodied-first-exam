"""Wang-layout relay recipes supplied with the 2026-10-03 IK source export."""
import json
from pathlib import Path

VARIATIONS = ("easy", "medium", "hard")
ASSIGNMENT = {"A": "right", "B": "left"}
HOLD_STEP_M = .01


def normalize_variation(value):
    value = value.removeprefix("rope_threading_")
    if value not in VARIATIONS:
        raise ValueError(f"No Wang relay profile for {value!r}")
    return value


def candidate_plans(variation):
    """Relay plans over abstract hands A/B (A = right, B = left by default).

    Verified on medium under the Wang placement (2026-10-01): A grasps the tip
    on the table and pushes R1; B receives beyond R1 and pulls 190 mm; B
    releases, regrasps 200 mm behind the tip and pushes the tip through R2 into
    R3 (no hand fits between R2 and R3); A receives beyond the last ring and
    pulls the overhang towards its own side. Later entries are fallbacks.
    """
    variation = normalize_variation(variation)
    if variation == "hard":
        return json.loads(Path(__file__).with_name("hard_plans.json").read_text())
    ring_count = 2 if variation == "easy" else 3
    A, B = "A", "B"
    def e(k, pusher, station, receiver, pull, poke=.05, rs=.02):
        return dict(ring=k, pusher=pusher, pusher_station_m=station, poke_m=poke, receiver=receiver,
                    receiver_station_m=rs if receiver else station, pull_m=pull,
                    pusher_orientation=None, receiver_orientation=None)
    def solo(k, hand, station, poke, rs=.01):
        return dict(ring=k, pusher=hand, pusher_station_m=station, poke_m=poke, receiver=None,
                    receiver_station_m=rs, pull_m=.12, pusher_orientation=None, receiver_orientation=None)
    if ring_count == 2:
        return [
            ("A10_B_pull19_B20_recvA", [e(0, A, .10, B, .19), e(1, B, .20, A, .12, poke=.06, rs=.01)]),
            ("A10_B_pull19_B20_solo", [e(0, A, .10, B, .19), solo(1, B, .20, .06)]),
            ("A10_B_pull12_B10_recvA", [e(0, A, .10, B, .12), e(1, B, .10, A, .12, poke=.06, rs=.01)]),
        ]
    return [
        ("A10_B_pull19_B20_keep_recvA6", [e(0, A, .10, B, .19), e(1, B, .20, None, 0.), e(2, B, .20, A, .12, poke=.06, rs=.01)]),
        ("A10_B_pull19_B20_keep_solo6", [e(0, A, .10, B, .19), e(1, B, .20, None, 0.), solo(2, B, .20, .06)]),
        ("A10_B_pull19_B20_keep_recvA5", [e(0, A, .10, B, .19), e(1, B, .20, None, 0.), e(2, B, .20, A, .12, poke=.05, rs=.0)]),
    ]
