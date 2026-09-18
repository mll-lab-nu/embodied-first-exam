# Bar-through-hole 的 Nyx 材质展示

> 2026-09-16 更新：Nyx + `compact_lab` 已成为共享默认，背景、灯光与桌面材质改由
> 通用模块接入。下文描述旧版演进；当前用法与范围见 [默认渲染说明](default_nyx_lab_zh.md)。

## 已实现与实测

独立 Nyx 入口复用当前 bar-through-hole 的场景 builder、Franka 控制器、原 oracle、夹持与判定器，在同一个实时模拟 scene 上添加原生 Nyx sensor。未调整任务的碰撞网格、质量、摩擦、时间步或插孔控制。

当前展示使用摄影棚 HDRI、白色工程塑料外观桌面、木纹边框与侧裙、金属杆与黄铜色孔圈、面板／支架粗糙度。三个孔圈使用相同外观。周边加入地砖接缝、两面墙、踢脚线、储物柜和白板，提供尺度、遮挡与空间深度参照。配置与辅助模块只由 Nyx demo 使用，普通 demo 无须安装 Nyx。

环境：Genesis 1.2.1、gs-nyx-plugin 0.1.4、gs-nyx 0.1.3、NumPy 2.3.5，RTX 4090。新版默认以 1024×1024、64 spp、20 fps 录制。

2026-09-13 新版三路实测：每路 274 帧、13.7 秒，三路均已解码检查；原任务判定 success=true、threading=1、release_stable=true。全程相机矩阵最大元素误差 `2.38e-7`；腕部相机相对首帧最大位移约 17.5 cm，确认真实跟随。杆的 274 个采样位置与上版完全一致。Ruff 检查通过。

这是一版**原有资产的材质与光照演示**。木框使用真实木材的颜色／法线贴图；机器人仍使用原 MJCF 模型，实验室和工件仍有简化几何，没有重新制作摄影级资产。它也不表示物理抓取更真实：原任务仍使用 assisted grasp 和几何插入限位，结果报告中明确记录了这一点。新增环境装饰全部为固定、无碰撞物体，实验设备位于操作区之外。

## 相机和背景修正

第一版 `runs/bar_through_hole_nyx/` 使用另外设置的近景相机，位置 `[-0.52,-0.72,1.43]`、FOV 42°、16:9 画幅；这确实不是常规 oblique。第一版还主动把原地面棋盘纹理覆盖成灰色。这两点是 demo 配置选择，不是 Nyx 的限制。棋盘是 Genesis 地面纹理，不表示“没有东西”。旧产物保留，便于对照。

新版取消独立的 `env.renderer.camera`，统一通过 `recording.camera` 选择 `env.cameras`，并复用原 `recording.res` 分辨率覆盖逻辑：

| 相机 | 原配置，直接复用 |
|---|---|
| oblique | pos `[1,-0.8,1.42]`，lookat `[-0.08,0,0.98]`，FOV 57.2958° |
| front | pos `[0.42,0,1.30]`，lookat `[0.05,0,0.88]`，FOV 78° |
| wrist | 绑定机器人 `hand`；由现有 offset_pos / offset_lookat / offset_up 生成同一 offset_T，FOV 90° |

三者保留原方形画幅、裁剪距离、位姿与朝向，只提高像素数。若特意改成宽屏，相同垂直 FOV 下水平覆盖范围会改变；不要把分辨率与画幅比例混为一谈。

每个录制时刻读取 Nyx 实际提交的相机位姿，与原光栅相机的 world transform 比较；腕部两边都根据当前 link 更新。偏差超过 `5e-5` 会中止，避免悄悄录下静止或错位的腕部视频。三路视频来自同一 rollout、同一批采样时刻，不是三个独立重跑。

