#!/usr/bin/env bash
# ============================================================================
# 检查 topogym/world/genesis_ipc_vertex_constraints.py 的 install() 对装好的
# Genesis 还成不成立。
#
# install() 对 Genesis 的 IPC 耦合器做两处运行时替换，两处都照着 Genesis 1.2.1
# 的源码布局写：
#   1. build_ipc_scene_config —— 把 IPC 场景的 dt 除以 substeps，使 IPC 与刚体
#      求解器在 substeps>1 时走同一个时钟；
#   2. IPCCoupler._add_fem_entities_to_ipc —— 整段 vendored 副本，额外注册 FEM
#      的 per-vertex pin 与 SoftPositionConstraint follow。
# 换 Genesis 版本、换安装来源（wheel / git 源码）都可能让其中一处失配。
#
# 2026-08-19 在 mll-4090-2 上失配一次：
#   AttributeError: module 'genesis.engine.couplers.ipc_coupler.coupler'
#   has no attribute 'build_ipc_scene_config'
# 原因是该版本把 build_ipc_scene_config 写成函数体内的延迟导入，名字不进模块
# 命名空间，替换点必须落在定义处 ipc_coupler/utils.py。
#
# 不需要 GPU：只 import genesis 读源码，不 gs.init()、不建 scene。
#
# 退出码由 A、B 两节决定；C 节的 vendored 副本 diff 只打印，需要人工核对
# （围栏 `# --- topogym addition ---` 之外不应有差异）。
#
# 用法：
#   bash tests/check_genesis_ipc_patch.sh
#   TOPOGYM_VENV=.venv-gs121 bash tests/check_genesis_ipc_patch.sh
# ============================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  VENV="${TOPOGYM_VENV:-$REPO/.venv-gs121}"
  [[ -f "$VENV/bin/activate" ]] && source "$VENV/bin/activate"
fi

if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 无法 import genesis。先激活正确 venv（或设 TOPOGYM_VENV）。" >&2
  exit 1
fi

python - "$REPO" <<'PY'
import importlib
import inspect
import json
import sys
from difflib import unified_diff
from pathlib import Path

repo = Path(sys.argv[1])
failures = []


def report(ok, label, detail=""):
    print(f"[{'pass' if ok else 'FAIL'}] {label}" + (f" -- {detail}" if detail else ""))
    if not ok:
        failures.append(label)


# --- A. 装的是哪一份 genesis -------------------------------------------------
import genesis as gs

genesis_dir = Path(inspect.getfile(gs)).parent
print("=== A. genesis 安装信息 ===")
print(f"version        {gs.__version__}")
print(f"path           {genesis_dir}")

origin = "unknown"
for dist_info in genesis_dir.parent.glob("genesis_world-*.dist-info"):
    direct_url = dist_info / "direct_url.json"
    if direct_url.exists():
        origin = f"direct_url.json: {json.loads(direct_url.read_text())}"
    else:
        origin = f"index wheel ({dist_info.name})"
print(f"origin         {origin}")
report(gs.__version__ == "1.2.1", "genesis 版本是 install() 对着写的 1.2.1", gs.__version__)

# --- B. build_ipc_scene_config 的替换点 --------------------------------------
print("\n=== B. build_ipc_scene_config 替换点 ===")
coupler_mod = importlib.import_module("genesis.engine.couplers.ipc_coupler.coupler")
utils_mod = importlib.import_module("genesis.engine.couplers.ipc_coupler.utils")

# 名字在哪个模块的命名空间里可见，替换就必须落在哪个模块：coupler.py 顶层
# import 时替 coupler 才生效；写成函数体内延迟导入时，调用时才去 utils 取名字，
# 只有替 utils 生效。
if hasattr(coupler_mod, "build_ipc_scene_config"):
    effective = "coupler"
elif hasattr(utils_mod, "build_ipc_scene_config"):
    effective = "utils"
else:
    effective = None

for line_no, line in enumerate(inspect.getsource(coupler_mod).splitlines(), 1):
    if "build_ipc_scene_config" in line:
        indent = len(line) - len(line.lstrip())
        kind = "模块顶层" if indent == 0 else f"缩进 {indent}（函数体内）"
        print(f"coupler.py:{line_no}  {kind}  {line.strip()}")
print(f"本机上有效的替换点   {effective}")

# install() 当前实际替换的模块，从源码里读，改完代码这里跟着变。
vc_source = (repo / "topogym/world/genesis_ipc_vertex_constraints.py").read_text(encoding="utf-8")
current = None
for name, module_var in (("coupler", "coupler_module"), ("utils", "utils_module")):
    if f"{module_var}.build_ipc_scene_config =" in vc_source:
        current = name
print(f"install() 用的替换点 {current}")

report(effective is not None, "build_ipc_scene_config 在两个模块之一可见")
report(
    effective is not None and current == effective,
    "install() 的替换点与本机一致",
    f"install()={current} 本机={effective}",
)

# --- C. vendored 副本与装好的 1.2.1 的差异 ------------------------------------
print("\n=== C. _add_fem_entities_to_ipc vendored 副本 diff ===")
installed = inspect.getsource(coupler_mod.IPCCoupler._add_fem_entities_to_ipc)


def vendored_source(text):
    """从 install() 里切出 vendored 的方法体（def 起，到缩进退回类级为止）。"""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("def _add_fem_entities_to_ipc"))
    indent = len(lines[start]) - len(lines[start].lstrip())
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped and (len(lines[i]) - len(lines[i].lstrip())) <= indent:
            end = i
            break
    return "\n".join(lines[start:end]) + "\n"


vendored = vendored_source(vc_source)
diff = list(
    unified_diff(
        inspect.cleandoc(installed).splitlines(),
        inspect.cleandoc(vendored).splitlines(),
        fromfile="installed 1.2.1",
        tofile="topogym vendored",
        lineterm="",
    )
)
if diff:
    print("\n".join(diff))
    fenced = sum(1 for line in diff if "topogym addition" in line)
    changed = sum(
        1 for line in diff if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )
    print(f"\n差异行 {changed} 行，围栏标记 {fenced} 处；围栏之外的差异需要人工核对。")
else:
    print("无差异（此时说明 vendored 副本里的 topogym 改动已经丢失，同样要查）。")

print("\n=== 结论 ===")
if failures:
    print("失败项：" + "；".join(failures))
    sys.exit(1)
print("A、B 两节通过；C 节的 diff 需人工核对围栏外是否有差异。")
PY
