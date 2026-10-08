#!/usr/bin/env python3
"""Check an exported RoboTangle image context against scripts/robotangle/release.json: the public simulator source (what
images/topogym/prune.py keeps and hashes into SOURCE.json) and the audited uipc-build.json. Standard library only.
usage: python3 scripts/robotangle/check_context.py images/robotangle/context"""
import ast, hashlib, json, pathlib, sys

OMIT = {"agents", "planning", "data", "deferred", "legacy", "redundants", "rollout_simulation", "__pycache__"}


def public_source(ctx: pathlib.Path) -> dict:
    files = {}
    for p in sorted((ctx / "topogym").rglob("*")):
        rel = p.relative_to(ctx).as_posix()
        if not p.is_file() or set(p.relative_to(ctx).parts[1:-1]) & OMIT or p.suffix in (".md", ".pyc") or "__pycache__" in p.parts:
            continue
        data = p.read_bytes()
        if rel == "topogym/assets/geometry/cast_coil.py":   # prune.py drops the authoring-only `synthesize`
            src = data.decode(); lines = src.splitlines(keepends=True)
            for node in ast.parse(src).body:
                if isinstance(node, ast.FunctionDef) and node.name == "synthesize":
                    lines = lines[:node.lineno - 1] + lines[node.end_lineno:]; break
            data = "".join(lines).encode()
        files[rel] = hashlib.sha256(data).hexdigest()
    return {"sha256": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(), "files": len(files)}


def main() -> int:
    ctx = pathlib.Path(sys.argv[1])
    rel = json.loads((pathlib.Path(__file__).resolve().parent / "release.json").read_text())
    rt = rel["runtime"]
    bad = []
    src = public_source(ctx)
    if src != rt["source"]:
        bad.append(f"public source {src} != bound {rt['source']}")
    uj = ctx / "images/topogym/uipc-prebuilt/uipc-build.json"
    if not uj.is_file() or hashlib.sha256(uj.read_bytes()).hexdigest() != rt["uipc_build_sha256"]:
        bad.append(f"{uj}: missing or not the audited uipc-build.json ({rt['uipc_build_sha256'][:12]}…)")
    # the per-arch libuipc builds (release.json uipc_builds): the default one is the audited wheel above; a build with its
    # own prefix is in the context as its dataset folder without "image/" (fetch_image_context.sh: image/uipc-sm86 -> uipc-sm86)
    for arch, b in sorted(rel.get("uipc_builds", {}).items()):
        bj = ctx / b["dataset"].removeprefix("image/") / "uipc-build.json" if b.get("prefix") else uj
        if not bj.is_file() or hashlib.sha256(bj.read_bytes()).hexdigest() != b["uipc_build_sha256"]:
            bad.append(f"{bj}: missing or not the {arch} uipc-build.json ({b['uipc_build_sha256'][:12]}…)")
    for b in bad:
        print("FAIL", b)
    if not bad:
        print(f"ok context: source {src['sha256'][:12]} ({src['files']} files), uipc-build.json {rt['uipc_build_sha256'][:12]}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
