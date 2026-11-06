"""fencing (epee) on the v0.2 framework, the phrase-level sport since fencing-7 (the owner's decision of 2026-10-13):
the four groups of contract ② (core/sport.py) around the phrase table (phrases.py), the bout referee (bout.py) and the
scripted fencer (opponent.py).

  world + referee  FencingMatch: turn protocol, one action = one fencer's intention for the next phrase. Format bout:
                   seat A's intention; the scripted fencer (side B) chooses its own from what it has seen of the bout
                   (never from A's choice), the phrase is played (phrases.play: the measured phrase with this phrase's
                   delays and ends, drawn from the seed) and judged (bout.Bout.phrase), all inside apply. Format duel:
                   the first player's intention is kept hidden, the other player's completes the phrase. The state
                   digest covers the bout, the hidden intention, the scripted fencer and the table.
  actions          one low level: phrase {intention} (sport.toml [modes]: the intention is the robot's whole command
                   for a phrase, as a release command in the other turn sports)
  observation      observe = the score, the clocks, the cards and every phrase so far from the seat's view (both
                   intentions, both delays, the result); camera_job = the 2 x 2 tile image of the last phrase
                   (cameras.py, drawn in the seat's render worker)
"""
from __future__ import annotations

import hashlib
import json
import os

import bout as BT
import cameras as CAM
import fencing as F
import opponent as OP
import phrases as PH
from core.sport import FINISHED, PLAYING, MatchBase, Phase, SchemaLayer

HERE = os.path.dirname(os.path.abspath(__file__))
REVISION = "fencing-7+core-0.2"
OPPONENT = "B"                        # the scripted fencer's side in format bout (it has no seat)
TIEBREAKS = ("touches", "passivity", "time", "deciding_touch", "priority")
INTENTION_DOC = {
    "lunge": "a lunge with the point at the opponent's chest",
    "low": "a lunge with the point at the opponent's front knee",
    "line": "the point in line at the opponent's chest, held",
    "rline": "on guard; the point raised into line when the opponent comes (its pelvis coming faster than 0.2 x the "
             "distance per second)",
    "stop": "on guard; a stop-hit at the opponent's sword hand when it comes within reach",
    "counter": "waits; when the opponent comes (its pelvis faster than 0.15 m/s towards you), a lunge at its chest",
    "delay": "a lunge at the opponent's chest 0.4 s late (after the opponent has shown its intention)",
    "retreat": "steps back for the whole phrase",
    "draw": "a short advance (0.3 s, one 0.15 m step) to draw the opponent's attack, then a lunge at its chest when it "
            "comes, as counter",
}
SCHEMA = {"phrase": {"intention": {"type": "enum", "values": list(PH.INTENTIONS),
                                   "doc": "your intention for the next phrase (`game spec` intentions)"}}}
RESULT_VIEW = {"double": "double", "none": "none"}


def _res_code(res, me):
    """the decision programs' result code (opponent.Policy.observe): 1 = I scored alone, -1 = the other, 2 = double
    (also an annulled one), 0 = nothing"""
    return 2 if res == "double" else 0 if res == "none" else (1 if res == me else -1)


