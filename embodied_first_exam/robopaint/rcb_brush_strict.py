"""
rcb_brush_strict.py — RoboPaint's process rules on top of the picture score. The robot, the scene, the brush models, the target and
the picture score are those of rcb_brush.py and rcb_brush_score.py; this module only adds the rules and is used on the graders' side:
  - the privileged verifier (tests/grade.py replays with `python rcb_brush_strict.py replay ...`),
  - the privileged scoring service behind Session.score() (environment/scorer/, RCB_TOOL_MODULE=rcb_brush_strict),
  - the standard sim sidecar's collect hook (environment/sim/finalize.sh with RCB_TOOL=/srv/rcb_brush_strict.py).

Why: an agent can pass the picture score without writing or painting strokes, by setting one light press that draws a thin line
and filling the exemplar's area with long back-and-forth or contour paths (colouring in). The rules measure the strokes themselves.

Only inked (painted) strokes on the main sheet count; practice-sheet strokes are free. path_mm = the total length of the tip's path
while it presses on the main sheet (every physics sample). The rules (instance["target"]["success"], the same numbers as in the task
texts; a rule whose keys are absent is off):
  colouring in (calligraphy, lettering: max_path_mm + min_mark_width_mm): a run fails when path_mm > max_path_mm AND
                      mark_width_mm < min_mark_width_mm, where mark_width_mm = the area each stroke inks on its own (its own mark,
                      coverage >= 0.5; overlaps between different strokes count again) summed over the strokes / path_mm: the
                      average width of the marks. A long path with wide marks (strokes written over again) and thin marks on a
                      short path (a light hand) both pass; a long path of thin marks is colouring in.
  path budget (paintings: max_path_mm without min_mark_width_mm): path_mm <= max_path_mm.
  sweeps (paintings: max_scribble, max_scribble_share, scribble_min_mm): a stroke's scribble ratio = its length / the diagonal of
                      its bounding box (at least scribble_min_mm); scribble_share = the share of path_mm in strokes whose ratio
                      exceeds max_scribble (zigzags, back-and-forth fills, spirals, loops) must be <= max_scribble_share.
  strokes counted (calligraphy, 2026-10-14: stroke_gap_mm, mark_min_width_mm, max_stroke_path_mm): the stroke cap
                      (target.success max_strokes) counts strokes, not contacts. A contact is cut into two strokes wherever
                      the brush moves more than stroke_gap_mm along the sheet without marking it (its mark narrower than
                      mark_min_width_mm: a press too light to ink, which joined separately written pieces into one contact),
                      and a stroke longer than max_stroke_path_mm counts as ceil(length / max_stroke_path_mm) strokes (one
                      contact held down to write and re-write for minutes). n_strokes_counted <= max_strokes; the sweep rule
                      (max_scribble ...) is then measured on these strokes.
success = the picture rule (image_success) and every process rule (strict_ok). final_reward = the picture rule's continuous score
x min(1, max_path_mm / path_mm) when the colouring-in or path rule fails x (1 - scribble_share) when the sweep rule fails, with
the stroke cap's scaling taken on the counted strokes (max_strokes / n_strokes_counted): rule-abiding work keeps the picture
rule's score.

CLI: the same as rcb_brush.py (replay / render / run-oracle / selftest), scored with the rules.
"""

from __future__ import annotations

import math

import numpy as np

import rcb_brush as B
from rcb_brush import *  # noqa: F401,F403  (the scoring service reads Session, MAX_STEPS, ACTION_DIM and agent_metrics from here)

STRICT_KEYS = (
    "image_success",
    "image_final_reward",
    "strict_ok",
    "path_mm",
    "max_path_mm",
    "mark_width_mm",
    "min_mark_width_mm",
    "colour_in",
    "path_budget_ok",
    "longest_stroke_mm",
    "scribble_max",
    "scribble_share",
    "max_scribble",
    "max_scribble_share",
    "scribble_ok",
    "n_strokes_counted",
    "strokes_counted_ok",
    "n_marked_pieces",
    "longest_counted_stroke_mm",
    "max_stroke_path_mm",
)
RULE_KEYS = ("max_path_mm", "min_mark_width_mm", "max_scribble", "max_scribble_share", "scribble_min_mm",
             "stroke_gap_mm", "mark_min_width_mm", "max_stroke_path_mm")
SPLIT_KEYS = ("stroke_gap_mm", "mark_min_width_mm", "max_stroke_path_mm")   # the counted strokes (calligraphy): all three or none


