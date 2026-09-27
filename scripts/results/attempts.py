"""What each robot-driving tool call tried: what it ran, and what changed since the one before it (the command
itself, or the files it runs as written or patched in between), read from the agent's own log. Code only, no model:
collect.py stores the result per call in summary.json and session_video.py shows it."""
from __future__ import annotations

import difflib
import json
import os
import re

from calls import shell_heads

HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
WRITES = re.compile(r"\b(?:cat|tee)\b[^|&;]*?(?:>\s*|tee\s+(?:-a\s+)?)([\w./-]+)")   # cat > f <<X, cat <<X > f, tee f
RUNS = re.compile(r"\bpython[\d.]*\s+(?:-u\s+)?([\w./-]+\.py)\b")                   # python f.py args
STDIN = re.compile(r"\bpython[\d.]*(?:\s+-[A-Za-z]+)*\s+-(\s|$)")                        # python - <<X
PATCH = re.compile(r'"((?:[^"\\]|\\.)*?\*\*\* Begin Patch(?:[^"\\]|\\.)*)"|`([^`]*\*\*\* Begin Patch[^`]*)`', re.S)
TOKEN = re.compile(r"[A-Za-z_]\w*|-?\d*\.?\d+(?:[eE][-+]?\d+)?|\S")
NOISE = re.compile(r"^\s*(#|import |from \S+ import |print\(|\$ ?$|\$ .*<<-?\s*['\"]?\w+['\"]?\s*$|$)")
KEEP = 4   # changes shown per call


def heredocs(cmd: str) -> tuple[list[str], list[tuple[str, list[str]]]]:
    """A shell command's own lines, and (the line that opens it, its body) for each heredoc in it."""
    shell, docs, lines, i = [], [], cmd.splitlines(), 0
    while i < len(lines):
        shell.append(lines[i])
        m = HEREDOC.search(lines[i])
        if m:
            end = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == m.group(1)), len(lines))
            docs.append((lines[i], lines[i + 1:end])); i = end
        i += 1
    return shell, docs


def patch(files: dict, text: str) -> list[str]:
    """Apply one codex patch (*** Begin Patch ... *** End Patch) to the known file contents; the files it touched.
    A hunk that does not match what is known leaves that file unknown (None)."""
    touched = []
    for sec in re.split(r"^\*\*\* (?=(?:Add|Update|Delete) File: )", text, flags=re.M)[1:]:
        head, *body = sec.splitlines()
        how, path = head.split(" File: ", 1)
        name = os.path.basename(path.strip()); touched.append(name)
        if how == "Add":
            files[name] = [ln[1:] for ln in body if ln.startswith("+")]
        elif how == "Delete":
            files.pop(name, None)
        elif files.get(name) is not None:
            hunks = [[]]
            for ln in body:   # "@@ <context header>" starts a hunk; its rows are " " context, "-" and "+"
                if ln.startswith("@@"):
                    hunks.append([])
                elif not ln.startswith("*** "):
                    hunks[-1].append(ln if ln else " ")
            for rows in (h for h in hunks if h):
                old = [ln[1:] for ln in rows if ln[0] != "+"]; new = [ln[1:] for ln in rows if ln[0] != "-"]
                cur = files[name]
                at = next((k for k in range(len(cur) - len(old) + 1) if [c.rstrip() for c in cur[k:k + len(old)]] == [o.rstrip() for o in old]), None)
                if at is None:
                    files[name] = None; break
                files[name] = cur[:at] + new + cur[at + len(old):]
    return touched


def track(files: dict, x: dict) -> list[str]:
    """Update the known file contents with what one call wrote; the files it wrote."""
    touched = []
    for w in x.get("writes") or []:   # Claude Code's Write / Edit, as claude_session keeps them
        name = os.path.basename(w["path"]); touched.append(name)
        if "content" in w:
            files[name] = w["content"].splitlines()
        elif files.get(name) is not None and w["old"] in "\n".join(files[name]):
            files[name] = "\n".join(files[name]).replace(w["old"], w["new"], 1).splitlines()
        else:
            files[name] = None
    for m in PATCH.finditer(x["text"]):   # codex's apply_patch: the patch is a JS string in its code
        try:
            body = json.loads(f'"{m.group(1)}"') if m.group(1) is not None else m.group(2)
        except ValueError:
            continue
        touched += patch(files, body)
    for cmd in x.get("cmds") or []:
        shell, docs = heredocs(cmd)
        for opener, body in docs:
            if (m := WRITES.search(opener)):
                name = os.path.basename(m.group(1)); touched.append(name)
                files[name] = ((files.get(name) or []) + body) if ">>" in opener or "tee -a" in opener else body
    return touched


def script(x: dict, files: dict) -> tuple[str, list[str]]:
    """What one call ran, in one line, and as lines to compare: the command lines, the Python it piped in, and the
    files it ran as last written."""
    lines, what, ran = [], [], set()
    for cmd in x.get("cmds") or [x.get("label") or ""]:
        shell, docs = heredocs(cmd)
        lines += ["$ " + ln.strip() for ln in shell if ln.strip()]
        for opener, body in docs:
            if STDIN.search(opener) and not WRITES.search(opener):
                lines += body; what.append(f"inline Python, {len(body)} lines")
        for ln in shell:
            for path in RUNS.findall(ln):
                name = os.path.basename(path)
                if name not in ran:
                    ran.add(name); lines += files.get(name) or []
                what.append(re.sub(r"^.*?(python[\d.]*\s)", r"\1", ln.strip()).replace(path, name))
    py = next((ln.strip() for cmd in x.get("cmds") or [] for ln in heredocs(cmd)[0] if re.search(r"\bpython", ln)), "")
    return " · ".join(dict.fromkeys(what)) or py[:160] or (x.get("label") or "").splitlines()[0][:160], lines


