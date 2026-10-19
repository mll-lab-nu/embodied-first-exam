"""SkillLayer: the high level with its skill lowered by an implementation of the skill API instead of the platform's
(the competition test: "our fixed reference strategy on the agent's implementation", docs/framework_zh.md §6.3.7).

    layer = SkillLayer(sport.action_layer("high"), CONTRACTS, skill, decl, fallback=lambda seat, m: {...})
    core.local.play(with_layer(sport, "high", layer), cfg, players, plugin=PLUGIN)

parse() is the high level's own (same schema, same refusals); lower() calls skill.call(<skill>, *request, state=the
seat's whitelisted observation) and checks the answer against the match's low-level schema (core.sport.check_command).
A call that fails (error, time-out, an invalid command) lowers to `fallback(seat, match)` (a valid command that does
nothing useful, e.g. the weakest throw) or, without one, refuses the act; failures are counted in `failures`.
This covers turn-based sports; a realtime sport whose skill also has a periodic step() writes its own competition
hook with the same Skill interface (skilleval/sandbox.py)."""

from __future__ import annotations

from core.observe import filter_fields
from core.spec import whitelist
from core.sport import Refused, check_command

from .sandbox import SkillError


class SkillLayer:
    level = "high"

    def __init__(self, high, contracts: dict, skill, decl: dict, fallback=None):
        self.high, self.contracts, self.skill, self.fallback = high, contracts, skill, fallback
        self.allowed = whitelist(decl)
        self.failures: list[str] = []
        self.worker = None

    def schema(self, match, seat):
        return self.high.schema(match, seat)

    def parse(self, seat, body, match, ctx):
        return self.high.parse(seat, body, match, ctx)

    def snapshot(self, seat, cmd, match, ordinal):
        return None

    def prepare(self, job):
        return None

    def lower(self, seat, cmd, prepared, match):
        c = self.contracts.get(cmd.get("type"))
        if c is None:  # a high-level command that is not a skill (e.g. none)
            return self.high.lower(seat, cmd, prepared, match)
        state, _ = filter_fields(match.observe(seat), self.allowed)
        try:
            low = self.skill.call(c.name, *c.args_of(cmd), state=state)
            low = check_command(match.schema(seat), low)
        except (SkillError, Refused) as e:
            self.failures.append(f"{type(e).__name__}: {e}"[:300])
            if self.fallback is None:
                raise Refused("the skill implementation gave no valid command") from e
            return self.fallback(seat, match), {"skill_failed": True}
        return low, {"skill": c.name}

    def reply(self, seat, cmd, info, match):
        return {}


class _WithLayer:
    def __init__(self, sport, level, layer):
        self._sport, self._level, self._layer = sport, level, layer

    def action_layer(self, level):
        return self._layer if level == self._level else self._sport.action_layer(level)

    def __getattr__(self, k):
        return getattr(self._sport, k)


def with_layer(sport, level: str, layer):
    """The sport with `layer` as its action layer for `level` (everything else unchanged)."""
    return _WithLayer(sport, level, layer)
