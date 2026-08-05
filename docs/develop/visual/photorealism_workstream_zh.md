# Photorealism 工作流 devlog

> 日期：2026-07-11
> 对应：reviewer plan §2.5。范围经用户裁剪：**光照/光追不做、纹理贴图暂缓**；本轮只做**统一材质**；物理真实性先立准则（见 `physical_realism_guidelines_zh.md`）。

## 1. 盘点结论（改动前现状）

全库 35 处 `gs.surfaces.Plastic(平色)` 内联调用、12 种零散 roughness（0.5~0.95）；场景零灯光/贴图/阴影配置（全吃 Genesis 默认）；env config 的 `renderer:` 键是死配置（标准 builder 不消费，仅 common_room 原型消费且只支持 rasterizer/batch）；无资产目录。

## 2. 两条不可行发现（读 Genesis 1.2.1 源码证实，避免后人踩坑）

1. **RayTracer 不可用**：需 LuisaRender 扩展（`genesis/vis/raytracer.py` 无条件 `import LuisaRenderPy`），本安装 `genesis/ext/LuisaRender` 不存在 → "换光追 / HDRI 环境光"路线在不自行编译 LuisaRender 前提下走不通。
2. **光栅化器丢弃 PBR 参数**：`genesis/utils/mesh.py:235 surface_uvs_to_trimesh_visual()` 只保留 diffuse 颜色/图片贴图 + opacity；`roughness/metallic/normal/emissive` 是 raytracer-only → 在 `gs.surfaces.*` 上调这些参数是**视觉无效操作**（`Metal` 与 `Plastic` 只差颜色）。真 PBR 的唯一通路 = 导入自带烘焙材质的 GLB（pyrender 完整映射 `genesis/ext/pyrender/mesh.py:286-300`）。
   - 光栅化下**有效**的手段（将来若重启视觉升级）：`VisOptions`（lights 方向光/点光、ambient_light、shadow、plane_reflection、background_color）+ diffuse `ImageTexture`（png/jpg；hdr/exr 仅光追）。AmbientLight 类型光源光栅化不支持，环境光走 `ambient_light` 字段。

## 3. 本轮落地：统一材质（2026-07-11）

新增 `topogym/world/materials.py`：9 个语义角色（table/stage/frame/board/marker/fixture/connector/object/deformable）各定一档 roughness；`materials.plastic(role, color, vis_mode=None)` 是全库唯一的 surface 构造入口。**颜色仍由 config/调用方驱动**，模块只统一"工艺"。

迁移了全部 35 处调用（`world/tabletop.py`、`world/common_room.py` + 8 个 task 文件）；`env` yaml 里被收编的 `world.table.roughness`/`stage.roughness` 注释留档（数值不变）。由于光栅化本就忽略 roughness（§2.2），本轮**视觉输出零变化**——收益是结构性的：改观感=改一个文件；未来渲染器升级免费继承一致的粗糙度体系。

## 4. 后续阶梯（均未立项）

- 灯光组/背景（`VisOptions` 接线,~半天）——**已落地，见 §5**；
- 程序生成/CC0 diffuse 贴图（木纹桌面）——用户当前裁掉（"有点 advance"）；
- GLB PBR 资产做连接件金属感——依赖资产管线；
- BatchRenderer（Madrona 可用性未验证）/ LuisaRender 编译评估——重；
- 物理真实性 metrics 实装（M8/M9/M12 与通用 probe）——见 guidelines 文档 §3，待批准。

## 5. 灯光组落地：共用光影模块（2026-07-24）

用户新反馈："光影+材质再做得舒服一点，特别是加光影（应是通用模块）"。范围裁定：**只做光影**（贴图仍缓），基调走**中性浅灰影棚**。

现状根因：`StandardTabletopSceneBuilder.create()` 之前**不传** `vis_options` 给 `gs.Scene(...)` → 全场景吃 Genesis 默认（单一硬 key 方向光 `dir=(-1,-1,-1) intensity=5`、`ambient_light=(0.1,0.1,0.1)` 近黑、深蓝背景），故观感又硬又暗。

落地（与 `materials.py` 同构：一个模块统一"工艺"，config 可覆盖）：

- 新增 `topogym/world/lighting.py`：`vis_options(env_cfg=None) -> gs.options.VisOptions`。默认 rig = 主 key 方向光 `(-0.6,-0.5,-1.0)` + 反向 fill 方向光 `(0.6,0.4,-0.7)` + 抬高 `ambient_light=(0.35,0.35,0.38)` + 浅灰背景 `(0.55,0.58,0.62)` + `shadow=True`、`plane_reflection=False`。读可选 `env.vis` 覆盖块；缺省即模块默认。
- `StandardTabletopSceneBuilder.create()` 构建时传 `vis_options=lighting.vis_options(self.env_cfg)` → 所有 task/demo 免改自动继承（真·通用）。
- `world/__init__.py` 导出 `lighting`；`env_configs/world_tabletop_v1.yaml` 加注释版 `vis:` 覆盖块（默认留在模块，缺省不改行为）。

Genesis 版本注：本轮基于已装 **1.10**（`genesis/options/vis.py`）核对 API（§2 老结论基于 1.2.1）——光栅化仍只认 `VisOptions` 的 lights/ambient/background/shadow/plane_reflection，**不认 surface roughness**，故 `materials.py` 数值本轮不动（改了也无视觉效果），材质"变舒服"完全靠新光照让既有 diffuse 色读出 key/fill 梯度。

附带核实（stacked_plate 桌框问题）：桌面边框由共用 `_add_table_frame` 生成，stacked_plate 与其它 task 走**同一** builder + 同一 `world_tabletop_v1.yaml`（无 per-task `frame` 覆盖），几何逐字节相同。边框代码 2026-07-21 落地（commit `6b71709`）——观感差异应为旧渲染截图早于该 commit，或高盘阵视角把远端桌沿裁出画面，非 config 不一致。以现代码重渲即可确认。
