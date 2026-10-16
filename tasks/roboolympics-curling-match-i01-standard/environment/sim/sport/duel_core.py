"""Two-player curling (program play duel): the single-player match rules (curling.py) with two agents instead of the
scripted team.

  * Seat A throws the yellow stones (team 0), seat B the red ones (team 1). 4 ends of 5 stones per team; while tied,
    extra ends until a team scores, at most 3; a tie after them goes to the player with more chess-clock time left.
    Free guard zone (five-rock rule) as in curling.py.
  * FIRST_PLAYER throws the first stone of end 1, so the other player has the hammer (the last stone) in end 1.
    Afterwards the team that scored throws first in the next end; a blank end keeps the hammer.
  * Each player's execution error is its own seeded stream: the n-th stone of a team in an end draws
    (DUEL_SEED, end, stream, n), stream 1 for the player who throws the first stone of end 1 (FIRST, after the coin
    toss) and 2 for the other. The duel is a pair of matches on the same seed with the first player swapped, so the
    two players swap the streams and meet the same draws over the pair (revision duel-turn-3, 2026-10-08; until
    duel-turn-2 the n-th stone of each team drew the same error, which the team throwing later could pre-compensate).
  * The ice's deceleration scale kd (curling-3, hidden from both players) is the same for both seats and both matches
    of a pair (plugin.ice_kd draws it from the seed).
The match is a pure function of the seed, the first player, kd and the sequence of throws (deterministic replay).
"""
from __future__ import annotations

import hashlib
import json

import numpy as np

import curling as C

SIDES = ("A", "B")
OTHER = {"A": "B", "B": "A"}
TEAM = {"A": 0, "B": 1}
REVISION = "duel-turn-3"


class Duel(C.Match):
    def __init__(self, seed: int, first: str, kd: float = 1.0):
        assert first in SIDES
        super().__init__(1, kd)
        self.L["seed"] = int(seed)
        self.seed, self.first = int(seed), first
        self.hammer = 1 - TEAM[first]        # the team without the hammer throws first
        self.shots = []

    def noise_stream(self, team: int) -> int:
        """The seat's execution-noise stream: 1 for the first player (FIRST), 2 for the other (the pair swaps them)."""
        return 1 if SIDES[team] == self.first else 2

    def _noise(self, team: int):
        if getattr(self, "noiseless", False):       # planning copies only (as curling.Match._noise)
            return 0.0, 0.0
        # each player its own stream (the first player's 1, the other's 2): the opponent's errors say nothing of yours
        rng = np.random.default_rng([self.seed, self.end, self.noise_stream(team), C.N_STONES - self.stones_left(team)])
        z = rng.standard_normal(2)
        return float(z[0] * C.PLAYER_NOISE["speed"]), float(z[1] * C.PLAYER_NOISE["angle_deg"])

    @property
    def turn(self) -> str:
        return SIDES[self.thrower()]

    @property
    def winner(self):
        t = self.winner_team
        return None if t is None else SIDES[t]

    def resolve_tie(self, seat: str, clock_left_s: dict) -> None:
        """The chess clocks decide a tie after the last extra end (server_duel.py)."""
        self.resolve_tiebreak(SIDES.index(seat), [clock_left_s["A"], clock_left_s["B"]])

    @property
    def score_by_seat(self) -> dict:
        return {"A": self.score[0], "B": self.score[1]}

    def play(self, seat: str, dec: dict) -> dict:
        assert not self.done and seat == self.turn
        self.decisions.append({"seat": seat, "type": "throw", "v": dec["v"], "angle": dec["angle"], "spin": dec["spin"]})
        n_ends = len(self.ends)
        rec = self._throw(TEAM[seat], dec["v"], dec["angle"], dec["spin"], {"seat": seat})
        rec = dict(rec, end_finished=self.ends[-1] if len(self.ends) > n_ends else None)
        self.shots.append(rec)
        return rec

    def replay(self, decisions: list[dict]) -> None:
        for d in decisions:
            if self.done:
                break
            self.play(d["seat"], d)

    def state_sha(self) -> str:
        blob = json.dumps({"score": self.score, "log": self.log, "ends": self.ends, "done": self.done,
                           "hammer": self.hammer, "tiebreak": getattr(self, "tiebreak", None), "kd": self.kd,
                           "stones": [[s["id"], s["x"], s["y"]] for s in self.sheet.stones]},
                          sort_keys=True, default=float)
        return hashlib.sha256(blob.encode()).hexdigest()


def render_video(seed: int, first: str, decisions: list[dict], path: str, fps: int = 10) -> None:
    """Replay video of a recorded duel (1 s of simulated time per frame)."""
    import imageio.v2 as imageio
    import render
    rd = render.Renderer()
    w = imageio.get_writer(path, fps=fps, codec="libx264", quality=7, macro_block_size=4)
    who = {0: "A (yellow)", 1: "B (red)"}

    def cb(frames, rec, m):
        if frames is None:
            msg = "blank end" if rec["team"] < 0 else f"{who[rec['team']]} scores {rec['points']}"
            for _ in range(fps * 2):
                w.append_data(rd.video_frame(f"End {rec['end_over'] + 1} over: {msg}   |   A {m.score[0]} - {m.score[1]} B"))
            return
        ban = (f"End {rec['end'] + 1}  throw {rec['k'] + 1}/{2 * C.N_STONES}  {who[rec['team']]}  v={rec['v']:.3f} m/s  "
               f"angle={rec['angle']:+.3f} deg  {rec['spin']}   |   A {m.score[0]} - {m.score[1]} B")
        for _t, st in frames:
            rd.set_stones(st)
            w.append_data(rd.video_frame(ban))
        for _ in range(fps // 2):
            w.append_data(rd.video_frame(ban))

    rd.set_stones([])
    for _ in range(fps):
        w.append_data(rd.video_frame(f"Curling duel: A (yellow) vs B (red), first player {first}"))
    m = Duel(seed, first)
    m.frames_cb = cb
    m.replay(decisions)
    w.close()