def stroke_stats(strokes: list[dict], cur: dict | None = None, px_mm2: float = 0.0) -> list[tuple[float, float, float]]:
    """(length mm, bounding-box diagonal mm, own mark area mm2) of every inked stroke on the main sheet. A stroke's own mark is its
    `mask` (coverage >= 0.5, as for the sheet's ink); `cur` = a stroke still pressed: its samples and `acc` (coverage in its bbox)."""
    out = []
    for s in list(strokes) + ([cur] if cur is not None else []):
        if s.get("sheet") != "main" or not s.get("inked"):
            continue
        P = np.asarray(s.get("samples", ()), np.float64).reshape(-1, 9)
        L = float(np.sum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])))) * 1000.0 if len(P) > 1 else 0.0
        d = float(np.hypot(*(P[:, :2].max(0) - P[:, :2].min(0)))) * 1000.0 if len(P) > 1 else 0.0
        m = s.get("mask")
        if m is not None and np.size(m):
            own = float(np.count_nonzero(np.asarray(m) >= 128)) * px_mm2
        elif s.get("acc") is not None:
            own = float(np.count_nonzero(np.asarray(s["acc"]) >= 0.5)) * px_mm2
        else:
            own = 0.0
        out.append((L, d, own))
    return out


def _path_mm(P: np.ndarray) -> float:
    return float(np.sum(np.hypot(np.diff(P[:, 0]), np.diff(P[:, 1])))) * 1000.0 if len(P) > 1 else 0.0


def marked_pieces(P: np.ndarray, min_w_mm: float, gap_mm: float) -> list[tuple[int, int]]:
    """Sample ranges [a, b) of the marked pieces of one contact (samples P (N, 9), column 3 = the mark's width in m): runs of
    samples whose mark is at least min_w_mm wide, joined across the samples between them unless the tip moves more than gap_mm
    there. Samples before the first and after the last marking one belong to no piece (the touch-down and the lift)."""
    idx = np.flatnonzero(P[:, 3] >= min_w_mm / 1000.0) if len(P) else np.zeros(0, np.int64)
    if not len(idx):
        return []
    out, a, prev = [], int(idx[0]), int(idx[0])
    for i in idx[1:]:
        i = int(i)
        if i != prev + 1 and _path_mm(P[prev:i + 1]) > gap_mm:
            out.append((a, prev + 1))
            a = i
        prev = i
    out.append((a, prev + 1))
    return out


def piece_stats(strokes: list[dict], cur: dict | None, cfg: dict) -> list[tuple[float, float]] | None:
    """(length mm, bounding-box diagonal mm) of every marked piece of the main sheet's inked strokes, or None when the rule has
    no counted strokes (SPLIT_KEYS absent)."""
    if not all(k in cfg for k in SPLIT_KEYS):
        return None
    out = []
    for s in list(strokes) + ([cur] if cur is not None else []):
        if s.get("sheet") != "main" or not s.get("inked"):
            continue
        P = np.asarray(s.get("samples", ()), np.float64).reshape(-1, 9)
        for a, b in marked_pieces(P, float(cfg["mark_min_width_mm"]), float(cfg["stroke_gap_mm"])):
            Q = P[a:b]
            d = float(np.hypot(*(Q[:, :2].max(0) - Q[:, :2].min(0)))) * 1000.0 if len(Q) > 1 else 0.0
            out.append((_path_mm(Q), d))
    return out


def counted_strokes(pieces: list[tuple[float, float]], cfg: dict) -> int:
    """The strokes the cap counts: one per marked piece, ceil(length / max_stroke_path_mm) for a longer one."""
    lim = float(cfg["max_stroke_path_mm"])
    return int(sum(max(1, math.ceil(L / lim - 1e-9)) for L, _ in pieces))


