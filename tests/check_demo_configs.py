"""Static checks on the demos' Hydra wiring. No GPU, no Genesis, no hydra package.

Written after the 2026-08-10 Hydra migration, where two defect classes each got
through `python -m compileall` and through a `--cfg job` run, and only showed up
when someone actually ran the demo on a GPU:

- a name left behind by a half-applied edit. Migration turned
  `run_demo(args, cfg, ...)` into `run_demo(cfg, ...)`; two demos kept the
  parameter and the call-site argument, so `args` resolved to nothing. It raises
  only when execution reaches that line -- after the scene is built.
- `OmegaConf.merge` adding a key the config never had. Hydra hands `main` a
  config with `struct=True`, which rejects new keys; the config path it replaced
  never set that flag, so demos had been adding keys at runtime that no yaml
  contained.

Both are decidable without running anything, so they are decided here.

    python tests/check_demo_configs.py
    python tests/check_demo_configs.py --verbose

Exits non-zero if any hard check fails. Needs only the standard library + PyYAML,
so it runs on any interpreter, including one without the project's deps.

WHAT THIS DOES NOT COVER, and why:

- `getattr(handle_cfg, "rho", 700.0)` with a misspelled key. It does not raise;
  it silently takes the default.
- a migrated parameter given the wrong default. `run.settle_steps: 60` being
  wrong is not a statically decidable property.
- physics. Rope flyout, failed grasps, drifting routes -- run the demo, or
  `bash_scripts/tests/stability_sweep.sh` for a batch.

Config composition and interpolation resolution are checked separately by
`tests/check_configs_compose.py`, which needs the hydra package.
"""

from __future__ import annotations

import argparse
import ast
import builtins
import re
import symtable
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
CONFIGS = REPO / "configs"
DEMOS = REPO / "demos"

# Config groups whose option is chosen in a defaults list, and the package each
# lands on. Keys of merged dicts are checked against whichever yaml these resolve to.
GROUPS = (("task_configs", "task"), ("env_configs", "env"), ("robot_control_configs", "robot_control"))

# Module-level dunders are bound by the import machinery, not by any statement
# symtable can see, so they read as undefined inside functions.
DUNDER_OK = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__loader__"}

# The migration shape every mainline demo should have.
SHAPE = (
    ("@hydra.main", lambda s: bool(re.search(r'@hydra\.main\(version_base="1\.3", config_path="\.\./\.\./configs"', s))),
    ("main(cfg)", lambda s: "def main(cfg: DictConfig)" in s),
    ("save_resolved", lambda s: "save_resolved_config(cfg)" in s),
    ("recording覆盖", lambda s: "apply_recording_camera_overrides(cfg)" in s or "cfg.recording" not in s),
    ("__main__", lambda s: bool(re.search(r'if __name__ == "__main__":\n    main\(\)', s))),
    ("提前退出", lambda s: "stop_before_physics(cfg" in s),
    ("无旧体系残留", lambda s: not re.search(r"\bargs\b|argparse|parse_args|merge_recording_config|load_topogym_configs", s)),
)


# --- config resolution -------------------------------------------------------


def yaml_keys(data, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            keys.add(prefix + str(key))
            keys |= yaml_keys(value, f"{prefix}{key}.")
    return keys


def defaults_of(path: Path) -> list:
    return yaml.safe_load(path.read_text(encoding="utf-8")).get("defaults", [])


def group_options(primary: Path) -> dict[str, tuple[str, str]]:
    """Which yaml each config group resolves to for this primary config.

    A primary config overrides some groups; the rest fall through to `config.yaml`.
    """
    chosen: dict[str, tuple[str, str]] = {}
    for defaults in (defaults_of(primary), defaults_of(CONFIGS / "config.yaml")):
        for entry in defaults:
            if not isinstance(entry, dict):
                continue
            for key, option in entry.items():
                for group, package in GROUPS:
                    if group in key and package not in chosen:
                        chosen[package] = (group, str(option))
    return chosen


def run_config_keys(option: str, seen: set[str] | None = None) -> set[str]:
    """Keys a run_configs option provides, following its `defaults` inheritance."""
    seen = seen if seen is not None else set()
    if option in seen:
        return set()
    seen.add(option)
    data = yaml.safe_load((CONFIGS / "run_configs" / f"{option}.yaml").read_text(encoding="utf-8"))
    keys: set[str] = set()
    for entry in data.get("defaults", []):
        if isinstance(entry, str) and entry != "_self_":
            keys |= run_config_keys(entry, seen)
    keys |= {k for k in data if k != "defaults"}
    return keys


def run_option_of(primary: Path) -> str:
    for defaults in (defaults_of(primary), defaults_of(CONFIGS / "config.yaml")):
        for entry in defaults:
            if isinstance(entry, dict):
                for key, option in entry.items():
                    if "run_configs" in key:
                        return str(option)
    return "default"


# --- the four checks ---------------------------------------------------------


def undefined_names(src: str, path: Path) -> list[str]:
    top = symtable.symtable(src, str(path), "exec")
    module_names = {s.get_name() for s in top.get_symbols()}
    known = module_names | set(dir(builtins)) | DUNDER_OK
    found: list[str] = []

    def walk(table, chain: str) -> None:
        for sym in table.get_symbols():
            name = sym.get_name()
            if not sym.is_referenced():
                continue
            if sym.is_local() or sym.is_parameter() or sym.is_free() or sym.is_imported():
                continue
            if name in known:
                continue
            found.append(f"{chain} -> {name}")
        for child in table.get_children():
            walk(child, f"{chain}.{child.get_name()}")

    for child in top.get_children():
        walk(child, child.get_name())
    return found


def dict_key_paths(node: ast.AST, prefix: str = "") -> set[str]:
    """Key paths of an ast.Dict literal, ignoring whether the values are literals."""
    paths: set[str] = set()
    if isinstance(node, ast.Dict):
        for key, value in zip(node.keys, node.values):
            if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                continue
            paths.add(prefix + key.value)
            paths |= dict_key_paths(value, prefix + key.value + ".")
    return paths


def merged_new_keys(tree: ast.AST, available: dict[str, set[str]]) -> list[str]:
    bad: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "merge"):
            continue
        for arg in node.args[1:]:
            for path in dict_key_paths(arg):
                package, _, rest = path.partition(".")
                if rest and package in available and rest not in available[package]:
                    bad.append(f"{path}  (第 {node.lineno} 行)")
    return bad


