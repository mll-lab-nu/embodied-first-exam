"""rl_audit.py: the post-match method audit of the joint-level soccer CPU mode (v4, Chi 2026-10-14; design
review/screening/cpu_gpu_rule_zh.md Q1 / detail 2), modelled on players/nocode/nocode_audit.py.

The CPU mode measures whether a model understands robot engineering, so compute must not replace understanding:
  BANNED  any algorithm that updates policy parameters from reward or return (PPO, SAC, policy gradient, Q-learning,
          REINFORCE, evolution strategies that train a neural network, ...), neural-network controllers (a trained
          network in the loop), imitation learning (behaviour cloning, DAgger, ...);
  ALLOWED hand-written control (PD, LQR, inverted-pendulum / ZMP / capture-point gaits, whole-body QP), online planning
          (MPC, sampling MPC such as MPPI), offline trajectory optimisation, system identification, and search-tuning
          of at most 50 parameters of a hand-written controller (grid, CEM, CMA-ES, differential evolution).
The agent writes /app/output/METHOD.md before `game start` (methods, the tuned parameters and how many).

Three layers (a violation = a valid trial that is lost, reported as `rl_violation`, decided 2026-10-14):
  1. this script: METHOD.md present and written before the start, the declared tuned-parameter count, and a keyword /
     pattern scan of every program, note and log the seat left in /app/output and of the session transcript
     (agents/*/: the commands and patches the model ran), with file:line excerpts -> rl_audit.json, verdict
     "clean" (no hit) or "review";
  2. a model reviewer reads the packet (rl_review.md: METHOD.md, the hits with context, the list of programs) and
     answers whether a banned method was used to produce the controller that played;
  3. a human spot-checks every "violation" and a sample of "clean".

    python3 rl_audit.py TRIAL_DIR [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

MAX_TUNED = 50
TEXT_EXT = {".py", ".md", ".txt", ".sh", ".json", ".jsonl", ".log", ".yaml", ".yml", ".toml", ".cfg", ""}
MAX_BYTES = 4_000_000
# category -> patterns (case-insensitive). Strong categories alone send a trial to review.
PATTERNS = {
    "rl_library": [r"\bimport\s+(torch|jax|optax|flax|tensorflow|keras|gym|gymnasium|stable_baselines3?|rsl_rl|"
                   r"skrl|rl_games|tianshou|brax|mjlab)\b", r"\bfrom\s+(torch|jax|optax|flax|tensorflow|keras|gym|"
                   r"gymnasium|stable_baselines3?|rsl_rl|skrl|brax|mjlab)\b", r"pip\s+install"],
    "rl_algorithm": [r"\bppo\b", r"proximal policy", r"policy[ _-]?gradient", r"\breinforce\b", r"actor[ _-]?critic",
                     r"\bgae\b", r"generali[sz]ed advantage", r"q[ _-]?learning", r"\bdqn\b",
                     r"\bsac\b", r"soft actor", r"\btd3\b", r"\bddpg\b", r"replay[ _]buffer", r"value[ _]function",
                     r"\bcritic\b", r"discounted return", r"log[ _]?prob", r"clip[ _]?ratio|clip_param"],
    "neural_network": [r"neural", r"\bmlp\b", r"hidden[ _]?(layer|dim|size|units)", r"backprop", r"\badam\b",
                       r"\bsgd\b", r"np\.tanh\([^)]*@", r"@\s*w\d", r"\bweights?\b.*\bbias(es)?\b",
                       r"\.npz\b", r"\bepochs?\b", r"learning[ _]rate", r"\bgradient\b"],
    "evolution_on_network": [r"evolution(ary)? strateg", r"openai[ _-]?es\b", r"\bneuroevolution\b", r"\bneat\b"],
    "imitation": [r"\bimitation[ _]learn", r"behaviou?r[ _]clon", r"\bdagger\b"],
    "reward_design": [r"\breward\b", r"\breturns?\b(?!\s*(self|out|np|None|True|False|\[|\())", r"episode[ _]return"],
    "optimiser_dimension": [r"\b(cma|cmaes|cma-es|differential_evolution|cem)\b", r"popsize|population", r"\bsigma0\b"],
}
STRONG = {"rl_library", "rl_algorithm", "evolution_on_network", "imitation"}
MISC = {"neural_network", "reward_design", "optimiser_dimension"}
CODE_EXT = {".py", ".md", ".sh", ""}


def text_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_EXT and p.stat().st_size <= MAX_BYTES and "__pycache__" not in p.parts:
            yield p


def scan(path: Path, rel: str):
    hits = []
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return hits
    comp = {c: [re.compile(p, re.I) for p in ps] for c, ps in PATTERNS.items()}
    for i, ln in enumerate(lines):
        if len(ln) > 2000:
            ln = ln[:2000]
        for c, rs in comp.items():
            if c in MISC and path.suffix.lower() not in CODE_EXT:
                continue                                  # weak patterns only in programs and notes, not in logs
            for r in rs:
                m = r.search(ln)
                if m:
                    hits.append(dict(category=c, file=rel, line=i + 1, match=m.group(0)[:60], text=ln.strip()[:240]))
                    break
    return hits


def method_md(out_dir: Path):
    p = out_dir / "METHOD.md"
    if not p.exists():
        return dict(present=False)
    t = p.read_text(errors="replace")
    m = (re.search(r"tuned[^\n]*?(\d+)\s*(scalar )?(parameters|params|settings)", t, re.I) or
         re.search(r"(\d+)\s*(tuned |scalar )?(parameters|settings)", t, re.I))
    n = int(m.group(1)) if m else None
    rl_claim = re.search(r"\b(no|none|not used)\b[^\n]*(rl|reinforcement|learning)", t, re.I) is not None
    return dict(present=True, bytes=len(t), mtime=p.stat().st_mtime, declared_tuned_params=n,
                over_cap=(n is not None and n > MAX_TUNED), says_no_rl=rl_claim, text=t[:6000])


def game_start_time(trial: Path):
    for ep in trial.rglob("episode.jsonl"):
        for ln in open(ep, errors="replace"):
            if '"ev": "ready"' in ln and '"unit": 0' in ln:
                try:
                    return json.loads(ln)["ts"]
                except (ValueError, KeyError):
                    return None
    return None


def audit(trial: Path):
    trial = Path(trial)
    outs = [p for p in trial.rglob("app/output") if p.is_dir()]
    res = dict(trial=str(trial), seats={})
    t_start = game_start_time(trial)
    for od in outs:
        seat = "A" if "seat_b" not in str(od) else "B"
        hits = []
        for f in text_files(od):
            hits += scan(f, str(f.relative_to(od)))
        meth = method_md(od)
        if meth.get("present") and t_start:
            meth["written_before_start"] = meth["mtime"] <= t_start + 60   # file copies keep mtimes (harbor artifacts)
        res["seats"][str(od.relative_to(trial))] = dict(seat=seat, method=meth, hits=hits)
    tr_hits = []
    for ag in trial.rglob("agents"):
        if ag.is_dir():
            for f in text_files(ag):
                tr_hits += scan(f, str(f.relative_to(trial)))
    res["transcript_hits"] = tr_hits
    for k, s in res["seats"].items():
        cats = {h["category"] for h in s["hits"]}
        s["categories"] = sorted(cats)
        s["n_hits"] = {c: sum(h["category"] == c for h in s["hits"]) for c in sorted(cats)}
        missing = not s["method"].get("present") or s["method"].get("written_before_start") is False
        s["verdict"] = "review" if (cats & STRONG or s["method"].get("over_cap") or missing) else "clean"
    return res


def packet(res) -> str:
    """The layer-2 review packet (markdown) for a model or a human reviewer."""
    out = ["# RL audit review packet", "", "Rule (CPU mode): " + __doc__.split("Three layers")[0].split("compute must not "
           "replace understanding:")[1].strip(), "", "Question: was any BANNED method used to produce, or does any "
           "banned method run inside, the controller that played the match? Answer violation / no violation with the "
           "evidence (file:line).", ""]
    for k, s in res["seats"].items():
        out += [f"## Seat {s['seat']} ({k}): verdict of layer 1 = {s['verdict']}", "",
                "### METHOD.md", "", "```", s["method"].get("text", "(missing)")[:4000], "```", "",
                f"declared tuned parameters: {s['method'].get('declared_tuned_params')}, written before the start: "
                f"{s['method'].get('written_before_start')}", "", "### Hits (strong categories first)", ""]
        hs = sorted(s["hits"], key=lambda h: (h["category"] not in STRONG, h["category"], h["file"], h["line"]))
        for h in hs[:300]:
            out.append(f"- [{h['category']}] {h['file']}:{h['line']}: `{h['text']}`")
        out.append("")
    if res["transcript_hits"]:
        out += ["## Transcript hits (strong categories)", ""]
        for h in [h for h in res["transcript_hits"] if h["category"] in STRONG][:200]:
            out.append(f"- [{h['category']}] {h['file']}:{h['line']}: `{h['text']}`")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trial")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = audit(Path(a.trial))
    out = Path(a.out or a.trial)
    out.mkdir(parents=True, exist_ok=True)
    (out / "rl_audit.json").write_text(json.dumps(res, indent=1))
    (out / "rl_review.md").write_text(packet(res))
    for k, s in res["seats"].items():
        print(s["seat"], k, s["verdict"], s["n_hits"], "METHOD.md:", s["method"].get("present"),
              s["method"].get("declared_tuned_params"))


if __name__ == "__main__":
    main()
