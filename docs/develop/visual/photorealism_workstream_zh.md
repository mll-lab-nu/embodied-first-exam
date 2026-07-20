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

- 灯光组/背景（`VisOptions` 接线,~半天）——用户当前裁掉；
- 程序生成/CC0 diffuse 贴图（木纹桌面）——用户当前裁掉（"有点 advance"）；
- GLB PBR 资产做连接件金属感——依赖资产管线；
- BatchRenderer（Madrona 可用性未验证）/ LuisaRender 编译评估——重；
- 物理真实性 metrics 实装（M8/M9/M12 与通用 probe）——见 guidelines 文档 §3，待批准。
