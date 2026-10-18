"""The scripted fencer of format bout (fencing-7, the phrase-level sport): before each phrase it chooses its intention
from what it has seen of the bout (the intentions both fencers played and the results), never from the agent's choice
for this phrase. It knows the phrase table (phrases.Table.counts, the same counts as `game spec` phrase_table).

Two levels (docs/screening/fencing.md, section 6 "Phrase-level construction" and "fencing-7"): level 1 chosen in step 4
of the screening on tables measured before it was frozen and checked on a table measured after (the design and the
check: docs/screening/fencing/phrase/game.py, the same classes); level 2 redesigned on the exact table on 2026-10-14,
because the first level 2 was beaten far more often than level 1 by a reader that models how it reads, then set to the
option the maintainers chose (Chi, 2026-10-14): checked on fresh seeds against the reference, the pattern reader, the
equilibrium mix and the simple programs (docs/screening/fencing/phrase/levels/):
  level 1  a reader with a fixed library of simple models of the agent (its whole-bout mix, its recent mix, it repeats
           its last intention, it answers my last one, it copies my last one, it plays what just won, it goes round the
           menu); it believes the model with the best recent prediction score and plays the best answer to it, but
           in 70 % of the phrases it plays its habit instead (the best answer to the agent's whole-bout mix, with a
           prior of 3 per intention): a slow, readable tendency
  level 2  a reader of the agent that also models how the agent reads it (class Mind): five predictors of the agent's
           next intention (its mix; after its last one; after its last two; after my last one; after the last pair)
           and five hypotheses that the agent predicts MY next intention from my patterns and answers it; the
           hypothesis with the best recent prediction score is answered (logit 20 per net touch), and in 10 % of the
           phrases a draw from the table's equilibrium mix
Its random draws come from its own stream (the seed), so a bout replays exactly."""
from __future__ import annotations

import math

import numpy as np

PRIOR = 1.0                      # the table's counts + PRIOR per outcome: the expected net touches the players use
LEVELS = {
    1: dict(family="models", h=0.7, habit_prior=3.0,
            desc="model reader, 70% habit (whole-bout best answer, prior 3)"),
    2: dict(family="mind", beta=20.0, eps_eq=0.1,
            desc="reads your patterns and how you read it (logit 20), 10% equilibrium"),
}


def solve_zero_sum(M, max_iter=10000):
    """Equilibrium of the zero-sum game where the row player maximises x' M y. Simplex on the column player's LP
    (max 1'y' s.t. (M + c) y' <= 1, y' >= 0, with M + c > 0), Bland's rule; the row player's mix from the duals.
    Returns (value, x, y)."""
    M = np.asarray(M, float)
    m, n = M.shape
    c = 1.0 - M.min()
    A = M + c
    T = np.zeros((m + 1, n + m + 1))
    T[:m, :n] = A
    T[:m, n:n + m] = np.eye(m)
    T[:m, -1] = 1.0
    T[m, :n] = -1.0
    basis = list(range(n, n + m))
    for _ in range(max_iter):
        neg = np.flatnonzero(T[m, :-1] < -1e-12)
        if len(neg) == 0:
            break
        col = int(neg[0])
        colv = T[:m, col]
        pos = colv > 1e-12
        ratios = np.full(m, np.inf)
        ratios[pos] = T[:m, -1][pos] / colv[pos]
        rmin = ratios.min()
        ties = np.flatnonzero(ratios <= rmin + 1e-12)
        r = int(min(ties, key=lambda k: basis[k]))
        T[r] /= T[r, col]
        for k in range(m + 1):
            if k != r and T[k, col] != 0.0:
                T[k] -= T[k, col] * T[r]
        basis[r] = col
    else:
        raise RuntimeError("simplex did not converge")
    z = T[m, -1]
    yp = np.zeros(n)
    for r, b in enumerate(basis):
        if b < n:
            yp[b] = T[r, -1]
    xp = np.clip(T[m, n:n + m], 0.0, None)
    x, y = xp / xp.sum(), yp / yp.sum()
    return float(1.0 / z - c), x, y


