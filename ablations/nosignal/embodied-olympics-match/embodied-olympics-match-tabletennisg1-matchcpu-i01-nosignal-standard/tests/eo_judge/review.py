"""Review diagnostics (fw_pattern_1020.md §7 item 3, decided 10-20): a missing review never loses a match; WHY / PLAN
are still requested and recorded, and what was missing, empty or a template is reported here, never judged.

Rule eo-review-diag/1 (reproducible from the episode alone):

  due        realtime: after every unit_over row that did not end the match by its rules (no `end` row with reason
             match_over / completed at the same step), every
             seat the row names in `review` (when the Host records it), else every seat not retired before the row;
             turn-based: after every command of a seat, unless the match ended right after it by its rules
             (`end` with reason match_over before any review)
  submitted  realtime: the seat's `ready` rows with unit >= 1 (unit 0 is the start); turn-based: its `review` rows
  missing    a due review without a submission (realtime: none for that unit; turn-based: none before the seat's
             next command or the end)
  empty      a submission whose WHY and PLAN both have no letter or digit
  template   a submission whose normalized text equals the text of another submission of the same seat;
             normalized = Unicode NFKC, lower case, every run of digits replaced by '#', every run of whitespace by
             one space, stripped; text = normalized WHY + newline + normalized PLAN
  undetermined  template detection needs two non-empty submissions of the seat: with fewer, each one cannot be
             judged ("无法判断")
  distinct   a non-empty submission that is not a template

A seat's template verdict: "yes" (some submission is a template), "no" (two or more non-empty submissions and none is),
"undetermined" (fewer than two). The source tag of each submission (agent / program / program_raw, declared by the
seat's process chain) is counted as recorded; it says nothing about who wrote the text and is never judged.
"""
from __future__ import annotations

import re
import unicodedata

RULE = "eo-review-diag/1"
_DIGITS = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")
_ALNUM = re.compile(r"[^\W_]", re.UNICODE)


def normalize(text) -> str:
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    return _SPACE.sub(" ", _DIGITS.sub("#", t)).strip()


def is_empty(why, plan) -> bool:
    return not _ALNUM.search(str(why or "")) and not _ALNUM.search(str(plan or ""))


def _turn(rows: list, subs: dict, due_n: dict, missing: list) -> None:
    pending = None                                 # (seat, k) of the command whose review is due
    for r in rows:
        ev, seat = r.get("ev"), r.get("seat")
        if ev == "cmd" and seat in subs:
            if pending is not None:
                missing.append({"seat": pending[0], "unit": pending[1]})
            pending = (seat, r.get("k"))
            due_n[seat] += 1
        elif ev == "review" and seat in subs:
            subs[seat].append({"unit": r.get("after_action"), "why": r.get("why"), "plan": r.get("plan"),
                               "source": r.get("source")})
            if pending is not None and pending[0] == seat:
                pending = None
        elif ev == "end" and pending is not None:
            if r.get("reason") == "match_over":
                due_n[pending[0]] -= 1             # the command ended the match: no review was due
            else:
                missing.append({"seat": pending[0], "unit": pending[1]})
            pending = None
    if pending is not None:
        missing.append({"seat": pending[0], "unit": pending[1]})


NO_REVIEW_RESUME_S = 2.0      # a unit the world resumed from this fast, with no review sent or missed, held none


def _held(rows: list) -> dict:
    """{unit: whether the world held a review after it}. A unit whose rules hold no review (a shoot-out kick: the
    next kick is set up at once) is followed by the world's `resume` within moments, with no `ready` for it and no
    `review_missing` row; a missed review is resumed only at the window's deadline and leaves a `review_missing` row.
    Units this cannot tell (no resume row) count as held."""
    out, opened = {}, {}
    sent = {r.get("unit") for r in rows if r.get("ev") == "ready"}
    lost = {r.get("after_unit") for r in rows if r.get("ev") == "review_missing"}
    for r in rows:
        ev = r.get("ev")
        if ev == "unit_over":
            opened = {"unit": r.get("unit"), "ts": r.get("ts")}
        elif ev == "resume" and opened:
            u, ts = opened["unit"], opened.get("ts")
            quick = ts is not None and r.get("ts") is not None and r["ts"] - ts < NO_REVIEW_RESUME_S
            out[u] = not (quick and u not in sent and u not in lost)
            opened = {}
    return out


def _realtime(rows: list, seats: list, side_of: dict, subs: dict, due_n: dict, missing: list) -> None:
    # a unit that ended the match by its rules has no review (an `end` row at the same step with reason match_over /
    # completed); a Host that ended the match on a late review leaves that review due
    ends = {r.get("k") for r in rows if r.get("ev") == "end" and r.get("reason") in ("match_over", "completed")}
    held = _held(rows)
    retired: set = set()
    due = []
    for r in rows:
        ev = r.get("ev")
        if ev == "retire":
            side = r.get("side", side_of.get(r.get("seat")))
            retired |= {s for s in seats if side_of.get(s, s) == side} | {r.get("seat")}
        elif ev == "unit_over" and r.get("k") not in ends and held.get(r.get("unit"), True):
            named = r.get("review")
            who = list(named) if isinstance(named, list) else [s for s in seats if s not in retired]
            due += [(s, r.get("unit")) for s in who if s in subs]
        elif ev == "ready" and r.get("seat") in subs and (r.get("unit") or 0) >= 1:
            subs[r["seat"]].append({"unit": r.get("unit"), "why": r.get("why"), "plan": r.get("plan"),
                                    "source": r.get("source")})
    got = {(s, x["unit"]) for s, xs in subs.items() for x in xs}
    for s, u in due:
        due_n[s] += 1
        if (s, u) not in got:
            missing.append({"seat": s, "unit": u})


def diagnose(rows: list, seats: list, protocol: str | None, side_of: dict | None = None) -> dict:
    """{"rule", "by_seat": {seat: counts, template verdict, sources}, "missing": [{seat, unit}]} from the episode
    rows (file order)."""
    subs: dict = {s: [] for s in seats}
    due_n = {s: 0 for s in seats}
    missing: list = []
    if protocol == "turn":
        _turn(rows, subs, due_n, missing)
    else:
        _realtime(rows, seats, side_of or {}, subs, due_n, missing)
    by_seat = {}
    for s in seats:
        items = subs[s]
        texts = [normalize(x["why"]) + "\n" + normalize(x["plan"]) for x in items]
        nonempty = [i for i, x in enumerate(items) if not is_empty(x["why"], x["plan"])]
        counts = {"due": due_n[s], "submitted": len(items),
                  "missing": sum(1 for m in missing if m["seat"] == s), "empty": len(items) - len(nonempty),
                  "template": 0, "distinct": 0, "undetermined": 0}
        if len(nonempty) < 2:
            counts["undetermined"] = len(nonempty)
            verdict = "undetermined"
        else:
            for i in nonempty:
                if any(texts[i] == texts[j] for j in nonempty if j != i):
                    counts["template"] += 1
                else:
                    counts["distinct"] += 1
            verdict = "yes" if counts["template"] else "no"
        sources: dict = {}
        for x in items:
            sources[str(x.get("source"))] = sources.get(str(x.get("source")), 0) + 1
        by_seat[s] = {**counts, "template_seat": verdict, "sources": dict(sorted(sources.items()))}
    return {"rule": RULE, "by_seat": by_seat, "missing": missing}
