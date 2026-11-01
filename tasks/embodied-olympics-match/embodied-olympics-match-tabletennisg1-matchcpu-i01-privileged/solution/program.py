"""The reference program of the privileged twin: the sport's camera-only reference player (builtin_players.py:
OpenReference, its learned striker in skill/) in its in-process form (one control cycle per view). It ignores
view["truth"]; a full-state program can do better."""
import builtin_players as bp


def make_policy(config):
    return bp.OpenReference(config["spec"], config.get("seat", "A"), int(config.get("seed", 0)))
