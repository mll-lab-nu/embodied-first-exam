# 默认渲染与背景：Nyx + compact_lab

2026-09-16 起，两个共享桌面预设默认采用 Nyx 与既有的完整封闭实验室
`compact_lab`（3.8 × 3.4 m，四面墙、顶棚、地板、柜体、白板、门）。
复用 staged-lock 已校准的四盏室内灯；白色桌面与木纹边框也成为共享外观。
历史的 `lab` 是两面墙的布景，仍可显式选择。

单一配置源：[`configs/presentation_configs/nyx_lab.yaml`](../../../configs/presentation_configs/nyx_lab.yaml)。
刚体 / PBD 与 FEM 世界都通过 Hydra 引入它；`env.appearance` 只放任务外观，
不会再因 OmegaConf 替换整个列表而丢失公共桌面材质。

## 通用模块调整

| 模块 | 改动与原因 |
| --- | --- |
| `world/tabletop.py` | 实际消费 `env.renderer.type`；在所有任务实体添加完、`scene.build()` 前统一接入背景、材质与传感器。 |
| `world/presentation.py` | 统一预构建入口；各相机只注册一次，HDRI 与灯只注册一组。独立夹具试验通过 `add_preview_camera` 使用相同预设。 |
| `world/nyx.py` | `NyxCamera` 适配现有 `render()` / 录像 / 标定接口；保留原始 raster camera 供明确对照。纹理路径相对仓库解析，腕部没有机器人时采用静态相机。 |
| `world/nyx_lab.py` | 背景沿用既有几何；所有装饰固定、无碰撞，且 `needs_coup=False`，不加入柔体耦合。 |
| `utils/recording.py` | 无须更改接口：选相机、采样步长、HUD、视频保存继续调用同一相机协议。 |
| `data/episode_dataset_writer.py` | RGB 采集接口保持一致；setup 增加与 `camera_names` 对齐的 `camera_renderers` / `camera_backgrounds`，记录采集来源。旧/外部相机未声明来源时写 `unknown`。 |
| 安装与启动脚本 | 安装器默认建立 `.venv-gs121-nyx`；有录制功能的 shell 入口优先使用它，仍尊重已激活环境与显式 `TOPOGYM_VENV`。 |

这些改动不调整任务形状、接触参数、控制器、成功判据或相机视场角。
当前任务的专用相机和任务材质继续由各自配置覆盖；旧版任务及其演进记录已归档到 `legacy/`。

## 使用与回退

```bash
# 新机器准备（本机已有安装与资产）。
bash env_setup_gs121.sh
.venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py

# 查看默认环境；同时检查腕部跟随、录像与 HDF5 RGB 采集。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview

# 普通桌面任务已经默认走 Nyx，无须选专用 _nyx demo。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking run.inspect_only=true

# 显式选择 CPU 光栅和原棋盘背景（纯刚体 / PBD 环境）。
.venv-gs121/bin/python -m demos.environment_bootstrap.lock_picking run.inspect_only=true \
  env.genesis.backend=cpu env.renderer.type=rasterizer env.presentation.background=checker

# 只安装原光栅环境。
INSTALL_NYX=0 bash env_setup_gs121.sh
```

独立 `chain_links`、`buzz_wire`、`lock_aperture` 入口默认也使用 Nyx，
可用 `--renderer rasterizer`；前两者的 `--no-render` 继续跳过相机与背景。
历史产物不会因默认配置变化而重新渲染。

`env.renderer.type` 支持 `nyx`、`rasterizer`、`batch`、`auto`。
`auto` 保留原来的 n_envs 分流：0 为光栅，正数为 Madrona；默认 Nyx 不会静默改成批量渲染。
共享 Nyx 相机目前限定 `sim.n_envs=0`，深度、分割、法线请求会明确报错，需选择其他后端。
交互式 Genesis viewer 仍是光栅窗口；Nyx 用于传感器 RGB、视频和数据集。

Nyx 读取任一 sensor 会刷新该场景已注册的全部 Nyx 相机。大规模采集应只保留需要的
`env.cameras`，并设置合适的录制采样间隔；锁定预设要求保留原 base_camera。
渲染计时与批量渲染探针显式保留历史后端，避免修改测量基线。

## 验证产物

- [`默认场景预览`](../../../runs/environment_bootstrap/default_presentation/index.html)：房间全景、oblique、wrist；
  [`报告`](../../../runs/environment_bootstrap/default_presentation/report.json) 包含实际渲染后端、背景实体、材质与腕部标定误差。
- `tests.check_shared_presentation`：默认继承、渲染器选择、灯光只注册一次、无机器人腕部回退、RGB 独立拷贝、录制采样契约。
- `presentation_preview`：CUDA 实际出图，腕部姿态变化与 Nyx 提交姿态误差 < 5e-5；
  共享录像每路 2 帧；HDF5 实际写入 2 帧与渲染来源；背景碰撞几何数为 0。

本轮验证覆盖渲染与数据入口，未重新执行所有任务的长程物理验收。

原环境 `.venv-gs121` 的显式光栅路径也完成实际出图、录像与 HDF5 验证。
当前主配置和任务组的 compose / resolve 检查通过；独立的刺猬预览按自身所需的配置节验证。
归档后的实际 GPU 渲染见 [目录整理验证报告](../../../runs/environment_bootstrap/cleanup_validation/presentation/report.json)。
