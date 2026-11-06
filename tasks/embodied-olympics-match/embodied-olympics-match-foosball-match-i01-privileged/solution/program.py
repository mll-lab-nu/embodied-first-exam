"""The full-state reference program for foosball (the privileged twin's oracle): the camera-only reference player
(builtin_players.Reference: its opening, its blocks, its passes and its aimed shots with the player policy) with the
true ball and the true opposing figures in place of the overhead image (no colour detection, no tracker). Generated
from builtin_players.Reference.act of the frozen revision: only the perception block is replaced."""

from builtin_players import RODS, Reference

LEAD_S = 0.03  # the camera player's look-ahead (Tracker.estimate lead): the command reaches the motors 20 ms later


def make_policy(config):
    return TruthReference(dict(config["spec"]), "A", int((config["spec"].get("cfg") or {}).get("seed", 0)))


class TruthReference(Reference):
    def act(self, view):
        st = view.get("state") or {}
        if st.get("phase") == "unit_over":
            return {"type": "ready"}  # the review after a rally: carry on (the camera player's service sent it)
        if not st.get("rods") or st.get("awaiting_review") or st.get("game_over"):
            return None
        if self.policy is None or st.get("rally") != self.rally:
            self.rally, self.policy = st.get("rally"), self.new_policy(st)
        tr = view.get("truth") or {}
        t = st["t_rally"]
        b, v = tr["ball_pos"], tr["ball_vel"]
        p, w = (b[0] + v[0] * LEAD_S, b[1] + v[1] * LEAD_S), (v[0], v[1])  # seat A: local = world
        rods = {r: dict(slide=st["rods"][r]["slide"], angle=st["rods"][r]["angle"]) for r in RODS}
        rs = st.get("restart") or {}
        cmd = self.policy.update(
            t,
            p,
            w,
            rods,
            {r: list(ys) for r, ys in tr["figures"]["opponent"].items()},
            opening_done=rs.get("team") != "you" or bool(rs.get("opening_complete")),
        )
        sp = self.act_spec
        body = {r: {k: round(float(x), 5) for k, x in c.items()} for r, c in cmd.items()}
        for r, c in body.items():  # keep inside the documented ranges
            tr_, am = sp["slide_range_m"][r], sp["angle_range_rad"]
            c["slide"] = max(-tr_, min(tr_, c["slide"]))
            c["angle"] = max(-am, min(am, c["angle"]))
            c["omega"] = max(0.5, min(sp["max_angular_speed_rad_s"], c["omega"]))
            c["speed"] = max(0.05, min(sp["max_slide_speed_m_s"], c["speed"]))
        return {"type": "rods", "rods": body}
