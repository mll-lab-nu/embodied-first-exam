# Nyx 与 Genesis 1.2.1：安装与官方示例

验证日期：2026-09-13。结论：无需升级 Genesis；锁定兼容插件并调整 NumPy 后，官方示例已在本机 RTX 4090 上成功生成图像。

## 版本选择

以 PyPI 发布包的 `Requires-Dist` 为准，而非仅看 latest 文档：

| gs-nyx-plugin | Genesis 约束 | 适合当前 1.2.1？ |
|---|---|---|
| 0.1.3 | >=1.1.0,<1.2.0 | 否 |
| **0.1.4** | **>=1.2.0,<1.3.0** | **是，本轮采用** |
| 0.1.5 / 0.1.6 | >=1.3.1,<1.4.0 | 否，需升级 Genesis |

插件 0.1.2 的声明只有 `genesis-world>=0.4.7`，范围过宽，未据此推断其运行兼容性。本轮验证与 1.2.x 明确配套的 0.1.4。

已实测组合：

```text
Python            3.11.15
genesis-world     1.2.1
gs-nyx-plugin     0.1.4
gs-nyx            0.1.3
numpy             2.3.5
torch             2.12.0+cu126
GPU               NVIDIA GeForce RTX 4090, 24 GiB
NVIDIA driver     570.153.02
glibc             2.35
```

Nyx 要求 `numpy>=1.26.4,<2.4`，与主环境的 `numpy==2.4.4` 冲突。`requirements/uv-topogym-gs121-nyx.txt` 同时作为附加 requirements 和 uv overrides，只在启用 Nyx 时覆盖 NumPy。不能直接在主环境运行不锁版本的 `pip install gs-nyx-plugin`，它会选择不同的 Genesis 版本。

来源：[插件 0.1.4 元数据](https://pypi.org/pypi/gs-nyx-plugin/0.1.4/json)、[插件 0.1.6 元数据](https://pypi.org/pypi/gs-nyx-plugin/0.1.6/json)、[引擎 0.1.3 元数据](https://pypi.org/pypi/gs-nyx/0.1.3/json)。

## 前置准备及完成状态

| 项目 | 状态 |
|---|---|
| 确认匹配 Genesis 1.2.1 的插件和引擎 wheel | 已完成 |
| Python / Linux x86-64 / glibc 与 wheel 匹配 | 已完成 |
| 独立环境 `.venv-gs121-nyx` | 已创建 |
| NumPy 冲突解决，`uv pip check` | 已通过 |
| NyxCameraOptions 导入与实例化 | 已通过 |
| 官方示例、模型、HDRI、许可 | 已下载，固定提交并校验 SHA256 |
| CUDA 访问 | 沙箱内不可见；沙箱外 RTX 4090 可用 |
| 官方示例完整 GPU 渲染 | 已通过 |
| TopoGym 布料 / FEM+IPC 动态场景 | 本轮未验证 |

官方安装文档要求 CUDA 12.9+、NVIDIA driver 575+，wheel 自带 CUDA runtime。本机驱动 570.153.02 虽低于文档要求，但本轮固定版本的官方示例实际通过。这个结果只证明当前组合和示例可运行，不改写官方支持范围，也不证明所有 Nyx 功能都可用。未修改驱动或全局 CUDA；PyTorch 的 cu126 标签不等同于宿主驱动版本。

来源：[Nyx 安装说明](https://genesis-embodied-ai.github.io/genesis-nyx/latest/user_guide/installation.html)。

## 安装及运行

本机已经安装完成，直接运行最后一条即可复现。新机器完整流程：

```bash
cd /home/jianwen/topogym

# 启用 Nyx，默认使用独立的 .venv-gs121-nyx。
INSTALL_NYX=1 bash env_setup_gs121.sh

# 只下载和校验资源，无需 GPU；缓存完整时无需网络。
.venv-gs121-nyx/bin/python scripts/nyx_official_demo.py --prepare-only

# 检查固定包版本、相机配置 API、CUDA 与驱动；不渲染。
.venv-gs121-nyx/bin/python scripts/nyx_official_demo.py --check-only

# 运行未修改的官方示例并归档图像。
.venv-gs121-nyx/bin/python scripts/nyx_official_demo.py
```

`env_setup_gs121.sh` 新增 `INSTALL_NYX=1` 开关；普通调用依然使用原 gs121 配置。新 profile 中的 NumPy 调整经过所有包依赖一致性检查，但尚未做 TopoGym 全任务物理回归。独立环境也不会复制现有 venv 中手动安装的额外包或手动补丁；后续 FEM+IPC 测试还需核对 pyuipc 和项目运行时补丁。

示例入口固定上游提交 `d8d61f2682083dbf000cfc08e34cfac83eb27c67`，保留原始 Python 脚本。PBR_Ball.glb 使用 Git LFS 实体内容，不是 132 字节的指针文件。运行目录为 `.external/nyx-official/<commit>`，Nyx 的临时导出内容也留在那里。

官方脚本构建一个金属材质球与地面，用 HDRI 照明，以 `FastPathTracer`、1920×1080、64 spp 渲染一帧。它通过 `scene.add_sensor(NyxCameraOptions(...))` 进入 Genesis 1.2.1 的真实 sensor manager，完整出图验证覆盖插件发现、场景构建和读取图像，而不只是 Python import。

源码：[固定提交的官方示例](https://github.com/Genesis-Embodied-AI/genesis-nyx/blob/d8d61f2682083dbf000cfc08e34cfac83eb27c67/examples/01_hello_nyx.py)。

## 产物与验证范围

- `runs/nyx_official/01_hello_nyx.png`：渲染图像。
- `runs/nyx_official/metadata.json`：核心版本、驱动、示例提交。
- `.cache/nyx-audit/install.log`：独立环境安装及导入检查日志。
- `.cache/nyx-audit/official-demo.log`：首次原版示例运行日志。
- `.cache/nyx-audit/official-runner.log`：项目复现入口运行日志。

已目视检查图像：模型完整，金属表面有环境反射，地面有接触阴影，非空白或全黑输出。首次运行包含模型凸分解和 kernel 编译，不将其总耗时作为每帧渲染性能。

安装检查不能在 `gs.init()` 前主动导入 `NyxCameraSensor`：这会提早导入 Genesis 求解器，在 `gs.qd_float` 尚未初始化时失败。遵循官方顺序，只提前导入 options；具体 sensor 由初始化后的 `scene.add_sensor()` 发现。本轮已按这个顺序修正安装检查。

下一步是把 Nyx sensor 接到 TopoGym 的相机和录制入口，再测试 PBD/FEM 动态网格。这个官方刚体示例的通过，不代表这些项目级适配已经完成。