def context(a: str, at: int) -> tuple[str, str]:
    """What stands before position `at`: the code back to the start of its statement or argument, brackets skipped
    (`q0[[4,9]]-=`, `left_hip_pitch=`), and the call it is an argument of (`range`), if any."""
    def back(stop: str) -> int:
        depth = 0
        for k in range(at - 1, -1, -1):
            if a[k] in ")]}":
                depth += 1
            elif a[k] in "([{":
                if depth == 0:
                    return k
                depth -= 1
            elif depth == 0 and a[k] in stop:
                return k
        return -1
    k, j = back(";,"), back("")
    call = re.search(r"([A-Za-z_][\w.]*)\s*$", a[:j]) if j >= 0 and a[j] == "(" else None
    return a[k + 1:at].strip().strip("'\"")[-24:], call.group(1) if call else ""


def balanced(t: str) -> bool:
    """Brackets that open before they close, all of them: a piece of code, not a cut through it."""
    depth = 0
    for ch in t:
        depth += (ch in "([{") - (ch in ")]}")
        if depth < 0:
            return False
    return depth == 0


def token_changes(a: str, b: str) -> list[tuple[str, bool]]:
    """One edited line as its edited pieces, each after the code just before it: `q0[[4,9]]-=.067 → .05`,
    `40 → 100  in step()`, `+ piece` added, `− piece` removed; and whether that code names what changed."""
    ta, tb = [(m.group(), m.start(), m.end()) for m in TOKEN.finditer(a)], [(m.group(), m.start(), m.end()) for m in TOKEN.finditer(b)]
    text = lambda s, t, i, j: s[t[i][1]:t[j - 1][2]].strip(" ,;") if j > i else ""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, [t[0] for t in ta], [t[0] for t in tb], autojunk=False).get_opcodes():
        old, new = text(a, ta, i1, i2), text(b, tb, j1, j2)
        if op == "equal" or not (old or new):
            continue
        ctx, call = context(a, ta[i1][1] if i1 < len(ta) else len(a))
        named = re.search(r"([A-Za-z_][\w.]*(?:\[[^\]]*\]+)*\s*[-+*/]?=\s*)$", ctx)   # an assignment or a keyword argument
        out.append((f"+ {new}" if not old else f"− {old}" if not new else
                    f"{named.group(1)}{old} → {new}" if named else f"{old} → {new}" + (f"  in {call}()" if call else ""),
                    balanced(old) and balanced(new) and bool(named or call or re.search(r"[A-Za-z_]", old + new) and not (old and new))))
    return out


def similar(a: str, b: str) -> float:
    m = difflib.SequenceMatcher(None, a, b, autojunk=False)
    return m.ratio() if m.real_quick_ratio() >= 0.5 and m.quick_ratio() >= 0.5 else 0.0


def changes(a: list[str], b: list[str]) -> list[list[str]]:
    """What differs from a to b, the most telling first: a line that was edited as its edited pieces ("~"),
    otherwise whole lines added ("+") or removed ("-"); imports, prints, comments and blank lines only if nothing
    else changed, and pieces with a number before the rest."""
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        olds = list(a[i1:i2])
        for n in b[j1:j2]:
            best = max(range(len(olds)), key=lambda k: similar(olds[k], n), default=None)
            if best is not None and similar(olds[best], n) >= 0.5:   # an edit of that line
                o = olds.pop(best)
                pieces = token_changes(o, n)
                readable = [p for p, ok in pieces if ok]
                if readable or len(pieces) <= 2:   # the pieces that say what changed, else the two lines
                    out += [["~", p, n] for p in readable or [p for p, _ in pieces]]
                else:
                    out += [["-", o.strip(), o], ["+", n.strip(), n]]
            else:
                out.append(["+", n.strip(), n])
        out += [["-", o.strip(), o] for o in olds]
    telling = [c for c in out if not NOISE.match(c[2])] or out
    ranked = list({c[1]: c for c in sorted(telling, key=lambda c: not re.search(r"\d", c[1]))}.values())   # each once
    return [c[:2] for c in ranked[:KEEP]] + ([["…", f"{len(ranked) - KEEP} more"]] if len(ranked) > KEEP else [])


def describe(calls: list[dict], robots: list[dict]) -> list[dict | None]:
    """Per call (None for one that did not move the robot): its number among the calls that did, what it ran, the
    files written since the last one, and what changed since the last one."""
    files, out, prev, n, since = {}, [], None, 0, []
    moved = lambda r: r.get("steps") or r.get("resets") or (r.get("after") or {}).get("steps")
    python = lambda x: any(h.startswith("python") or h.endswith(".py") for c in x.get("cmds") or [] for h, _ in shell_heads(c))
    for x, r in zip(calls, robots):
        since += track(files, x)
        if not (moved(r) and python(x)):   # a read or a patch made while a script drives the robot is no attempt
            out.append(None)
            continue
        n += 1
        what, lines = script(x, files)
        a = {"n": n, "runs": what[:160], "edited": list(dict.fromkeys(since))}
        if prev is not None:
            a["same"] = lines == prev
            new = difflib.SequenceMatcher(None, prev, lines, autojunk=False).ratio() < 0.35   # little in common: a new script
            a["changes"] = [] if a["same"] else changes(prev, lines)
            if new:   # its own lines with numbers in them say more than a diff against another script
                a["changes"] = [["*", f"a new script, {len(lines)} lines"]] + [c for c in a["changes"] if c[0] == "+" and not c[1].startswith("$ ")][:KEEP - 1]
        out.append(a); prev, since = lines, []
    return out
