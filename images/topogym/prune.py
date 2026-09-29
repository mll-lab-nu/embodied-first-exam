"""Build step of images/topogym: keep the simulator, drop everything that could hold a solution, record the source hash.

    python prune.py /opt/topogym

The image is infrastructure only (docs/rcb/PROTOCOL.md §1, §4): the agent must not find a reference motion in it. Removed:
topogym/{agents,planning,data,deferred,legacy,redundants,rollout_simulation} (scripted policies, recorded runs; also left
out by .dockerignore) and the authoring-only `synthesize` of topogym/assets/geometry/cast_coil.py, which embeds a
reference motion (runtime tasks build the frozen geometry from templates and never call it). SOURCE.json = sha256 of every
remaining file, so an instance records which simulator source built it."""
import ast, hashlib, json, pathlib, shutil, sys

root = pathlib.Path(sys.argv[1])
pkg = root / "topogym"
for d in ("agents", "planning", "data", "deferred", "legacy", "redundants", "rollout_simulation"):
    for p in pkg.rglob(d):
        if p.is_dir():
            shutil.rmtree(p)
coil = pkg / "assets/geometry/cast_coil.py"
src = coil.read_text(); lines = src.splitlines(keepends=True)
for node in ast.parse(src).body:
    if isinstance(node, ast.FunctionDef) and node.name == "synthesize":
        lines = lines[:node.lineno - 1] + lines[node.end_lineno:]
        break
coil.write_text("".join(lines))
files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
         for p in sorted(pkg.rglob("*")) if p.is_file() and "__pycache__" not in p.parts}
digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
(root / "SOURCE.json").write_text(json.dumps({"sha256": digest, "files": len(files)}, indent=1))
print(f"topogym source {digest[:16]} ({len(files)} files)")