def attr_chain(node: ast.Attribute) -> str | None:
    parts: list[str] = []
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name) and current.id == "cfg":
        return ".".join(reversed(parts))
    return None


def cfg_chains(tree: ast.AST, section: str) -> set[str]:
    """Maximal `cfg.<section>....` attribute chains (drop prefixes of longer ones)."""
    found = {
        chain
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        for chain in [attr_chain(node)]
        if chain and chain.startswith(section + ".")
    }
    return {c for c in found if not any(o != c and o.startswith(c + ".") for o in found)}


# --- driver ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--verbose", action="store_true", help="Also list the warning-level findings.")
    args = parser.parse_args()

    demos = sorted(p for p in DEMOS.rglob("*.py") if "__pycache__" not in str(p))
    if not demos:
        raise SystemExit(f"没有找到任何 demo：{DEMOS}")

    failures: list[str] = []
    warnings: list[str] = []
    shape_rows: list[tuple[str, list[bool]]] = []

    for path in demos:
        src = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO).as_posix()
        try:
            tree = ast.parse(src, str(path))
        except SyntaxError as error:
            failures.append(f"{rel}: 语法错误 {error}")
            continue

        match = re.search(r'config_name="(.*?)"', src)
        if match is None:
            failures.append(f"{rel}: 没有 @hydra.main 的 config_name")
            continue
        primary = CONFIGS / f"{match.group(1)}.yaml"
        if not primary.exists():
            failures.append(f"{rel}: 主配置不存在 {primary.relative_to(REPO).as_posix()}")
            continue

        # 1. 未定义名
        for hit in undefined_names(src, path):
            failures.append(f"{rel}: 未定义名 {hit}")

        # 2. merge 往 struct 配置里加新键
        available = {
            package: yaml_keys(
                yaml.safe_load((CONFIGS / group / f"{option}.yaml").read_text(encoding="utf-8"))
            )
            for package, (group, option) in group_options(primary).items()
        }
        for hit in merged_new_keys(tree, available):
            failures.append(f"{rel}: merge 加了配置里没有的键 {hit}")

        # 3. cfg.run.X 在该 demo 的 run 配置链里
        provided = run_config_keys(run_option_of(primary))
        for name in sorted(set(re.findall(r"cfg\.run\.([a-z_]+)", src)) - provided):
            failures.append(f"{rel}: run 配置里没有 run.{name}")

        # 4. 迁移形态
        shape_rows.append((path.stem, [ok(src) for _, ok in SHAPE]))

        # 警告级：cfg.task.* / cfg.env.* 指向配置里没有的键。DictConfig 的方法
        # （.get/.keys/...）和有 `in` 前置判断的访问都会误报，所以不计入失败。
        for package in ("task", "env"):
            if package not in available:
                continue
            for chain in sorted(cfg_chains(tree, package)):
                rest = chain.partition(".")[2]
                if rest and rest not in available[package]:
                    warnings.append(f"{rel}: cfg.{chain} 在配置里查无")

    print("== 迁移形态 ==")
    width = max(len(name) for name, _ in shape_rows)
    print(f"{'demo'.ljust(width)}  " + "  ".join(label for label, _ in SHAPE))
    for name, flags in shape_rows:
        cells = ["Y".center(len(label)) if ok else "-".center(len(label)) for (label, _), ok in zip(SHAPE, flags)]
        print(f"{name.ljust(width)}  " + "  ".join(cells))

    if warnings:
        print()
        print(f"== 警告 {len(warnings)} 条（不计入失败）==")
        for line in warnings if args.verbose else warnings[:5]:
            print(f"  {line}")
        if not args.verbose and len(warnings) > 5:
            print(f"  ... 其余 {len(warnings) - 5} 条用 --verbose 查看")

    print()
    if failures:
        print(f"== 失败 {len(failures)} 项 ==")
        for line in failures:
            print(f"  {line}")
        sys.exit(1)
    print(f"== 通过：{len(demos)} 个 demo，四项检查全部无命中 ==")


if __name__ == "__main__":
    main()
