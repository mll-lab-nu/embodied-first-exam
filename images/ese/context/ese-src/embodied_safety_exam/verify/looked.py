"""Re-mark records post hoc (0.5.4): `python -m embodied_safety_exam.verify.looked RECORD.json [...]` replays each record from
scratch (`verify.verify`) and prints, one JSON line per record, the marks the pictures decide: `looked`,
`told_after_evidence`, `evidence_seen` (camera, tick, call), the decision instant (`moments.decision`), and pass /
outcome / judgment_class. A record of RCB's service (`record.json` of a trial's verifier) is one of these. Marks taken
by the live pixel check before 0.5.4's ray casting (or any record) are re-marked this way; the result does not depend
on the host, on what else was drawn, or on the clock."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def remark(record: dict) -> dict:
    from embodied_safety_exam import verify
    v = verify.verify(record)
    m = v.get("marks") or {}
    return {"instance": record.get("instance"), "version": v.get("version"),
            "recorded_scoring": v.get("recorded_scoring"), "judged_by": v.get("judged_by"),
            "scoring_identity": v.get("scoring_identity"), "pass": v.get("pass"), "outcome": v.get("outcome"),
            "judgment_class": v.get("judgment_class"), "looked": m.get("looked"), "told_after_evidence": m.get("told_after_evidence"),
            "evidence_seen": v.get("evidence_seen"), "decision": (v.get("moments") or {}).get("decision"),
            "replay_match": (v.get("replay") or {}).get("match"), "error": v.get("error")}


def main(argv=None) -> int:
    paths = list(argv if argv is not None else sys.argv[1:])
    if not paths:
        print(__doc__)
        return 2
    for p in paths:
        out = remark(json.loads(Path(p).read_text()))
        print(json.dumps({"record": str(p), **out}, sort_keys=True, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
