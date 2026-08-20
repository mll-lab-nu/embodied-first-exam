#!/usr/bin/env bash
# ============================================================================
# 装着的 Genesis 到底给了什么：布料材质的默认值、贴图接口、自带素材与用法示例。
#
# 为什么要先跑这个，而不是直接改代码：
#
#   1. 组会给的方向是「采用 Genesis 官方布料示例的材质参数」。但**从 wheel 装的
#      Genesis 里没有 examples 目录**（示例在 GitHub 仓库里）。离线能拿到的等价物
#      是材质类自己的字段默认值——官方示例基本就是直接用默认值。
#
#   2. 贴图是唯一能给布加表面细节的通道（光栅化器只保留 diffuse 颜色与 diffuse 贴图，
#      粗糙度/金属度/法线/自发光都是光追专用，而光追在本安装不可用）。这条通路是从
#      docs/develop/visual/photorealism_workstream_zh.md 读来的，**本仓从未真正调用过
#      任何贴图 API**，先确认再动代码。
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

ROOT = pathlib.Path(gs.__file__).parent
print(f"genesis {getattr(gs, '__version__', '?')}  @ {gs.__file__}")


def dump_fields(label, cls):
    """字段名 + 默认值。这些材质类是 Pydantic 模型，签名被吞成 **data，
    所以签名看不到东西，要读 model_fields。"""

    print(f"\n=== {label} 的字段与默认值 ===")
    fields = getattr(cls, "model_fields", None)
    if not fields:
        try:
            print(inspect.getsource(cls))
        except OSError as exc:
            print(f"(既无 model_fields 也取不到源码: {exc})")
        return
    for name, info in fields.items():
        default = getattr(info, "default", "?")
        if repr(default) == "PydanticUndefined":
            default = "(必填)"
        print(f"  {name:24s} = {default!r}")


# ---- 1. 布料材质的默认值 = 离线能拿到的「官方示例参数」 --------------------
dump_fields("gs.materials.PBD.Cloth", gs.materials.PBD.Cloth)
# 同类对照：Genesis 自带的 FEM 布料。我们走 PBD（绳 FEM+IPC / 布 PBD 是已定分工），
# 但它的取值量级同样是官方口径，值得并排看。
fem_cloth = getattr(getattr(gs.materials, "FEM", None), "Cloth", None)
if fem_cloth is not None:
    dump_fields("gs.materials.FEM.Cloth（对照，不使用）", fem_cloth)

print("\n对照当前 cloth_fold 配置里的值（它们其实是绳子 prefab 的值）:")
print("  stretch_compliance 0.0012 / bending_compliance 0.0200")
print("  stretch_relaxation 0.35   / bending_relaxation 0.2")
print("  rho 400.0 / air_resistance 0.001")
print("  static_friction 0.35 / kinetic_friction 0.25   （这两个是布对布，不管桌面）")

# ---- 2. 贴图接口 -----------------------------------------------------------
print("\n=== Plastic 收哪些贴图槽 ===")
for name, annotation in getattr(gs.surfaces.Plastic, "__annotations__", {}).items():
    if "texture" in name:
        print(f"  {name:20s}: {annotation}")
print("  注意：normal_texture 这个槽存在，但光栅化器把它丢掉（见最后一节），")
print("        给得进去、不报错、没效果——最容易踩的坑。")

image_texture = getattr(gs.textures, "ImageTexture", None)
if image_texture is not None:
    print("\n=== ImageTexture 的字段 ===")
    dump_fields("gs.textures.ImageTexture", image_texture)

# ---- 3. Genesis 自带素材与实际用法 -----------------------------------------
print("\n=== 包里自带的素材目录 ===")
asset_dirs = sorted(
    {p.parent for p in ROOT.rglob("*")
     if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".obj", ".glb", ".gltf"}}
)
if asset_dirs:
    for directory in asset_dirs[:20]:
        kinds = sorted({f.suffix.lower() for f in directory.iterdir() if f.is_file()})
        count = sum(1 for f in directory.iterdir() if f.is_file())
        print(f"  {directory.relative_to(ROOT)}  ({count} 个文件, {' '.join(kinds)})")
    if len(asset_dirs) > 20:
        print(f"  ... 另有 {len(asset_dirs) - 20} 个目录")
else:
    print("  (无)")

print("\n=== 包里哪些文件实际构造过布料（事实上的官方用法）===")
hits = []
for path in ROOT.rglob("*.py"):
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for marker in ("PBD.Cloth(", "FEM.Cloth(", "materials.PBD.Cloth", "materials.FEM.Cloth"):
        if marker in text:
            hits.append((path.relative_to(ROOT), marker))
            break
for path, marker in hits:
    print(f"  {path}  ({marker})")
if not hits:
    print("  (只有材质类自身的定义；wheel 安装不带 examples，示例在 GitHub 仓库里)")

# ---- 4. 复核「光栅化器丢弃 PBR 参数」这条结论 -------------------------------
# 整个贴图方案都建在这条结论上，而它是 2026-07-11 读源码得出的，之后 Genesis 版本变过。
print("\n=== 光栅化器保留哪些表面属性 ===")
try:
    from genesis.utils import mesh as mesh_utils

    fn = getattr(mesh_utils, "surface_uvs_to_trimesh_visual", None)
    if fn is None:
        print("  surface_uvs_to_trimesh_visual 不存在了——那条结论要重新核对")
    else:
        source = inspect.getsource(fn)
        for key in ("roughness", "metallic", "normal", "emissive", "diffuse", "texture", "opacity"):
            print(f"  提到 {key:10s}: {'是' if key in source else '否'}")
        print("\n  函数原文：")
        for line in source.splitlines():
            print(f"    {line}")
except Exception as exc:
    print(f"  取不到: {exc}")
PY

echo
echo "日志: ${LOG}"