class FencingMatch(MatchBase):
    def __init__(self, cfg):
        self.cfg = cfg
        self.table = PH.table()
        self.kn = OP.Knowledge(self.table.counts())
        self.single = len(cfg.side_list()) == 1
        self.level = self.opp = None
        if self.single:
            self.level = 1 if cfg.level is None else int(cfg.level)
            if self.level not in OP.LEVELS:
                raise ValueError(f"opponent level must be one of {sorted(OP.LEVELS)}")
            self.first, self.second = cfg.seats[0], OPPONENT
            self.opp = OP.Opponent(self.level, cfg.seed, self.kn)
        else:
            self.first = cfg.first if cfg.first in cfg.seats else cfg.seats[0]
            self.second = next(s for s in cfg.seats if s != self.first)
        self.bout = BT.Bout(cfg.seed, self.first, self.second)
        self.pending: dict = {}                       # format duel: the first player's hidden intention
        self.k = 0

    def other(self, side):
        return self.second if side == self.first else self.first

    # ---------------------------------------------------------------- world + referee
    def _phrase(self, choices):
        b = self.bout
        n = len(b.log)
        p = PH.play(self.table, choices[self.first], choices[self.second], self.cfg.seed, n)
        res = {"first": self.first, "second": self.second}.get(p["res"], p["res"])
        info = dict(intentions={self.first: choices[self.first], self.second: choices[self.second]},
                    delays_ms={self.first: p["first_delay_ms"], self.second: p["second_delay_ms"]},
                    ends={self.first: p["first_end"], self.second: "B" if p["first_end"] == "A" else "A"},
                    why=p["why"], k=p["k"], row=p["row"])
        rec = b.phrase(res, p["s"], info)
        if self.opp is not None:
            idx = self.table.idx
            self.opp.observe(idx[choices[OPPONENT]], idx[choices[self.first]], _res_code(rec["res"], OPPONENT))
        return rec

    def apply(self, seat, cmd):
        i = cmd["intention"]
        self.k += 1
        if self.single:
            sc = self.bout.score
            j = self.table.names[self.opp.choose((sc[OPPONENT], sc[seat]))]
            rec = self._phrase({seat: i, OPPONENT: j})
            return self._result(seat, rec)
        self.pending[seat] = i
        if len(self.pending) < 2:
            return {"committed": i, "phrase": len(self.bout.log) + 1,
                    "note": "kept hidden until the other fencer has chosen; the phrase is fenced then"}
        choices, self.pending = self.pending, {}
        rec = self._phrase(choices)
        return self._result(seat, rec)

    def _result(self, seat, rec):
        v = self._phrase_view(rec, seat)
        return {"phrase": v["n"], "you": v["you"], "opponent": v["opponent"], "result": v["result"],
                "score": v["score_after"], "bout_over": self.bout.over}

    def forfeit(self, seat, why):
        self.bout.forfeit(self.cfg.side_of(seat), why)
        return True

    def to_move(self):
        if self.bout.over:
            return None
        if self.single:
            return self.cfg.seats[0]
        return self.first if self.first not in self.pending else self.second

    def phase(self):
        return Phase(FINISHED, reason=self.bout.how or "bout_over") if self.bout.over else Phase(PLAYING)

    def unit(self):
        return len(self.bout.log)

    def scores(self):
        return dict(self.bout.score)

    def tiebreaks(self):
        """FIE t.38 and t.124 as bout.py decides it: 15 touches; the P-black card for unwillingness to fight; at time
        the fencer ahead; the deciding touch of the extra minute; the priority drawn by lot before it (the last rule
        always decides)."""
        rules = [(n, (lambda m, n=n: m.bout.winner if m.bout.how == n else None)) for n in TIEBREAKS[:-1]]
        return rules + [(TIEBREAKS[-1], lambda m: m.bout.winner)]

    def state_digest(self):
        st = dict(bout=self.bout.state(), pending=self.pending, k=self.k, table=self.table.sha,
                  opp=None if self.opp is None else self.opp.state())
        return hashlib.sha256(json.dumps(st, sort_keys=True, default=str).encode()).hexdigest()

    # ---------------------------------------------------------------- actions
    def schema(self, seat):
        return SCHEMA

    # ---------------------------------------------------------------- observation
    def _phrase_view(self, r, seat):
        me = self.cfg.side_of(seat)
        ot = self.other(me)
        res = r["res"]
        result = "you" if res == me else "opponent" if res == ot else res
        if r.get("annulled"):
            result = "double, not counted at 14-14"
        out = {"n": r["n"], "you": r["intentions"][me], "opponent": r["intentions"][ot], "result": result,
               "seconds": r["s"], "your_delay_ms": r["delays_ms"][me], "opponent_delay_ms": r["delays_ms"][ot],
               "score_after": {"you": r["score"][me], "opponent": r["score"][ot]}}
        if r.get("cut_by_clock"):
            out["cut_by_clock"] = True
        if r.get("card"):
            out["card"] = r["card"] if r["card"] != "P-black" else \
                f"P-black to {'you' if r['black'] == me else 'the opponent'}"
        if r.get("extra_minute_starts"):
            out["extra_minute_starts"] = True
        return out

    def observe(self, seat, query=None):
        b, me = self.bout, self.cfg.side_of(seat)
        ot = self.other(me)
        out = {"score": {"you": b.score[me], "opponent": b.score[ot]}, "phrase": len(b.log) + 1,
               "fencing_time_s": round(b.t, 2), "time_left_s": b.time_left_s(), "extra_minute": b.extra,
               "priority": None if b.priority is None else ("you" if b.priority == me else "opponent"),
               "passivity": {"no_hit_s": b.no_hit_s(), "limit_s": BT.PASSIVE_S, "p_cards": b.p_calls},
               "phrases": [self._phrase_view(r, seat) for r in b.log]}
        if not self.single:
            out["committed"] = self.pending.get(me)
        return out

    def _snaps(self, seat):
        if not self.bout.log:
            q = self.table.guard_qpos()
            return [dict(label="on guard", qpos=q), dict(label="on guard", qpos=q)]
        r = self.bout.log[-1]
        steps, qs = self.table.frames(r["row"])
        seat_a = self.cfg.seats[0] if self.single else "A"
        turn = r["ends"].get(seat_a, "A") != "A"     # seat A's fencer fenced from the table's end B
        m = _scene_model()
        out = []
        for s, q, what in zip(steps, qs, ("half-way", "end")):
            q = CAM.half_turn(m, q) if turn else q
            out.append(dict(label=f"phrase {r['n']} {what}: {(int(s) + 1) * PH.STEP_S:.2f} s", qpos=q))
        return out

    def camera_job(self, seat):
        job = {"seat": seat, "snaps": self._snaps(seat)}
        return job, dict(image_layout=CAM.IMAGE_LAYOUT, phrase=len(self.bout.log))

    def render_state(self):
        return {"qpos": [float(x) for x in self._snaps(self.cfg.seats[0])[-1]["qpos"]]}

    def final_fields(self):
        b = self.bout
        out = {"phrases": b.log, "extra_minute": b.extra, "priority": b.priority, "how": b.how,
               "fencing_time_s": round(b.t, 2), "first_player": self.first, "p_cards": b.p_calls,
               "touches": b.T, "table_sha256": self.table.sha}
        if self.single:
            out["level"] = self.level
        return out