class Knowledge:
    """the table as the players use it: P[i, j] = (counts + PRIOR) / (total + 4 PRIOR) over [me, other, double, none];
    T[i, j] = P(I touch alone) - P(the other touches alone): my expected net touches per phrase; x, y: its equilibrium"""

    def __init__(self, counts, prior=PRIOR):
        C = np.asarray(counts, float)
        self.n = C.shape[0]
        self.P = (C + prior) / (C.sum(-1, keepdims=True) + 4 * prior)
        self.T = self.P[..., 0] - self.P[..., 1]
        self.v, self.x, self.y = solve_zero_sum(self.T)


def sample(p, rng):
    return int(min(np.searchsorted(np.cumsum(p), rng.random(), side="right"), len(p) - 1))


class Policy:
    """one fencer's decision program from its own seat: P[mine, other] = its expected net touches per phrase.
    observe(mine, other, res): res 1 = I scored alone, -1 = the other alone, 2 = double (also annulled), 0 = nothing"""

    def __init__(self, name, desc=""):
        self.name, self.desc = name, desc

    def reset(self, kn, side, rng):
        self.side, self.rng = side, rng
        self.P = kn.T if side == 0 else -kn.T.T
        self.eq = kn.x if side == 0 else kn.y
        self.n = kn.n
        self.hist = []
        self.t = 0

    def observe(self, mine, other, res):
        self.hist.append((mine, other, res))
        self.t += 1


class Context(Policy):
    """pattern prediction: five predictors of the other's next intention (its overall mix; after its last one; after
    its last two; after my last one; after the last pair), each a table of decayed counts; the predictor with the best
    recent log-score is used; then the best answer to the prediction (logit beta), and with probability eps_eq a draw
    from the equilibrium mix instead (so it cannot be read in turn)"""
    CONTEXTS = ("m", "o1", "o2", "me1", "pair")

    def __init__(self, name, desc="", beta=20.0, eps_eq=0.25, decay=0.9, prior=0.3, score_decay=0.8):
        super().__init__(name, desc)
        self.beta, self.eps_eq, self.decay, self.prior, self.score_decay = beta, eps_eq, decay, prior, score_decay

    def reset(self, kn, side, rng):
        super().reset(kn, side, rng)
        self.tabs = {c: {} for c in self.CONTEXTS}
        self.score = {c: 0.0 for c in self.CONTEXTS}
        self._keys, self._preds = {}, {}

    def _key(self, c):
        h = self.hist
        if c == "m":
            return 0
        if not h:
            return None
        if c == "o1":
            return h[-1][1]
        if c == "o2":
            return (h[-2][1], h[-1][1]) if len(h) >= 2 else None
        if c == "me1":
            return h[-1][0]
        return (h[-1][1], h[-1][0])

    def _pred(self, c, key):
        t = self.tabs[c].get(key) if key is not None else None
        if t is None:
            return None
        p = t + self.prior
        return p / p.sum()

    def dist(self):
        self._keys = {c: self._key(c) for c in self.CONTEXTS}
        marg = self._pred("m", 0)
        if marg is None:
            marg = np.full(self.n, 1.0 / self.n)
        self._preds = {"m": marg}
        best, bs = "m", self.score["m"]
        for c in self.CONTEXTS[1:]:
            p = self._pred(c, self._keys[c])
            self._preds[c] = marg if p is None else p
            if p is not None and self.score[c] > bs + 1e-12:
                best, bs = c, self.score[c]
        v = self.P @ self._preds[best]
        if self.beta is None:
            core = (v >= v.max() - 1e-9).astype(float)
        else:
            core = np.exp(self.beta * (v - v.max()))
        core /= core.sum()
        return self.eps_eq * self.eq + (1.0 - self.eps_eq) * core

    def choose(self, score):
        return sample(self.dist(), self.rng)

    def observe(self, mine, other, res):
        for c, p in self._preds.items():
            self.score[c] = self.score_decay * self.score[c] + math.log(p[other])
        super().observe(mine, other, res)
        for c, key in self._keys.items():
            if key is None:
                continue
            t = self.tabs[c].get(key)
            if t is None:
                t = self.tabs[c][key] = np.zeros(self.n)
            t *= self.decay
            t[other] += 1.0


