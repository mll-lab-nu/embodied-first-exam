"""Remove RoboTwin's built-in reference solutions from the image so agents cannot look them up.

Every task class in envs/<task>.py ships an expert `play_once` (plus helpers such as `pick_and_place_block`).
Keep only the scene definition and the success predicate: `setup_demo`, `load_actors`, `check_success` and
whatever those call; every other method body becomes `raise NotImplementedError("scrubbed")`.
Also deletes code_gen/ (LLM prompts with worked task solutions), description/, XPolicyLab/.
Fails loudly if a `play_once` body survives."""
import ast, pathlib, re, shutil, sys

root = pathlib.Path("/opt/RoboTwin")
KEEP = {"setup_demo", "load_actors", "check_success", "__init__"}


def self_calls(fn: ast.FunctionDef) -> set[str]:
    out = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self":
            out.add(n.attr)
    return out


scrubbed, files = [], 0
for p in sorted((root / "envs").glob("*.py")):
    if p.name.startswith("_"):
        continue
    src = p.read_text(); tree = ast.parse(src); lines = src.splitlines(keepends=True)
    edits = []
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef)]:
        fns = {f.name: f for f in cls.body if isinstance(f, ast.FunctionDef)}
        keep, todo = set(), list(KEEP)
        while todo:  # transitive closure of self.<method> references from the kept methods
            k = todo.pop()
            if k in keep or k not in fns:
                continue
            keep.add(k); todo.extend(self_calls(fns[k]))
        for name, f in fns.items():
            if name in keep:
                continue
            body_start = f.body[0].lineno - 1  # first statement (docstring included) -> replaced
            body_end = f.end_lineno
            indent = re.match(r"\s*", lines[body_start]).group(0)
            edits.append((body_start, body_end, f'{indent}raise NotImplementedError("scrubbed: reference solution removed")\n'))
            scrubbed.append(f"{p.name}:{name}")
    if edits:
        for s, e, rep in sorted(edits, reverse=True):
            lines[s:e] = [rep]
        p.write_text("".join(lines)); files += 1

for d in ["code_gen", "description", "XPolicyLab", "assets/files", "policy"]:  # data/ = image codec, imported by envs
    shutil.rmtree(root / d, ignore_errors=True)

left = []
for p in (root / "envs").glob("*.py"):
    if p.name.startswith("_"):
        continue
    for cls in [n for n in ast.parse(p.read_text()).body if isinstance(n, ast.ClassDef)]:
        for f in cls.body:
            if isinstance(f, ast.FunctionDef) and f.name == "play_once" and not (
                len(f.body) == 1 and isinstance(f.body[0], ast.Raise)):
                left.append(f"{p.name}:play_once")
print(f"scrubbed {len(scrubbed)} methods in {files} files: {scrubbed}\nleftovers: {left}")
sys.exit(1 if left else 0)