_MODEL: dict = {}


def _scene_model():
    if "m" not in _MODEL:
        import mujoco as mj
        _MODEL["m"] = mj.MjModel.from_xml_string(F.scene_xml())
    return _MODEL["m"]


_RENDER: dict = {}


class Fencing:
    name = "fencing"
    protocol = "turn"
    revision = REVISION
    source_dirs = [HERE]
    workers = ("render",)

    def build(self, cfg):
        return FencingMatch(cfg)

    def action_layer(self, level):
        if level != "low":
            raise ValueError("fencing-7 has the low level only (sport.toml [modes]): the intention for a phrase")
        return SchemaLayer()

    def worker_init(self, kind, seat, cfg):
        r = CAM.Renderer(seat)
        q = PH.table().guard_qpos()
        r.render([dict(label="on guard", qpos=q)] * CAM.N_FRAMES)      # the GL context before 'ready'
        return r

    def worker_call(self, obj, kind, job):
        if obj is None:                               # in-process (core/local.py): one renderer per seat
            obj = _RENDER.get(job["seat"]) or _RENDER.setdefault(job["seat"], CAM.Renderer(job["seat"]))
        return {"png": obj.render(job["snaps"])}

    def scene(self, cfg):
        from renderers.base import Scene
        return Scene(xml=F.scene_xml(), assets={})

    def spec(self, cfg, seat, match):
        t = PH.table()
        C = t.counts()
        names = t.names
        out = dict(
            cameras=CAM.cam_info(), image=CAM.IMAGE_LAYOUT,
            intentions={s: INTENTION_DOC[s] for s in names},
            phrase_table=dict(
                note=("your chances against each intention of the opponent: for each pair 'yours|theirs', the phrases "
                      f"out of {int(C[0, 0].sum())} (both ends of the piste x {t.J} x {t.J} start delays) that end "
                      "with a touch for you alone, for the opponent alone, a double, or no touch; every phrase draws "
                      "its delays and ends from the seed, the same for both fencers"),
                columns=["you", "opponent", "double", "none"],
                counts={f"{a}|{b}": [int(x) for x in C[i, j]] for i, a in enumerate(names)
                        for j, b in enumerate(names)}),
            phrase=dict(gap_m=t.gap_m, start_delay_ms=[0, 10 * (t.J - 1)], max_s=t.max_s,
                        source="measured in the fencing-6 world (docs/screening/fencing/phrase/)"),
            bout=dict(touches=BT.TOUCHES, time_s=BT.regulation_s(BT.TOUCHES), extra_minute_s=BT.EXTRA_S,
                      passivity_s=BT.PASSIVE_S))
        if len(cfg.side_list()) == 1:
            lv = int(cfg.level or 1)
            out["opponent"] = dict(level=lv, levels="1-2: level 2 is stronger",
                                   plays=("it chooses its intention before each phrase from what it has seen of the "
                                          "bout (both fencers' intentions and the results), never from yours for "
                                          "this phrase; it knows the phrase table"))
        else:
            out["first_player"] = cfg.first or "A"
        return out

    def players(self):
        import builtin_players as bp
        return {"reference": bp.Reference, "rival": bp.Rival, "random": bp.Random}


SPORT = Fencing()
