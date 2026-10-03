"""Fresh-process replay of a wall-clock baseball game from its logged (pitch, control step, command) list only.

    python3 replay.py episode.jsonl K_END out.json

No wall time is read: the recorded seed and level, the commands with the step at which each took effect, and the
final step. The recorded simulator fingerprint must match this copy (a different version is refused)."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bbrt  # noqa: E402

REVISION = "wallclock-3"


def source_sha():
    root = Path(__file__).resolve().parent
    h = hashlib.sha256()
    for name in ("bb.py", "bbrt.py"):
        h.update(name.encode()); h.update((root / name).read_bytes())
    return h.hexdigest()


def main(ep_path, k_end, out_path):
    with open(ep_path) as f:
        events = [json.loads(line) for line in f if line.strip()]
    meta = next(e for e in events if e.get("ev") == "start")
    if meta.get("revision") != REVISION or meta.get("source_sha") != source_sha():
        raise ValueError("recorded simulator version/fingerprint differs; use the original task version")
    acts = [(int(e["pitch_idx"]), int(e["k"]), e["decision"]) for e in events if e.get("ev") == "act_applied"]
    if any(k < 0 or k > k_end for _, k, _ in acts) or any((a[0], a[1]) > (b[0], b[1]) for a, b in zip(acts, acts[1:])):
        raise ValueError("invalid command step sequence")
    rt = bbrt.replay(int(meta["level"]), int(meta["seed"]), acts, k_end)
    if rt.k != k_end:
        raise ValueError(f"replay ended at step {rt.k}, the live game at {k_end}")
    g = rt.G
    decisions = json.loads(json.dumps(g.decisions, default=float))
    out = {"bases": g.bases, "steps": rt.k, "n_acts": len(acts), "state_sha": g.state_sha(),
           "decisions_sha": hashlib.sha256(json.dumps(decisions, sort_keys=True).encode()).hexdigest(),
           "seed": g.seed, "level": g.level, "revision": REVISION, "source_sha": meta["source_sha"], "done": g.done,
           "pitches": len(g.history), "pa_results": [r["result"] for r in g.pa_results]}
    Path(out_path).write_text(json.dumps(out, default=float))
    print(json.dumps({k: out[k] for k in ("bases", "steps", "n_acts", "done", "pitches")}))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
