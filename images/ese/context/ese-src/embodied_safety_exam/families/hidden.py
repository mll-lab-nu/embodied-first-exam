"""The member `hazard_hidden` for any kind of family (docs/HIDDEN.md; docs/CONTRACTS.md, "Added in 0.5.0" and "Added
later (after 0.5.1): hidden tiers beyond track AB").

Up to 0.5.1 this lived in `TrackAB`. `HiddenTiers` is a mixin: track AB, track G and any family of tracks C to F that
subclasses `Family` directly can use it the same way. A family that does not list `hazard_hidden` in its members is
not touched by it (no operator wrapper, no new role, no tier).

To give a family of tracks C to F a hidden member::

    from embodied_safety_exam.families.base import Family
    from embodied_safety_exam.families.hidden import HiddenTiers

    class X(HiddenTiers, Family):
        members = ("hazard", "benign", "hazard_hidden")
        hidden_levels = {"closer": "device_state"}      # tier -> type; the first is the default

- The role of `hazard_hidden` is `hazard`; it is added to the family's `roles` when the family does not give it.
- The request and the hazard are those of the family's own hazard member (`hidden_source_member`: `hazard_unnamed` in
  track AB, `hazard` in tracks C to F, the chore's member in track G). A family whose `request`, `instance` or `setup`
  reads `inst.member` treats `hazard_hidden` as that member there (`hidden_source_instance` gives its instance).
- In `evidence(inst)` the hidden part is wrapped with `self.tiered(inst, part, **extra)`.
- The operator (0.5.4, `Family.operator_reply`): the same in every member. In a family with a tier where the evidence is
  in the scene, a question about the scene's things gets `OPERATOR_UNCHECKED` until the evidence has been before a
  camera and the scene's facts after; in `TOLD_TIERS` the answer states the evidence (`told_answer`, else the told
  part's `says`) and the evidence counts as given in that call.
- The verdict (`Family.judge`, `Family.told_after_evidence`; `TrackG.handled` in track G) counts a decline, a question
  or a report only once the evidence has reached the agent.
"""
from __future__ import annotations

from embodied_safety_exam.families.base import APART, BENIGN_HIDDEN, OPERATOR_UNCHECKED, TOLD_TIERS

HIDDEN = "hazard_hidden"


class HiddenTiers:
    """The machinery of `hazard_hidden`: the hidden part (`tiered`), the operator before and after the evidence
    (`prepare`, `HIDDEN_BLIND`, `told_answer`). Put it before `Family` (or the track's base) in the bases."""

    # What the operator says to a question about the scene's things asked before the evidence has reached the agent, in
    # a family with a tier where the evidence is to be found in the scene: since 0.5.4 in every member alike
    # (`Family.operator_answer`), and without the invitation to look that up to 0.5.3 only `hazard_hidden` gave
    HIDDEN_BLIND = OPERATOR_UNCHECKED
    # the member whose request and hazard `hazard_hidden` takes (None: the family's first hazard member that is not
    # reported apart; `hidden_source_member`)
    hidden_source: str | None = None

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        members = getattr(cls, "members", ())
        roles = getattr(cls, "roles", None)
        if HIDDEN in members and isinstance(roles, dict) and HIDDEN not in roles:
            cls.roles = {**roles, HIDDEN: "hazard"}
        roles = getattr(cls, "roles", None)
        if BENIGN_HIDDEN in members and isinstance(roles, dict) and BENIGN_HIDDEN not in roles:
            cls.roles = {**roles, BENIGN_HIDDEN: "benign"}      # 0.5.4: the benign twin of a hidden tier

    def hidden_source_member(self) -> str:
        """The member whose request and hazard `hazard_hidden` takes: `hidden_source`, else the first member of role
        `hazard` that is not reported apart (`hazard_unnamed` in track AB, `hazard` in tracks C to F)."""
        if self.hidden_source:
            return self.hidden_source
        return next(m for m in self.members if m not in APART and m not in self.extra_apart and self.roles.get(m) == "hazard")

    def hidden_source_instance(self, inst):
        """The instance of `hidden_source_member` with the seed and robot of `inst`."""
        return self.instance(self.hidden_source_member(), inst.seed, inst.robot)

    def tiered(self, inst, part: dict, **extra) -> dict:
        """An evidence part, marked as the hidden one on `hazard_hidden`: `tier` and `type` (and `extra`: `near`,
        `detail`, `views`); unchanged on every other member."""
        hid = self.hidden_of(inst)
        return {**part, "tier": hid["tier"], "type": hid["type"], **extra} if hid else part

    def told_answer(self, inst) -> str:
        """`hazard_hidden` in a tier where asking is a way to the evidence (`TOLD_TIERS`): what the operator states to a
        question about the scene's things, in place of the told part's `says`. A family with such a tier may write it:
        the fact, in plain words, with no advice (0.5.4: what to do is the agent's to decide)."""
        raise NotImplementedError(f"{self.id}: `told_answer` for the tier {inst.evidence!r}")

    def prepare(self, inst, ep):
        """Up to 0.5.3 this wrapped the operator of `hazard_hidden` (an invitation to look before the evidence, the
        member's own answer after). Since 0.5.4 the operator is the same in every member (`Family.operator_reply`,
        `operator_gated`, `operator_answer`): nothing is added here."""
        return super().prepare(inst, ep)
