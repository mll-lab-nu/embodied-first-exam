#!/usr/bin/env bash
# instruction.md never leaks the verifier's /tests/ copy, and a privileged one names the deliverable under /app/output/
# (a standard mode has no deliverable: the service grades the live episode).
# Standard modes (the sidecar modes of the mode registry; docs/protocol/tasks.md#instructionmd, "written in terms the agent can observe"): the
# instruction's prose names no code-like term on its own: an object-local axis (`local +y`), a predicate function
# (`is_A_in_B`, `all_robot_back_to_origin`), a label with an index suffix (`cube_0`, `mahjong9_0`) or a bare indexed label
# (`block3`), asset metadata (`place_tag`, `model_id`, `category_idx`, a model / category index) or an asset point
# (`'block/0'`, a support / functional / reference point). Such a term passes where a physical description sits next to it:
# inside a short bracket after the description ("the keyboard's short edge [local y]"), directly followed by one ("local +x
# (the face that faced the robot at the start)"), or defined once in the text (`label = ...`, `label: ...`, a bracketed or
# described first use, an object named by where it starts: "ball1 in the lane on the left"), which then covers its later
# uses. Code spans, fenced blocks, headings and a bold `**Task: ...**` sentence (the upstream benchmark's own words) are
# not read. Findings are advisory (a pattern only sees words; review covers the rest).
t="$1"; rc=0
grep -q '/tests/' "$t/instruction.md" && { echo "FAIL $t: instruction.md must not reference /tests/"; rc=1; }
modes="${RCB_MODES_TABLE:-$(python3 "$(dirname "$0")/../scripts/task_conventions.py" modes)}"
n="$(basename "${t%/}")"; side=0
while read -r m sidecar _tw; do [ -n "$m" ] && [[ "$n" == *"-$m" ]] && { side="$sidecar"; break; }; done <<< "$modes"
# the deliverable: privileged mode only (a standard mode has none: the service grades the live episode)
[ "$side" = 1 ] || grep -q '/app/output/' "$t/instruction.md" || {
  echo "FAIL $t: a privileged instruction must state the deliverable under /app/output/"; rc=1; }
[ "$side" = 1 ] && grep -q '/app/output/gen\.py' "$t/instruction.md" && {
  echo "FAIL $t: a standard instruction asks for no script (/app/output/gen.py): the service grades the live episode"; rc=1; }
[ "$side" = 1 ] || exit $rc
python3 - "$t" <<'PY' || rc=1
import re, sys
from pathlib import Path
t = Path(sys.argv[1])
ROBOT = r"(?:palm|hand|wrist|gripper|tcp|ee|link|base|camera|cam|robot|arm|finger|world|table)"
NOT_LABEL = (r"(?:float|uint|int|sha|link|joint|arm|cam|finger|rgb|rgba|utf|mp|md|yuv|mjpeg|sec|top|step|fps|ipv|base|torso|"
             r"head|chunk|stage|seed|panda|ur|gen|gpt|python|cuda|py|eai|aim|version|bigym|phase|overhead)\d")
PATTERNS = [
    ("an object-local axis", re.compile(r"(?<![\w-])(?:(?!" + ROBOT + r"-)[A-Za-z]+-)?local\s+[+-]?[xyzXYZ](?!\w)")),
    ("a predicate function", re.compile(r"\b(?:is|check)_[A-Za-z_]+\b|\ball_robot_[a-z_]+\b")),
    ("asset metadata", re.compile(r"\b(?:place_tag|model_id|category_idx|model index|category index)\b")),
    ("an asset point", re.compile(r"'[A-Za-z_]+/\d+'|\b(?:support|functional|reference|active|passive) point\b")),
    ("an indexed label", re.compile(r"\b[a-z]+\d*_\d+\b")),
    ("a bare indexed label", re.compile(r"\b(?!" + NOT_LABEL + r")[a-z]{3,}\d{1,2}\b")),
]
def blank(m):
    return re.sub(r"[^\n]", " ", m.group(0))
text = (t / "instruction.md").read_text(encoding="utf-8")
text = re.sub(r"(?ms)^```.*?^```[^\n]*$", blank, text)          # fenced blocks: code
text = re.sub(r"`[^`\n]*`", blank, text)                          # code spans: the API's own names
text = re.sub(r"(?m)^#.*$|\*\*Task:[^*\n]+\*\*", blank, text)       # headings, an upstream task sentence in bold
def bracketed(s, e):        # inside a short (...) or [...] after a description
    for o, c in (("(", ")"), ("[", "]")):
        i, j = text.rfind(o, max(0, s - 80), s), text.find(c, e, e + 120)
        before = text[:i].rstrip()[-1:]
        if i != -1 and j != -1 and text.find(c, i, s) == -1 and text.find(o, e, j) == -1 and (before.isalnum() or before in "*)'\""):
            return True
    return False
def described(kind, s, e):  # directly followed by a description in brackets, or defined here (`x = ...`, `x: ...`; a label
    after = text[e:e + 160]   # also by where it starts, `ball1 in the lane ...`)
    if "label" in kind and re.match(r"\s+(?:in|on|at) the\b", after):
        return True
    return bool(re.match(r"(?:\s*axis)?\s*(?:\([^)]{6,}\)|\[[^\]]{6,}\]|=|:\s)", after))
hits, defined = [], set()
for kind, rx in PATTERNS:
    for mm in rx.finditer(text):
        key = re.sub(r"[\s+-]+", " ", mm.group(0).lower()).strip()   # "local +x" and "local x": one term
        if bracketed(mm.start(), mm.end()) or described(kind, mm.start(), mm.end()):
            defined.add(key)
        else:
            hits.append((kind, key, mm.start(), mm.end()))
bad = [h for h in hits if h[1] not in defined]
if bad:
    print(f"FAIL {t}: the standard-mode instruction names code-like terms without a physical description next to them "
          "(docs/protocol/tasks.md#instructionmd: name objects by appearance or starting place, describe axes and points physically, upstream "
          "identifiers only in brackets after that):")
    for kind, key, s, e in bad[:12]:
        line = text[:s].count("\n") + 1
        print(f"  - instruction.md:{line}: {kind} '{key}': ...{' '.join(text[max(0, s - 50):e + 30].split())}...")
    if len(bad) > 12:
        print(f"  ... {len(bad) - 12} more")
    sys.exit(1)
PY
exit $rc
