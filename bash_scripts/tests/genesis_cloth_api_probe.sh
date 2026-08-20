#!/usr/bin/env bash
# ============================================================================
# 装着的 Genesis 到底给了什么：布料材质的默认值、贴图接口、是否带布料示例。
#
# 为什么要先跑这个，而不是直接改代码：
#
#   1. 组会给的方向是「采用 Genesis 官方布料示例的材质参数」。但**从 wheel 装的
#      Genesis 里没有 examples 目录**（示例在 GitHub 仓库里）。离线能拿到的等价物
#      是 `PBD.Cloth` 的构造默认值——官方示例基本就是直接用默认值。本脚本把它打出来。
#
#   2. 贴图是唯一能给布加表面细节的通道（光栅化器只保留 diffuse 颜色与 diffuse 贴图，
#      粗糙度/金属度/法线/自发光都是光追专用，而光追在本安装不可用）。但这条通路
#      是从 docs/develop/visual/photorealism_workstream_zh.md 读来的，**本仓从未
#      真正调用过任何贴图 API**。先确认 `Plastic` 收不收贴图参数、`ImageTexture`
#      的签名长什么样，再动代码。
#
# 纯读取，不建场、不跑物理、不写任何仓库文件，秒级返回。
#
# 用法：
#   bash bash_scripts/tests/genesis_cloth_api_probe.sh
# ============================================================================
set -uo pipefail

STAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="runs/genesis_cloth_api/${STAMP}"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/probe.log"

if ! python -c "import genesis" 2>/dev/null; then
  echo "[error] 当前环境导入不了 genesis，先激活装了 Genesis 的 venv。" >&2
  exit 1
fi

python - <<'PY' 2>&1 | tee "${LOG}"
import inspect
import pathlib

import genesis as gs

print(f"genesis {getattr(gs, '__version__', '?')}  @ {gs.__file__}")


def show(label, thing):
    print(f"\n=== {label} ===")
    try:
        print(inspect.signature(thing))
    except (TypeError, ValueError) as exc:
        print(f"(取不到签名: {exc})")


# ---- 1. 布料材质的默认值 = 离线能拿到的「官方示例参数」 --------------------
show("gs.materials.PBD.Cloth 的默认值", gs.materials.PBD.Cloth.__init__)
print("\n对照当前 cloth_fold 配置里的值（它们其实是绳子 prefab 的值）:")
print("  stretch_compliance 0.0012 / bending_compliance 0.0200")
print("  stretch_relaxation 0.35   / bending_relaxation 0.2")
print("  rho 400.0 / air_resistance 0.001")
print("  static_friction 0.35 / kinetic_friction 0.25   （这两个是布对布，不管桌面）")

# ---- 2. 贴图接口 -----------------------------------------------------------
print("\n=== gs.surfaces 有哪些 ===")
print(sorted(n for n in dir(gs.surfaces) if not n.startswith("_")))
show("gs.surfaces.Plastic", gs.surfaces.Plastic.__init__)

print("\n=== 贴图类型 ===")
textures = getattr(gs, "textures", None)
if textures is None:
    print("gs.textures 不存在——换个地方找：")
    for name in ("gs.surfaces.Texture", "gs.options.surfaces"):
        print(f"  {name}: {'有' if hasattr(gs, name.split('.')[1]) else '无'}")
else:
    print(sorted(n for n in dir(textures) if not n.startswith("_")))
    for name in ("ImageTexture", "ColorTexture"):
        cls = getattr(textures, name, None)
        if cls is not None:
            show(f"gs.textures.{name}", cls.__init__)

# Plastic 到底收哪些字段（dataclass / attrs 都能看出来）
print("\n=== Plastic 的字段（判断能不能塞贴图）===")
fields = getattr(gs.surfaces.Plastic, "__dataclass_fields__", None)
if fields:
    for name, field in fields.items():
        print(f"  {name}: {field.type}")
else:
    hints = getattr(gs.surfaces.Plastic, "__annotations__", {})
    print("  " + ", ".join(f"{k}: {v}" for k, v in hints.items()) if hints
          else "  (既不是 dataclass 也没有注解，见上面的签名)")

# ---- 3. 装的包里带没带布料示例 ---------------------------------------------
print("\n=== 包里有没有布料相关的文件 ===")
root = pathlib.Path(gs.__file__).parent
hits = [p for p in root.rglob("*.py") if "cloth" in p.name.lower()]
if hits:
    for p in hits:
        print(f"  {p}")
else:
    print("  (没有；wheel 安装不带 examples，示例在 GitHub 仓库里)")

# 顺带确认那条「光栅化器丢弃 PBR 参数」的结论在这一版仍然成立
print("\n=== 光栅化器保留哪些表面属性（本仓结论的复核）===")
try:
    from genesis.utils import mesh as mesh_utils

    fn = getattr(mesh_utils, "surface_uvs_to_trimesh_visual", None)
    if fn is None:
        print("  surface_uvs_to_trimesh_visual 不存在了——那条结论要重新核对")
    else:
        source = inspect.getsource(fn)
        for key in ("roughness", "metallic", "normal", "emissive", "diffuse", "texture", "opacity"):
            print(f"  提到 {key:10s}: {'是' if key in source else '否'}")
except Exception as exc:
    print(f"  取不到: {exc}")
PY

echo
echo "日志: ${LOG}"
