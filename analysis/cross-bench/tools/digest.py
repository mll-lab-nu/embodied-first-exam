#!/usr/bin/env python3
"""Readable trial digests for reviewers: $XB_RAW/<key>/skeleton.md and timeline.md (no LLM).

usage: tools/digest.py KEY [KEY ...]

skeleton.md  (skim, <= ~8k tokens): header, every agent message (trimmed), one line per command, the tail of each
             script run, the final message, the verifier's verdict.
timeline.md  (deep): every message, reasoning excerpt, command and write in order; long outputs keep head and tail
             (trim widens until the file fits ~40k tokens); then the final code and the verifier files.
"""
from __future__ import annotations
import glob, json, os, sys
import atif, features
from common import RAW

SKELETON_CHARS, TIMELINE_CHARS = 28_000, 150_000


def clip(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else f"{s[: n // 2]}\n…[{len(s) - n} chars cut]…\n{s[-n // 2:]}"


def stamp(t) -> str:
    return "--:--" if t is None else f"{int(t):02d}:{int(round((t % 1) * 60)) % 60:02d}"


def header(meta: dict, instruction: str, n: int, sig: dict) -> str:
    r = meta["row"]
    cutoff = sig.get("budget_min") or r["timeout_min"]
    signals = ", ".join(f"{k} {sig[k]}" for k in ("clock_checks", "first_clock_min", "first_output_min", "first_submit_min",
                                                   "submits", "resets", "images_seen", "sleep_min", "max_gap_min") if sig.get(k) not in (None, ""))
    return (f'# {r["task"]} · {r["agent"]} · {r["mode"]}\n\n'
            f'result **{r["state"]}** · end `{r["end_reason"] or r["exception"] or "-"}` · agent {r["agent_min"]} of {cutoff} min'
            f' (cutoff stated in the instruction; times below are minutes:seconds{", interpolated from gateway requests" if sig.get("t_approx") else ""})'
            f' · tokens in {int(r["tok_in"]):,} out {int(r["tok_out"]):,} · validity {r["validity"]} {r["validity_reason"]}\n\n'
            f'regex signals (heuristic; minutes): {signals}\n'
            f'\n## Instruction the agent received\n{clip(instruction, n)}\n')


def verifier(d: str, lines: int) -> str:
    parts = []
    for p in ("verifier/reward.json",):
        if os.path.exists(os.path.join(d, p)):
            parts.append(f"reward.json: {open(os.path.join(d, p)).read()[:1500]}")
    for p in glob.glob(os.path.join(d, "**/final.json"), recursive=True)[:1]:
        try:
            fin = json.load(open(p))
            parts.append("final.json: " + json.dumps({k: v for k, v in fin.items() if not isinstance(v, (list, dict))})[:1500])
        except ValueError:
            pass
    g = os.path.join(d, "verifier/grade.log")
    if os.path.exists(g):
        parts.append("grade.log (tail):\n" + "\n".join(open(g, errors="replace").read().splitlines()[-lines:]))
    return "\n\n".join(parts)


def _rows(ev: list[dict], msg: int, thought: int, out: int) -> list[tuple[int, str]]:
    """(tier, line): tier 0 = messages and thoughts, 1 = script runs with their output tail, 2 = other tool calls."""
    rows = []
    for e in ev:
        if e["kind"] == "message":
            rows.append((0, f'[{stamp(e["t"])}] **{clip(e["text"], msg)}**'))
        elif e["kind"] == "thought":
            rows.append((0, f'[{stamp(e["t"])}] think: {clip(" ".join(e["text"].split()), thought)}'))
        else:
            run = e["kind"] == "shell" and "python" in e["text"]
            tail = " ⟶ " + " | ".join(e["out"].strip().splitlines()[-3:])[:out] if run else ""
            rows.append((1 if run else 2, f'[{stamp(e["t"])}] {e["kind"]}{" +img" if e["img"] else ""}: {" ".join(e["text"].split())[:200]}{tail}'))
    return rows


def _fit(rows: list[tuple[int, str]], budget: int) -> tuple[str, str]:
    """Keep tiers in order of importance; sample a tier evenly once it no longer fits. Order stays chronological."""
    keep, note = set(), []
    for tier in (0, 1, 2):
        idx = [i for i, (t, _) in enumerate(rows) if t == tier]
        size = sum(len(rows[i][1]) + 1 for i in idx)
        used = sum(len(rows[i][1]) + 1 for i in keep)
        room = budget - used
        if size <= room:
            keep |= set(idx)
        elif room > 0 and idx:
            step = -(-size // room)
            keep |= set(idx[::step])
            note.append(f"{['messages/thoughts', 'script runs', 'other calls'][tier]}: every {step}th of {len(idx)}")
        elif idx:
            note.append(f"{['messages/thoughts', 'script runs', 'other calls'][tier]}: none of {len(idx)} kept")
    body = "\n".join(t for i, (_, t) in enumerate(rows) if i in keep)
    return body, ("(sampled to fit: " + "; ".join(note) + ")\n") if note else ""


def skeleton(meta: dict, ev: list[dict], d: str, instruction: str, sig: dict) -> str:
    for lim in ((500, 300, 260), (300, 180, 160), (180, 100, 100)):
        rows = _rows(ev, *lim)
        if sum(len(t) + 1 for tier, t in rows if tier == 0) <= SKELETON_CHARS * 0.7:
            break
    body, note = _fit(rows, SKELETON_CHARS)
    last = next((e["text"] for e in reversed(ev) if e["kind"] == "message"), "")
    return f'{header(meta, instruction, 4000, sig)}\n## Steps\n{note}{body}\n\n## Final message\n{clip(last, 3000)}\n\n## Verifier\n{verifier(d, 15)}\n'


def timeline(meta: dict, ev: list[dict], d: str, instruction: str, sig: dict) -> str:
    for out_n in (3000, 1600, 800, 400, 200, 0):   # 0 = compact: tool calls as one line, outputs only for script runs
        rows = []
        for e in ev:
            if e["kind"] == "thought":
                rows.append(f'[{stamp(e["t"])}] THINK: {clip(e["text"], max(out_n, 1500))}')
            elif e["kind"] == "message":
                rows.append(f'\n[{stamp(e["t"])}] AGENT: {clip(e["text"], 4000 if out_n else 1500)}')
            elif e["kind"] == "write":
                rows.append(f'[{stamp(e["t"])}] WRITE ({e["name"]}):\n```\n{clip(e["text"], 2 * out_n or 300)}\n```')
            elif not out_n:
                tail = " ⟶ " + " | ".join(e["out"].strip().splitlines()[-4:])[:400] if "python" in e["text"] else ""
                rows.append(f'[{stamp(e["t"])}] {e["kind"]}{" +img" if e["img"] else ""}: {" ".join(e["text"].split())[:300]}{tail}')
            else:
                rows.append(f'[{stamp(e["t"])}] {e["kind"].upper()} ({e["name"]}){" [saw %d image(s)]" % e["img"] if e["img"] else ""}:'
                            f'\n```\n{clip(e["text"], min(2500, out_n))}\n```' + (f'\n→ {clip(e["out"], out_n)}' if e["out"].strip() else ""))
        body = "\n".join(rows)
        if len(body) <= TIMELINE_CHARS:
            break
    code = []
    for p in sorted(glob.glob(os.path.join(d, "artifacts/app/output/**/*.py"), recursive=True))[:4]:
        code.append(f"### {os.path.relpath(p, d)}\n```python\n{clip(open(p, errors='replace').read(), 8000)}\n```")
    return (f'{header(meta, instruction, 16000, sig)}\n## Timeline\n{body}\n\n## Final code\n' + ("\n".join(code) or "(none in artifacts)") +
            f'\n\n## Verifier\n{verifier(d, 40)}\n')


def build(key: str) -> str:
    d = os.path.join(RAW, key)
    meta = json.load(open(os.path.join(d, "trial.json")))
    try:
        traj = json.load(open(os.path.join(d, "agent/trajectory.json")))
    except (OSError, ValueError):
        return f"{key}: no trajectory"
    ev, _ = atif.events(traj, atif.request_times(meta["detail"]))
    instruction = atif.instruction(traj)
    sig = features.feature_row(key) or {}
    open(os.path.join(d, "skeleton.md"), "w").write(skeleton(meta, ev, d, instruction, sig))
    open(os.path.join(d, "timeline.md"), "w").write(timeline(meta, ev, d, instruction, sig))
    return f'{key}: skeleton {os.path.getsize(os.path.join(d, "skeleton.md")) // 1000} KB, timeline {os.path.getsize(os.path.join(d, "timeline.md")) // 1000} KB'


if __name__ == "__main__":
    for k in sys.argv[1:]:
        print(build(k))