Nyx 本身支持多相机和 link attachment；[官方 sensor lifecycle](https://genesis-embodied-ai.github.io/genesis-nyx/latest/user_guide/advanced/sensor_lifecycle.html) 说明了共享渲染器和相机跟随的流程。本项目也核对了当前安装的 0.1.4 实现。所有相机在 build 前加入，光源／HDRI 只注册一次，避免多相机重复加灯。读取一路会渲染该 scene 的全部 Nyx 相机，因此只需要一路时应只选一路。

## 运行

从仓库根目录执行，使用已安装的 `.venv-gs121-nyx` 和可用 CUDA GPU：

```bash
cd /home/jianwen/topogym
.venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py
.venv-gs121-nyx/bin/python -m demos.routing.bar_through_hole_nyx_demo
```

只生成初始静态图：

```bash
.venv-gs121-nyx/bin/python -m demos.routing.bar_through_hole_nyx_demo run.inspect_only=true
```

同时录制三路：

```bash
.venv-gs121-nyx/bin/python -m demos.routing.bar_through_hole_nyx_demo \
  'recording.camera=[oblique,front,wrist]'
```

仅 wrist：`recording.camera=wrist`。只预览三路：在三路命令后加 `run.inspect_only=true`。

恢复原棋盘背景，同时保留白桌面和木框：

```bash
.venv-gs121-nyx/bin/python -m demos.routing.bar_through_hole_nyx_demo \
  run.inspect_only=true env.presentation.background=checker \
  recording.path=runs/bar_through_hole_nyx_checker/demo.mp4
```

提高静态图分辨率／采样数，可加 `'recording.res=[1536,1536]' env.renderer.spp=256`。修改镜头应覆盖 `env.cameras.oblique.*` 等共享相机定义。更改视频采样步数时，要同时让 `recording.fps = 1 / (env.sim.dt * recording.every_n_steps)`，入口会检查，避免加速播放造成误解。更改实验配置时建议覆盖 `recording.path` 到新目录，以保留原产物。

## 产物与实现

新版输出目录 `runs/bar_through_hole_nyx_lab/`：

- `demo.mp4`：单路输出；选择多路时为 `demo_oblique.mp4`、`demo_front.mp4`、`demo_wrist.mp4`。
- `nyx_<camera>_initial.png`、`nyx_<camera>_final.png`、`nyx_<camera>_<phase>.png`：静态图和阶段首帧。
- `rasterizer_<camera>_initial.png` / `final.png`：相同相机位姿与物理状态的光栅渲染。光栅使用原 VisOptions 光照，Nyx 使用 HDRI，因此这不是保持照明完全一致的渲染器性能比较。
- `config.yaml`、`cameras.json`、`frames.json`、`report.json`：配置、相机与 attachment 参数、每帧模拟时间／杆位置／相机 world transform、任务结果、包版本、GPU 与耗时。耗时不含首次场景构建，不能据此声称所有任务能以相同速度渲染。
- 静态预览另写 `preview_config.yaml` 与 `preview_report.json`。

入口：[bar_through_hole_nyx_demo.py](../../../demos/routing/bar_through_hole_nyx_demo.py)。配置：[bar_through_hole_nyx.yaml](../../../configs/bar_through_hole_nyx.yaml)。集成：[world/nyx.py](../../../topogym/world/nyx.py)。实验室装饰：[world/nyx_lab.py](../../../topogym/world/nyx_lab.py)。场景 builder 的 `before_finalize` 回调用于在 build 前配置展示、材质和传感器。

当前插件 0.1.4 的几何导出器在遇到 `ColorVisuals` 时只导出颜色，丢失 metalness／roughness。辅助模块对明确命中的外观规则设置等色 `TextureVisuals`，让其走完整 surface 导出路径，同时保留光栅所需颜色。此兼容处理只影响展示网格，不修改插件安装文件或碰撞网格；更换插件版本时应重新核对。

HDRI 为 Poly Haven 的 [Studio Small 09](https://polyhaven.com/a/studio_small_09)，作者 Sergej Majboroda。木纹为 [Wood Table 001](https://polyhaven.com/a/wood_table_001)，作者 Dimitrios Savva、Rico Cilliers。两者均为 CC0。准备脚本校验下载 SHA-256，并在 `.external/nyx-assets/` 写入来源信息。详细环境安装见 [nyx_gs121_setup_zh.md](nyx_gs121_setup_zh.md)。

新研究方向与现有任务是否达标的审查见 [Structurally Constrained 评估](../tasks/structurally_constrained_research_assessment_zh.md)；画面改善与结构任务有效性分别判断。
