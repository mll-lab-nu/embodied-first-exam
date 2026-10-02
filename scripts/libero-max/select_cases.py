"""Choose the LIBERO-MAX cases of this benchmark (deterministic; no policy outcomes are looked at).

    python3 select_cases.py candidates <libero_max_8000.json> <out.json> [--per-event 20]
    python3 select_cases.py pick <candidates.json> <frozen dir> <cases.json> [--per-event 6]

Rule:
1. Only LIBERO-PRO-derived cases of LIBERO-MAX's 8,000-case manifest (liberomax/LIBERO-MAX @ a1e3cef): LIBERO-PRO's
   code is MIT and its data CC-BY-4.0; LIBERO-plus has no licence and ships third-party (TurboSquid) assets.
2. Per event (LIBERO-MAX `change_type`), order the cases by SHA-256 of `case_id`; drop a case that repeats an earlier
   one's scene (same BDDL file and initial state) and change; keep the first `--per-event` as candidates.
3. Every candidate is frozen and gets a scripted reference (freeze.sh). Per event, walk the candidates in that order:
   first the first verified case of each suite not yet used (covering the four suites), then the next verified ones,
   until `--per-event` are chosen. A candidate is verified when its reference succeeds with the event in the live run
   and in two fresh-process replays, it is not solved at the start and its instruction is a complete sentence.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

EVENTS = ["target_relocation", "receptacle_relocation", "obstacle_insertion", "distractor_burst", "camera_shift",
          "sensor_noise_onset", "illumination_switch", "visual_theme_switch"]  # fmt: skip
SUITES = ["libero_spatial", "libero_object", "libero_goal", "libero_10"]


def order(case_id: str) -> str:
    return hashlib.sha256(case_id.encode()).hexdigest()


def candidates(manifest: str, out: str, per_event: int) -> None:
    cases = json.loads(Path(manifest).read_text())["cases"]
    pro = [c for c in cases if (c.get("substrate_variant") or {}).get("benchmark") == "LIBERO-PRO"]
    chosen = []
    for ev in EVENTS:
        seen, n = set(), 0
        for c in sorted((c for c in pro if c["scenario"]["change_type"] == ev), key=lambda c: order(c["case_id"])):
            key = (
                c["substrate_variant"]["bddl_file"],
                c["init_state_index"],
                json.dumps(c["scenario"]["change"], sort_keys=True),
            )
            if key in seen:
                continue
            seen.add(key)
            chosen.append(c)
            n += 1
            if n == per_event:
                break
    src = "liberomax/LIBERO-MAX@a1e3cef benchmark/max8000/libero_max_8000.json"
    Path(out).write_text(
        json.dumps({"source": src, "rule": __doc__.split("Rule:")[1].strip(), "cases": chosen}, indent=1) + "\n"
    )
    print(f"{len(chosen)} candidates")


def sentence_ok(text: str) -> bool:
    t = text.strip()
    return (
        bool(t) and "..." not in t and re.fullmatch(r"[A-Za-z][A-Za-z0-9 ,'\-]+", t) is not None and len(t.split()) >= 3
    )


def pick(cands: str, frozen: str, out: str, per_event: int) -> None:
    cases = json.loads(Path(cands).read_text())["cases"]
    picked, excluded = [], []
    for ev in EVENTS:
        evc = sorted((c for c in cases if c["scenario"]["change_type"] == ev), key=lambda c: order(c["case_id"]))
        ok = []
        for c in evc:
            rp = Path(frozen) / c["case_id"] / "report.json"
            r = json.loads(rp.read_text()) if rp.exists() else {"ok": False, "why": "not frozen"}
            if r.get("ok") and not sentence_ok(r.get("language", "")):
                r = {**r, "ok": False, "why": f"instruction is not a complete sentence: {r.get('language')!r}"}
            (ok if r.get("ok") else excluded).append(
                c if r.get("ok") else {"case_id": c["case_id"], "why": r.get("why")}
            )
        first = []
        for suite in SUITES:
            c = next((c for c in ok if c["task_suite_name"] == suite), None)
            if c:
                first.append(c)
        rest = [c for c in ok if c not in first]
        sel = (first + rest)[:per_event]
        sel.sort(key=lambda c: order(c["case_id"]))
        picked += sel
        excluded += [
            {"case_id": c["case_id"], "why": "verified, not needed (event already has its cases)"}
            for c in rest[len(sel) - len(first) :]
            if c not in sel
        ]
    src = json.loads(Path(cands).read_text())["source"]
    doc = {"source": src, "rule": __doc__.split("Rule:")[1].strip(), "cases": picked, "excluded": excluded}
    Path(out).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(f"{len(picked)} cases picked; {len(excluded)} candidates excluded")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["candidates", "pick"])
    p.add_argument("args", nargs="+")
    p.add_argument("--per-event", type=int)
    a = p.parse_args()
    if a.mode == "candidates":
        candidates(a.args[0], a.args[1], a.per_event or 20)
    else:
        pick(a.args[0], a.args[1], a.args[2], a.per_event or 6)