class Mind(Context):
    """pattern prediction (Context) plus five hypotheses that the other reads ME: it predicts my next intention from my
    patterns (my mix; after my last one; after my last two; after its last one; after the last pair) and answers that
    prediction (logit beta_o, eps_o spread); every hypothesis is scored by how well it predicted the other's choices,
    the best one is answered (logit beta), and with probability eps_eq a draw from the equilibrium mix instead. The
    same reader as the reference (builtin_players.MindReader), from this fencer's seat."""
    MINE = ("m", "me1", "me2", "o1", "pair")

    def __init__(self, name, desc="", beta=20.0, eps_eq=0.1, beta_o=40.0, eps_o=0.05, **k):
        super().__init__(name, desc, beta=beta, eps_eq=eps_eq, **k)
        self.beta_o, self.eps_o = beta_o, eps_o

    def reset(self, kn, side, rng):
        super().reset(kn, side, rng)
        self.mtabs = {c: {} for c in self.MINE}
        for c in self.MINE:
            self.score["tom_" + c] = 0.0
        self._mkeys = {}

    def _mkey(self, c):
        h = self.hist
        if c == "m":
            return 0
        if not h:
            return None
        if c == "me1":
            return h[-1][0]
        if c == "me2":
            return (h[-2][0], h[-1][0]) if len(h) >= 2 else None
        if c == "o1":
            return h[-1][1]
        return (h[-1][0], h[-1][1])

    def dist(self):
        self._keys = {c: self._key(c) for c in self.CONTEXTS}
        self._mkeys = {c: self._mkey(c) for c in self.MINE}
        marg = self._pred("m", 0)
        if marg is None:
            marg = np.full(self.n, 1.0 / self.n)
        self._preds = {"m": marg}
        for c in self.CONTEXTS[1:]:
            p = self._pred(c, self._keys[c])
            self._preds[c] = marg if p is None else p
        mmarg = self.mtabs["m"].get(0)
        for c in self.MINE:
            t = self.mtabs[c].get(self._mkeys[c]) if self._mkeys[c] is not None else None
            if t is None:
                t = mmarg
            q = np.full(self.n, 1.0 / self.n) if t is None else (t + self.prior) / (t + self.prior).sum()
            v = -self.P.T @ q                         # the other's net per intention against my predicted mix
            a = np.exp(self.beta_o * (v - v.max()))
            a /= a.sum()
            self._preds["tom_" + c] = self.eps_o / self.n + (1 - self.eps_o) * a
        best = max(self._preds, key=lambda c: (self.score[c], c == "m"))
        v = self.P @ self._preds[best]
        core = np.exp(self.beta * (v - v.max()))
        core /= core.sum()
        return self.eps_eq * self.eq + (1.0 - self.eps_eq) * core

    def observe(self, mine, other, res):
        for c, key in self._mkeys.items():
            if key is None:
                continue
            t = self.mtabs[c].get(key)
            if t is None:
                t = self.mtabs[c][key] = np.zeros(self.n)
            t *= self.decay
            t[mine] += 1.0
        super().observe(mine, other, res)


