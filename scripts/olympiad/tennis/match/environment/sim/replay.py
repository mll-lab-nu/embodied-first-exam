"""Fresh-process replay of a wall-clock tennis match from its logged commands (no wall time, no worker processes).

    python3 replay.py episode.jsonl K_END out.json

The log gives, in the order the service performed them, every act snapshot (the step k_s an act was accepted at)
and every applied command (its effect step; an act's plan was computed from the snapshot of k_s, for k_e). The
replay re-runs the match from its recorded seed, takes the same snapshots, recomputes each plan in-process with the
same code the planner process ran (tn.PlanCtx), installs it at its effect step and applies `none` / `move` at
theirs. It must consume the complete record and reproduce the score, the final state hash and every joint target.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def source_sha():
    h = hashlib.sha256()
    names = ["tn.py"] + [str(p.relative_to(HERE)) for p in sorted((HERE / "scene").rglob("*")) if p.is_file()]
    for name in names:
        h.update(name.encode()); h.update((HERE / name).read_bytes())
    return h.hexdigest()


def main(ep_path, k_end, out_path):
    with open(ep_path) as f:
        events = [json.loads(line) for line in f if line.strip()]
    meta = next(e for e in events if e.get("ev") == "start")
    os.environ["MATCH_SEED"] = str(meta["seed"])
    import tn
    if meta.get("revision") != tn.REVISION or meta.get("source_sha") != source_sha():
        raise ValueError("recorded simulator version/fingerprint differs; use the original task version")
    ops = sorted((e for e in events if e.get("ev") in ("act_snapshot", "act_applied")), key=lambda e: e["op"])
    ops = [e for e in ops if e["k"] < k_end]    # a command applied at the final step never acted on the world
    applied = {e["act_id"] for e in ops if e["ev"] == "act_applied"}
    ops = [e for e in ops if e["ev"] == "act_applied" or e["act_id"] in applied]   # snapshots of dropped acts: unused
    if any(a["k"] > b["k"] for a, b in zip(ops, ops[1:])) or any(e["k"] < 0 for e in ops):
        raise ValueError("invalid command step sequence")
    r = tn.Match(int(meta["level"]))
    ctx = tn.PlanCtx()
    pending, i, n_applied = {}, 0, 0
    while r.k < k_end and not r.done:
        while i < len(ops) and ops[i]["k"] == r.k:
            e = ops[i]; i += 1
            if e["ev"] == "act_snapshot":
                dec = next(o["decision"] for o in ops if o["ev"] == "act_applied" and o["act_id"] == e["act_id"])
                pending[e["act_id"]] = ctx.plan_act(tn.plan_snapshot(r), e["k_effect"] - e["k"], dec["t"], dec["pos"],
                                                    dec["normal"], dec["vel"], dec.get("base"))
                continue
            dec = e["decision"]
            if dec["type"] == "act":
                r.rt_install(pending.pop(e["act_id"]))
            elif dec["type"] == "none":
                r.rt_clear()
            else:
                r.rt_move(*dec["base"])
            n_applied += 1
        r.rt_advance(1)
    if i != len(ops) or r.k != k_end or pending:
        raise ValueError("replay did not consume the complete command/step record")
    a = np.ascontiguousarray(r.s.actions(), dtype=np.float64)
    out = {"score": list(r.score), "steps": r.k, "n_commands": n_applied, "state_sha": r.s.state_sha(),
           "actions_sha": hashlib.sha256(a.tobytes()).hexdigest(), "seed": meta["seed"], "revision": tn.REVISION,
           "source_sha": meta["source_sha"], "done": r.done,
           "points": [{k: p[k] for k in ("winner", "how", "score", "step")} for p in r.points]}
    Path(out_path).write_text(json.dumps(out, default=float))
    print(json.dumps({k: out[k] for k in ("score", "steps", "n_commands", "done")}))


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
