"""The world of the phrase-level sport (fencing-7): every phrase of the bout is one of the phrases measured in the
fencing-6 world, looked up in a table.

A phrase starts with both fencers on guard GAP_M apart (pelvis to pelvis). Each fencer has chosen one intention
(INTENTIONS), a fixed skill on the robot: the Unitree G1 of the robot library with its epee, its legs, waist and
left arm driven by NVIDIA's SONIC whole-body policy tracking our own fencing motions (en garde, steps, lunge), its
sword arm by the point skill. Each fencer starts its intention after a delay of 0, 10, ... 50 ms (JITTER_STEPS control
steps, drawn for each phrase from the seed); the phrase ends at the first touch (the electric apparatus and the
45 ms lockout of fencing-6's phrase referee) or after MAX_S without one. In that world a phrase's outcome is a function
of the two intentions and the two delays alone (every phrase measured more than once gave the same result at the same
step), so the 9 x 9 x 6 x 6 = 2916 phrases were each played once (docs/screening/fencing/phrase/: the generator, the
determinism check) and the bout replays them from phrases/table.json.

The two ends of the piste are not exactly alike in the simulation (the same phrase fenced from the other end ends
differently in about one case in seven), so each phrase also draws the end each fencer fences from: the first fencer
(seat A in format bout, the first player in format duel) is on the table's end A with probability 1/2. Both fencers
therefore meet the same chances, and a fencer's chances against an intention are the table's counts over both ends
(Table.counts: out of 2 x 36 phrases).

phrases/frames.npz keeps two frames of every phrase (the joint positions half-way and at the end) for the cameras."""
from __future__ import annotations

import hashlib
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "phrases")
INTENTIONS = ("lunge", "low", "line", "rline", "stop", "counter", "delay", "retreat", "draw")
OUTCOMES = ("A", "B", "AB", "none")      # the table's ends: a touch for A alone, for B alone, a double, none
STEP_S = 0.01                            # the control step: a delay step, the halt step k


class Table:
    """phrases/table.json: {"intentions", "gap_m", "jitter_steps", "max_s", "source", "phrases": [[a, b, dA, dB, res,
    k, why], ...]} (k: the control step of the halt, null for a phrase cut at max_s)"""

    def __init__(self, path=DATA):
        with open(os.path.join(path, "table.json"), "rb") as f:
            raw = f.read()
        self.sha = hashlib.sha256(raw).hexdigest()
        d = json.loads(raw)
        self.names = tuple(d["intentions"])
        if self.names != INTENTIONS:
            raise ValueError(f"table intentions {self.names} != {INTENTIONS}")
        self.idx = {s: i for i, s in enumerate(self.names)}
        self.J = int(d["jitter_steps"])
        self.gap_m, self.max_s = float(d["gap_m"]), float(d["max_s"])
        self.meta = {k: d[k] for k in ("gap_m", "jitter_steps", "max_s", "source") if k in d}
        self.row: dict = {}
        for n, (a, b, dA, dB, res, k, why) in enumerate(d["phrases"]):
            self.row[(a, b, int(dA), int(dB))] = (n, res, k, why)
        want = len(self.names) ** 2 * self.J ** 2
        if len(self.row) != want or any(r[1] not in OUTCOMES for r in self.row.values()):
            raise ValueError(f"table has {len(self.row)} phrases, needs {want} with outcomes in {OUTCOMES}")
        self.path = path
        self._frames = None

    def seconds(self, k):
        return self.max_s if k is None else (k + 1) * STEP_S

    def get(self, a, b, dA, dB):
        """the phrase with A's intention a after dA steps and B's b after dB: {res, k, why, s, row}"""
        n, res, k, why = self.row[(a, b, dA, dB)]
        return dict(res=res, k=k, why=why, s=round(self.seconds(k), 2), row=n)

    def counts(self):
        """C[i, j] = [touches for me alone, for the other alone, doubles, none] when I play i and the other j, over
        both ends and all delays (2 J^2 phrases)"""
        n = len(self.names)
        C = np.zeros((n, n, 4))
        for (a, b, _, _), (_, res, _, _) in self.row.items():
            i, j, o = self.idx[a], self.idx[b], OUTCOMES.index(res)
            C[i, j, o] += 1                                  # I am on end A
            C[j, i, (1, 0, 2, 3)[o]] += 1                    # I am on end B: A's touch is the other's
        return C

    def frames(self, row):
        """(steps [2], qpos [2, nq]) of the phrase's two frames (half-way, the end), on the table's ends"""
        if self._frames is None:
            z = np.load(os.path.join(self.path, "frames.npz"))
            self._frames = (z["steps"], z["qpos"], z["guard"])
        return self._frames[0][row], self._frames[1][row]

    def guard_qpos(self):
        """both fencers on guard GAP_M apart, before the first phrase"""
        self.frames(0)
        return self._frames[2]


_TABLE: dict = {}


def table(path=DATA) -> Table:
    if path not in _TABLE:
        _TABLE[path] = Table(path)
    return _TABLE[path]


def draw(seed, n, J):
    """phrase n's chance: (the first fencer's delay, the second's, the first on the table's end A)"""
    g = np.random.default_rng([int(seed), 21, int(n)])
    d = g.integers(0, J, 2)
    return int(d[0]), int(d[1]), bool(g.random() < 0.5)


def play(t: Table, i_first, i_second, seed, n):
    """phrase n with the first fencer's intention i_first and the second's i_second (names): the table's phrase with
    this phrase's delays and ends; res from the first fencer's view: 'first' | 'second' | 'double' | 'none'"""
    d1, d2, first_on_a = draw(seed, n, t.J)
    if first_on_a:
        p = t.get(i_first, i_second, d1, d2)
        res = {"A": "first", "B": "second", "AB": "double", "none": "none"}[p["res"]]
    else:
        p = t.get(i_second, i_first, d2, d1)
        res = {"A": "second", "B": "first", "AB": "double", "none": "none"}[p["res"]]
    return dict(res=res, k=p["k"], why=p["why"], s=p["s"], row=p["row"], first_delay_ms=10 * d1,
                second_delay_ms=10 * d2, first_end="A" if first_on_a else "B")