class Models(Policy):
    """a reader with a fixed library of simple models of the other fencer, each predicting its next intention:
      marg   its whole-bout mix                     recent its recency-weighted mix (0.7)
      repeat it repeats its last intention         counter it answers my last intention with the table's best answer
      copy   it copies my last intention           winner it plays what won the last phrase (whoever played it)
      seq    it continues its last step through the menu (a cycle)
    each model's prediction is 80 % its guess, 20 % spread (marg and recent as they are); the model with the best
    recent log-score (decay `score_decay`) is believed; the answer is the best (or logit beta) against it.
    habit: with probability h it plays its habit instead, the best answer to the other's whole-bout mix with a strong
    prior (`habit_prior` per intention): a slow, readable tendency. eps_eq: a draw from the equilibrium mix."""
    ALL = ("marg", "recent", "repeat", "counter", "copy", "winner", "seq")

    def __init__(self, name, desc="", models=ALL, h=0.0, habit_prior=3.0, eps_eq=0.0, beta=None, score_decay=0.7):
        super().__init__(name, desc)
        self.models, self.h, self.habit_prior, self.eps_eq, self.beta = tuple(models), h, habit_prior, eps_eq, beta
        self.score_decay = score_decay

    def reset(self, kn, side, rng):
        super().reset(kn, side, rng)
        self.wall = np.zeros(self.n)
        self.wrec = np.zeros(self.n)
        self.score = {m: 0.0 for m in self.models}
        self._preds = {}
        Q = -self.P.T                                      # Q[a, k]: the other's net when it plays a against my k
        self.other_brs = [np.flatnonzero(Q[:, k] >= Q[:, k].max() - 1e-9) for k in range(self.n)]

    def _point(self, k):
        """80 % on k (or spread over the tied set k), 20 % spread"""
        p = np.full(self.n, 0.2 / self.n)
        if np.ndim(k):
            p[k] += 0.8 / len(k)
        else:
            p[k] += 0.8
        return p

    def _predict(self):
        h, n = self.hist, self.n
        out = {}
        for m in self.models:
            if m == "marg":
                p = self.wall + 0.5
                out[m] = p / p.sum()
            elif m == "recent":
                p = self.wrec + 0.3
                out[m] = p / p.sum()
            elif not h:
                continue
            elif m == "repeat":
                out[m] = self._point(h[-1][1])
            elif m == "counter":
                out[m] = self._point(self.other_brs[h[-1][0]])
            elif m == "copy":
                out[m] = self._point(h[-1][0])
            elif m == "winner":
                mine, other, res = h[-1]
                out[m] = self._point(mine if res == -1 else other)
            elif m == "seq" and len(h) >= 2:
                out[m] = self._point((2 * h[-1][1] - h[-2][1]) % n)
        return out

    def dist(self):
        self._preds = self._predict()
        best = max(self._preds, key=lambda m: (self.score[m], m == "marg"))
        v = self.P @ self._preds[best]
        if self.beta is None:
            core = (v >= v.max() - 1e-9).astype(float)
        else:
            core = np.exp(self.beta * (v - v.max()))
        core /= core.sum()
        hp = self.wall + self.habit_prior
        hv = self.P @ (hp / hp.sum())
        habit = (hv >= hv.max() - 1e-9).astype(float)
        habit /= habit.sum()
        return self.h * habit + self.eps_eq * self.eq + (1.0 - self.h - self.eps_eq) * core

    def choose(self, score):
        return sample(self.dist(), self.rng)

    def observe(self, mine, other, res):
        for m, p in self._preds.items():
            self.score[m] = self.score_decay * self.score[m] + math.log(p[other])
        super().observe(mine, other, res)
        self.wall[other] += 1.0
        self.wrec *= 0.7
        self.wrec[other] += 1.0


def make_level(level):
    s = dict(LEVELS[level])
    fam, desc = s.pop("family"), s.pop("desc")
    return {"models": Models, "ctx": Context, "mind": Mind}[fam](f"level {level}", desc, **s)


class Opponent:
    """the scripted fencer at a level, the second fencer (side 1) of the bout"""

    def __init__(self, level, seed, kn):
        self.level = int(level)
        self.p = make_level(self.level)
        self.p.reset(kn, 1, np.random.default_rng([int(seed), 13]))

    def choose(self, score):
        return self.p.choose(score)

    def observe(self, mine, other, res):
        self.p.observe(mine, other, res)

    def state(self):
        return dict(level=self.level, hist=self.p.hist, rng=self.p.rng.bit_generator.state)