def process_metrics(stats: list[tuple[float, float, float]], cfg: dict, marks: bool = True,
                    pieces: list[tuple[float, float]] | None = None) -> dict:
    """The rules' quantities and verdicts from the main sheet's inked strokes (stroke_stats) and the rule (cfg). marks: the medium
    keeps each stroke's own mark (calligraphy, broad nib, pointed pen; not the paint engine). pieces: the marked pieces
    (piece_stats) where the rule counts strokes: the cap and the sweep rule are then taken on them."""
    L = np.asarray([x[0] for x in stats], np.float64)
    D = np.asarray([x[1] for x in stats], np.float64)
    A = np.asarray([x[2] for x in stats], np.float64)
    total = float(L.sum())
    m = {"path_mm": round(total, 2), "longest_stroke_mm": round(float(L.max()), 2) if len(L) else 0.0}
    if marks:
        m["mark_width_mm"] = round(float(A.sum()) / total, 4) if total > 0 else 0.0
    ok = True
    if "max_path_mm" in cfg and "min_mark_width_mm" in cfg:  # colouring in: a long path AND thin marks
        m["max_path_mm"], m["min_mark_width_mm"] = float(cfg["max_path_mm"]), float(cfg["min_mark_width_mm"])
        m["colour_in"] = float(total > m["max_path_mm"] and m.get("mark_width_mm", 0.0) < m["min_mark_width_mm"])
        ok = ok and not m["colour_in"]
    elif "max_path_mm" in cfg:  # the path budget alone
        m["max_path_mm"] = float(cfg["max_path_mm"])
        m["path_budget_ok"] = float(total <= m["max_path_mm"])
        ok = ok and bool(m["path_budget_ok"])
    if pieces is not None:  # the counted strokes (calligraphy): the cap and the sweep rule on the marked pieces
        L = np.asarray([x[0] for x in pieces], np.float64)
        D = np.asarray([x[1] for x in pieces], np.float64)
        n = counted_strokes(pieces, cfg)
        m["n_marked_pieces"] = float(len(pieces))
        m["n_strokes_counted"] = float(n)
        m["max_stroke_path_mm"] = float(cfg["max_stroke_path_mm"])
        m["longest_counted_stroke_mm"] = round(float(L.max()), 2) if len(L) else 0.0
        m["strokes_counted_ok"] = float(n <= int(cfg["max_strokes"]))
        ok = ok and bool(m["strokes_counted_ok"])
    ratio = L / np.maximum(D, float(cfg.get("scribble_min_mm", 10.0))) if len(L) else L
    m["scribble_max"] = round(float(ratio.max()), 4) if len(L) else 0.0
    if "max_scribble" in cfg:
        tot = float(L.sum())       # = path_mm; on the marked pieces, without the touch-downs, lifts and unmarked moves
        share = float(L[ratio > float(cfg["max_scribble"])].sum() / tot) if tot > 0 else 0.0
        m["scribble_share"] = round(share, 6)
        m["max_scribble"] = float(cfg["max_scribble"])
        m["max_scribble_share"] = float(cfg.get("max_scribble_share", 0.0))
        m["scribble_ok"] = float(share <= m["max_scribble_share"])
        ok = ok and bool(m["scribble_ok"])
    m["strict_ok"] = float(ok)
    return m


def apply_rules(m: dict, stats: list[tuple[float, float, float]], cfg: dict, marks: bool = True,
                pieces: list[tuple[float, float]] | None = None) -> dict:
    """RoboPaint's metrics m (success, final_reward) -> the same with the process rules: success = image success and the rules."""
    out = dict(m)
    pm = process_metrics(stats, cfg, marks, pieces)
    out.update(pm)
    out["image_success"] = float(bool(m.get("success")))
    out["image_final_reward"] = float(m.get("final_reward") or 0.0)
    out["success"] = float(bool(m.get("success")) and bool(pm["strict_ok"]))
    f = out["image_final_reward"]
    if (pm.get("colour_in") or pm.get("path_budget_ok") == 0.0) and pm["path_mm"] > pm["max_path_mm"] > 0:
        f *= pm["max_path_mm"] / pm["path_mm"]
    if not pm.get("scribble_ok", 1.0):
        f *= 1.0 - pm["scribble_share"]
    if "n_strokes_counted" in pm:  # the cap's scaling on the counted strokes instead of the contacts
        cap, n_raw, n = float(cfg["max_strokes"]), float(m.get("n_strokes") or 0.0), pm["n_strokes_counted"]
        f *= min(1.0, cap / n if n > 0 else 1.0) / min(1.0, cap / n_raw if n_raw > 0 else 1.0)
    out["final_reward"] = round(f, 6)
    return out


class Session(B.Session):
    """RoboPaint's Session; score() adds the process rules (graders' side: the instance holds the scoring data)."""

    def score(self) -> dict[str, float]:
        m = super().score()
        if self.truth is None:  # an agent-side copy asks the scoring service, which applies the rules itself
            return m
        cur = self.painter.cur
        cur_s = None
        if cur is not None:
            acc = cur.get("acc")
            bb = cur.get("bbox")
            cur_s = {
                "sheet": cur["sheet"],
                "inked": cur["inked"],
                "samples": cur["samples"],
                "acc": acc[bb[0] : bb[1], bb[2] : bb[3]] if (acc is not None and bb is not None) else None,
            }
        px_mm2 = (float(self.geo.px_m) * 1000.0) ** 2
        cfg = self.inst["target"]["success"]
        return apply_rules(
            m,
            stroke_stats(self.painter.strokes, cur_s, px_mm2),
            cfg,
            marks=self.medium != "mypaint",
            pieces=piece_stats(self.painter.strokes, cur_s, cfg),
        )


def agent_metrics(m: dict) -> dict:
    """What the scoring service returns to the agent: RoboPaint's agent metrics plus the process rules' quantities."""
    return {**B.agent_metrics(m), **{k: m[k] for k in STRICT_KEYS if k in m}}


def main() -> None:
    B.Session = Session  # rcb_brush's CLI (replay, render, run-oracle, selftest) with the rules
    B.main()


if __name__ == "__main__":
    main()
