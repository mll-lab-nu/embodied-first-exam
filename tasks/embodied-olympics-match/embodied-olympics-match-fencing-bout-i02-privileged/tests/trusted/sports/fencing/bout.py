"""The referee of an epee direct-elimination bout fenced phrase by phrase (FIE Technical Rules, August 2026: t.22,
t.37, t.38, t.44, t.92, t.124), the phrase-level sport since fencing-7.

The bout is 15 touches or 9 minutes of fencing time (t.38.2: three periods of 3 minutes; deviation: one period of 9
minutes, no breaks). Each phrase (phrases.py) gives a touch for one fencer, a double or none, and takes its fencing time
(the time to the halt; 3 s for a phrase without a touch). A double scores for both (t.92), except at 14-14, where it is
not counted. When the clock ends during a phrase, the phrase ends without a touch (t.44.1). At time the fencer ahead
wins; at equal scores one more minute for a deciding touch, the priority drawn by lot before it; still equal after the
minute, the fencer with priority wins. Every phrase starts on guard (t.22).

Unwillingness to fight (t.124): one minute of fencing time without a hit -> 'Halt!'. The first time both fencers get a
P-red card, a penalty hit each; the second time the fencer with the lower score gets the P-black card and loses the
bout, at equal scores the one who loses a lot. No P-card at 14-14 (the minute restarts). The minute restarts after each
hit, double, annulled double and penalty hit, not after a phrase without a touch; t.124 does not apply in the extra
minute.

The lots are drawn from the seed for the first fencer (seat A in format bout, the first player in format duel), so a
duel with the seats and the first player swapped is the mirror image. The rules are the same as the step-4 model of
the screening (docs/screening/fencing/phrase/game.py, play_bout)."""
from __future__ import annotations

import hashlib
import json
import math

import numpy as np

BOUT_S, EXTRA_S, PASSIVE_S, TOUCHES = 180.0, 60.0, 60.0, 15


def regulation_s(touches):
    """3 minutes of fencing time per 5 touches: a pool bout (5) 3 minutes, a direct-elimination bout (15) 9"""
    return BOUT_S * math.ceil(touches / 5)


class Bout:
    def __init__(self, seed, first, second, touches=TOUCHES):
        self.seed, self.T = int(seed), int(touches)
        self.first, self.second = first, second
        self.reg_s = regulation_s(self.T)
        self.score = {first: 0, second: 0}
        self.t = 0.0                       # fencing time (s)
        self.minute0 = 0.0                 # t.124: the fencing time of the last hit
        self.extra = False
        self.priority = None
        self.p_calls = 0                   # 1: the P-red cards given, 2: the P-black card
        self.winner = self.how = None
        self.log: list[dict] = []

    @property
    def over(self):
        return self.winner is not None

    def limit_s(self):
        return self.reg_s + (EXTRA_S if self.extra else 0.0)

    def time_left_s(self):
        return round(max(0.0, self.limit_s() - self.t), 2)

    def no_hit_s(self):
        return None if self.extra else round(self.t - self.minute0, 2)

    def _lot(self, salt):
        """the first fencer wins a lot drawn from the seed (salt 38: the priority, 124: the P-black card)"""
        return self.first if np.random.default_rng([self.seed, salt]).random() < 0.5 else self.second

    def phrase(self, res, dur, info=None):
        """one phrase: res = the side that touched alone, 'double' or 'none'; dur = its fencing time (s); info: the
        phrase's own fields for the log. Returns the log record."""
        if self.over:
            raise RuntimeError("the bout is over")
        a, b = self.first, self.second
        rec = dict(n=len(self.log) + 1, **(info or {}), res=res, s=dur, t0=round(self.t, 2))
        if self.t + dur > self.limit_s() + 1e-9:          # t.44.1: the clock ends the phrase before its touch
            rec.update(cut_by_clock=True, res="none", res_phrase=res)
            res, self.t = "none", self.limit_s()
        else:
            self.t += dur
        awarded, annulled, card = [], False, None
        if res in (a, b):
            awarded = [res]
        elif res == "double":
            if self.score[a] == self.score[b] == self.T - 1:
                annulled = True                           # 14-14: the double is not counted
            else:
                awarded = [a, b]                          # t.92
        for s in awarded:
            self.score[s] += 1
        hit = bool(awarded or annulled)
        black = None
        if hit:
            self.minute0 = self.t                         # t.124.3.d
        elif not self.extra and self.t - self.minute0 >= PASSIVE_S - 1e-9:
            self.minute0 = self.t
            if self.score[a] == self.score[b] == self.T - 1:
                card = "none at 14-14"                    # t.124.3.a
            elif self.p_calls == 0:
                self.p_calls, card = 1, "P-red to both"   # a penalty hit each
                self.score[a] += 1
                self.score[b] += 1
                hit = True
            else:
                self.p_calls, card = 2, "P-black"
                if self.score[a] != self.score[b]:
                    black = a if self.score[a] < self.score[b] else b
                else:
                    black = self._lot(124)
        sa, sb = self.score[a], self.score[b]
        starts_extra = False
        time_up = self.t >= self.limit_s() - 1e-9
        if black is not None:
            self.winner, self.how = (b if black == a else a), "passivity"
        elif self.extra and sa != sb:
            self.winner, self.how = (a if sa > sb else b), "deciding_touch"
        elif not self.extra and max(sa, sb) >= self.T and sa != sb:
            self.winner, self.how = (a if sa > sb else b), "touches"
        elif time_up and not self.extra:
            if sa != sb:
                self.winner, self.how = (a if sa > sb else b), "time"
            else:
                self.extra, self.priority = True, self._lot(38)    # the extra minute, on guard (t.22.8)
                starts_extra = True
        elif time_up and self.extra:
            self.winner, self.how = self.priority, "priority"
        rec.update(awarded=awarded, annulled=annulled, card=card, black=black, t=round(self.t, 2),
                   score={a: sa, b: sb}, extra_minute_starts=starts_extra)
        self.log.append(rec)
        return rec

    def forfeit(self, side, why):
        """the core's decision (a chess clock run out, a session abandoned): `side` loses"""
        if not self.over:
            self.winner, self.how = (self.second if side == self.first else self.first), why

    def state(self):
        return dict(seed=self.seed, T=self.T, first=self.first, score=self.score, t=round(self.t, 6),
                    minute0=round(self.minute0, 6), extra=self.extra, priority=self.priority, p_calls=self.p_calls,
                    winner=self.winner, how=self.how, log=self.log)

    def state_sha(self):
        return hashlib.sha256(json.dumps(self.state(), sort_keys=True, default=str).encode()).hexdigest()
