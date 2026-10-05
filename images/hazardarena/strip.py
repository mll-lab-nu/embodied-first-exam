"""Reduce a HazardArena checkout to its simulation engine for the eai-hazardarena image.

What the image must not carry is everything that tells a SAFE twin from an UNSAFE one, plus the reference solutions:
- the twin and inventory scene builders (`safety_twin_tasks/`, `semantic_safety_tasks/`): per variant they hold the
  request text, the SAFE/UNSAFE label, the risk tags, the scene recipe and the scripted expert;
- `risk_task.json` (the 51-scenario inventory, every one UNSAFE) and the registry in `configs/__init__.py` that reads it;
- the evaluation code and configs (`evaluation/`: stage predicates, evaluator, VLM gate, policy adapters;
  `configs/evaluation/`: tracks of seeds and conditions per task; `configs/sol/`: the gate's prompts);
- the per-task entries of `configs/task_config.json` (family names and scene choices; only `default` stays);
- every method named `get_expert_skill_sequence` that is left (task and environment base classes);
- dataset conversion and teleoperation helpers, the documentation, scripts, tests, packaging and checksum files
  (`SHA256SUMS` lists every file above), `.git`.
What stays is the engine: environments, robots, scene components and their assets, the generic condition classes, the
skill library and its planners. A task's scene (components, poses, request, success conditions) comes from its frozen
instance, built by the task's own tooling, which registers a single neutral scene class.

    python strip.py /opt/HazardArena          # the repository root; idempotent
"""

import ast
import json
import shutil
import sys
from pathlib import Path

root = Path(sys.argv[1])
pkg = root / "HazardArena"
DROP = [
    "HazardArena/tasks/hierarchical_tasks/primitive/safety_twin_tasks",
    "HazardArena/tasks/hierarchical_tasks/primitive/semantic_safety_tasks",
    "HazardArena/evaluation",
    "HazardArena/configs/evaluation",
    "HazardArena/configs/sol",
    "HazardArena/utils/rlds_builder.py",
    "HazardArena/utils/multithread_rlds_builder.py",
    "HazardArena/utils/interface.py",
    "risk_task.json",
    "docs",
    "scripts",
    "tests",
    "README.md",
    "CITATION.cff",
    "SHA256SUMS",
    "MANIFEST.in",
    "setup.py",
    "requirements.txt",
    ".gitignore",
    ".git",
]
REWRITE = {
    "HazardArena/tasks/hierarchical_tasks/primitive/__init__.py": (
        '"""Primitive task base classes. Scene builders are not part of this image: a task registers its own."""\n'
    ),
    "HazardArena/configs/__init__.py": (
        '"""Task series registry (load_env looks a task\'s series up here): empty in this image; a frozen scene carries\n'
        'its own configuration."""\n\nname2config = {}\n'
    ),
}

for p in list(root.rglob("__pycache__")):  # compiled copies of what is removed would keep it
    shutil.rmtree(p)
for rel in DROP:
    p = root / rel
    if p.is_dir():
        shutil.rmtree(p)
    elif p.exists():
        p.unlink()
for rel, text in REWRITE.items():
    (root / rel).write_text(text)
cfg = pkg / "configs/task_config.json"
cfg.write_text(json.dumps({"default": json.loads(cfg.read_text())["default"]}, indent=2) + "\n")

count = 0
for path in sorted(pkg.rglob("*.py")):
    text = path.read_text()
    spans = [
        (node.lineno, node.end_lineno)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_expert_skill_sequence"
    ]
    if not spans:
        continue
    lines = text.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        indent = lines[start - 1][: len(lines[start - 1]) - len(lines[start - 1].lstrip())]
        lines[start - 1 : end] = [indent + "# Expert skill sequences are not part of this image.\n"]
    result = "".join(lines)
    ast.parse(result)
    path.write_text(result)
    count += len(spans)

# Nothing that remains may name what was removed.
words = ("safety_twin", "semantic_safety", "risk_task", "stage_predicates", "UNSAFE", "def get_expert_skill_sequence")
texts = {p: p.read_text(errors="ignore") for p in root.rglob("*") if p.is_file() and p.suffix in (".py", ".json")}
left = sorted(f"{p.relative_to(root)}: {w}" for p, t in texts.items() for w in words if w in t)
assert not left, left
print(f"removed {count} expert methods; kept {sum(1 for _ in pkg.rglob('*.py'))} engine modules")
