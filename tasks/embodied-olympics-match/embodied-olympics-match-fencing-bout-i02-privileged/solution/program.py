"""The full-state reference program for fencing (the privileged twin's oracle): the sport's reference player
(builtin_players.Reference: it reads the opponent from the phrases so far and answers by the phrase table) as the
twin's oracle plays it; it needs no more than the phrase record, so the truth is not used."""

from builtin_players import Reference


def make_policy(config):
    return Policy(config["spec"])


class Policy:
    def __init__(self, spec):
        self.ref = Reference(spec, "A", 0)   # the twin's oracle: player seed 0 (RO_PLAYER_SEED's default)

    def act(self, view):
        if view["state"]["phase"] == "unit_over":
            return {"type": "ready"}         # the review after each phrase
        return self.ref.act(view)
