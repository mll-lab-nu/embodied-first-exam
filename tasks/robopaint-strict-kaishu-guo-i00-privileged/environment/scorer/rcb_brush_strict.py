"""
rcb_brush_strict.py — RoboPaint-strict: RoboPaint's brush tasks with process rules on top of the picture score. The robot, the
scene, the brush models, the target and the picture score are RoboPaint's own (rcb_brush.py and rcb_brush_score.py, byte-identical
to the RoboPaint tasks'); this module only adds the rules and is used on the graders' side:
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
success = RoboPaint's rule (image_success, unchanged) and every process rule (strict_ok). final_reward = RoboPaint's continuous
score x min(1, max_path_mm / path_mm) when the colouring-in or path rule fails x (1 - scribble_share) when the sweep rule fails:
rule-abiding work keeps RoboPaint's score.

CLI: the same as rcb_brush.py (replay / render / run-oracle / selftest), scored with the rules.
"""

from __future__ import annotations

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
)
RULE_KEYS = ("max_path_mm", "min_mark_width_mm", "max_scribble", "max_scribble_share", "scribble_min_mm")


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


def process_metrics(stats: list[tuple[float, float, float]], cfg: dict, marks: bool = True) -> dict:
    """The rules' quantities and verdicts from the main sheet's inked strokes (stroke_stats) and the rule (cfg). marks: the medium
    keeps each stroke's own mark (calligraphy, broad nib, pointed pen; not the paint engine)."""
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
    ratio = L / np.maximum(D, float(cfg.get("scribble_min_mm", 10.0))) if len(L) else L
    m["scribble_max"] = round(float(ratio.max()), 4) if len(L) else 0.0
    if "max_scribble" in cfg:
        share = float(L[ratio > float(cfg["max_scribble"])].sum() / total) if total > 0 else 0.0
        m["scribble_share"] = round(share, 6)
        m["max_scribble"] = float(cfg["max_scribble"])
        m["max_scribble_share"] = float(cfg.get("max_scribble_share", 0.0))
        m["scribble_ok"] = float(share <= m["max_scribble_share"])
        ok = ok and bool(m["scribble_ok"])
    m["strict_ok"] = float(ok)
    return m


def apply_rules(m: dict, stats: list[tuple[float, float, float]], cfg: dict, marks: bool = True) -> dict:
    """RoboPaint's metrics m (success, final_reward) -> the same with the process rules: success = image success and the rules."""
    out = dict(m)
    pm = process_metrics(stats, cfg, marks)
    out.update(pm)
    out["image_success"] = float(bool(m.get("success")))
    out["image_final_reward"] = float(m.get("final_reward") or 0.0)
    out["success"] = float(bool(m.get("success")) and bool(pm["strict_ok"]))
    f = out["image_final_reward"]
    if (pm.get("colour_in") or pm.get("path_budget_ok") == 0.0) and pm["path_mm"] > pm["max_path_mm"] > 0:
        f *= pm["max_path_mm"] / pm["path_mm"]
    if not pm.get("scribble_ok", 1.0):
        f *= 1.0 - pm["scribble_share"]
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
        return apply_rules(
            m,
            stroke_stats(self.painter.strokes, cur_s, px_mm2),
            self.inst["target"]["success"],
            marks=self.medium != "mypaint",
        )


def agent_metrics(m: dict) -> dict:
    """What the scoring service returns to the agent: RoboPaint's agent metrics plus the process rules' quantities."""
    return {**B.agent_metrics(m), **{k: m[k] for k in STRICT_KEYS if k in m}}


def main() -> None:
    B.Session = Session  # rcb_brush's CLI (replay, render, run-oracle, selftest) with the rules
    B.main()


if __name__ == "__main__":
    main()
