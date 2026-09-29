# 运行时统一 Nyx + compact_lab

日期：2026-09-23。

## 1. 本次调整

- `SimulatorConfig` 默认计算设备 CUDA、渲染 Nyx；RGB 仍通过 `enable_rgb=True` 按需开启。公共配置拒绝其他 renderer，CPU 物理须关闭 RGB。
- ALOHA 和 Panda＋Robotiq 两个 profile 继承同一 `compact_lab` 的 Nyx、HDRI、室内灯光和桌面/木纹材质配置，撤销覆盖它的 Rasterizer 配置。
- `World` 构造、夹具预览与 `Sensors` 统一接入 Nyx；不提供自动降级。关闭 RGB 时不创建 Nyx sensor，也不要求视觉资源。
- `Env.observe()`、`Env.render()` 和 `RecordingSession` 继续共享同一个 `SensorFrame`。Genesis 内部相机保留标定和位姿职责，运行时 RGB 由 `NyxCamera` 读取。
- 新观测按 episode / branch / state 标识刷新整组 Nyx 相机缓存；同一个 tick 回溯到其他分支，也不能复用上一个分支的图像。相同状态的重复 observe/render 继续复用已保存的 SensorFrame。
- 基础环境测试检查实际相机类型和 presentation；报告及录像 manifest 保存 renderer、背景、实际应用的材质与相机类型，同时记录 Nyx 包版本。
- 测试收尾与使用约定统一为：先完成并关闭录像消费者，再关闭 Env 或重建 episode。首轮 Nyx 检查发现原先反向关闭会在录像帧索引关闭时发生 `Bad file descriptor`；这次按资源使用顺序调整，不吞掉异常。

## 2. 使用

```python
from topogym.config import SimulatorConfig
from topogym.env import Env

with Env(SimulatorConfig(task_id="cast_coil", enable_rgb=True)) as env:
    observation, info = env.reset(seed=0)
    observation, reward, terminated, truncated, info = env.step({})
    rgb_by_camera = env.render()
```

依赖为 Genesis 1.2.1、gs-nyx 0.1.3、gs-nyx-plugin 0.1.4 和 CUDA；FEM 另需 pyuipc 0.0.25。仓库已备有 `.venv-gs121-nyx` 和 `.external/nyx-assets`。视觉资源由 `TOPOGYM_VISUAL_ASSET_ROOT` 或默认用户缓存定位；全新安装可运行 `scripts/prepare_nyx_studio.py`。

```bash
export TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets"
.venv-gs121-nyx/bin/python scripts/test_base_tasks.py --device cuda --steps 3 \
  --tasks cast_coil blanket_flatten rope_threading \
  --output runs/test_results/nyx_runtime_local
```

从仓库根目录运行；输出目录必须不存在。去掉 `--tasks` 可选择全部 13 项任务与两个公共机制。

## 3. 验证范围

- 配置、任务支持、Env 合同、录制/数据合同：64 项通过，1 项 HDF5 未选择；[最终 JUnit](../../../runs/test_results/nyx_configuration_checks_final/junit.xml)。包含模拟原生相机缓存的同 tick 分支观测检查。
- GPU 代表任务 Cast Coil（刚体）、Blanket（PBD）和 Rope Threading（FEM/IPC）均通过；[结果目录](../../../runs/test_results/nyx_runtime_smoke_02/README.md)。每项主连续片段为 3 个控制步、0.075 秒，另检查回溯、续跑和 seed 重建。各任务运行中源码未变，报告与录像均实际生成。
- 同 tick 缓存修正后，另对 Cast Coil 作定向复测并通过：[结果与录像](../../../runs/test_results/nyx_cache_acceptance/README.md)、[逐项报告](../../../runs/test_results/nyx_cache_acceptance/cast_coil/report.json)。先将 Nyx 内部缓存置零，再回溯到同 tick 的旧分支，要求所有相机重新取得非空图像；同时重新执行其完整短程生命周期。该项与上述三类生命周期验证分别记录，不声称缓存修正后重新跑过全部任务。
- `runs/test_results/nyx_runtime_smoke_01` 保留初轮诊断：Coil/Blanket 的物理检查完成，但录像收尾发生文件句柄错误；Rope 在回溯阶段以 SIGSEGV（-11）退出，原生原因尚未定位。第二轮 Rope 完整通过，不能把单次未复现描述为已修复原生崩溃；未修改 Genesis、Nyx 或 IPC 的第三方实现。尝试附加原生调试器被运行环境的 ptrace 限制阻止，记录保留在第二轮结果目录。
- 历史 `base_acceptance_final` 的 13/13 结果使用 Rasterizer；原报告和视频保持原样，历史索引另存为 `README_rasterizer.md`。当前 README 已切换为下文新一轮 Nyx 分批结果，不能混同两轮证据。
- 本次统一渲染配置，不重新设计任务材质/几何，不把短程检查视为可解证明或完整 demo。

| 任务 | 第二轮结果 | Nyx 实际录像 |
|---|---|---|
| Cast Coil | 通过，约 94 秒 | [斜视](../../../runs/test_results/nyx_runtime_smoke_02/cast_coil/branch_000/videos/oblique.mp4) |
| Blanket Flatten | 通过，约 132 秒 | [顶视](../../../runs/test_results/nyx_runtime_smoke_02/blanket_flatten/branch_000/videos/topdown.mp4) |
| Rope Threading | 通过，约 155 秒 | [斜视](../../../runs/test_results/nyx_runtime_smoke_02/rope_threading/branch_000/videos/oblique.mp4) |

## 4. 全量录像更新与画质、时长检查

用户要求先解释画质和“0 秒”，然后为原验收目录的全部任务更新 Nyx 录像。本轮保持相机与短程物理设置，重新执行当前 simulator，而非给历史 Rasterizer 轨迹改标签。全量结果写入 `runs/test_results/nyx_base_acceptance_all/`；最终入口更新到 `runs/test_results/base_acceptance_final/README.md`，原文件和物理报告另行保留。

### 4.1 画面为什么偏糊

- 实测斜视相机为 **512×512**，从整个桌面远景取景，任务物体占用像素较少。对照 `demos/cast_coil/varaition_baseline_assembly/front_oblique/2026-09-17_aloha_full_front_oblique.mp4` 的 **960×720 近景**，分辨率和物体画面占比均不相同。旧 demo 从预抓取位置开始，当前测试从机器人 home 开始，也影响视觉对比。
- 当前 native Nyx camera 使用 FastPathTracer、**32 spp**、`denoise=True`、SMAA、Reinhard、pinhole。没有发现景深失焦配置；去噪及抗锯齿可能柔化细节，但未做同机位参数消融，不能认定它们是主要原因。上述旧 demo 的归档配置为 24 spp，不能简单归因为当前采样数比旧版低。
- `recording/encoding.py` 没有缩小画面，只补齐奇数边长；编码为 H.264、CRF 18、yuv420p。Nyx 输出的初始 RGB 现按每相机保存为 PNG，不调整尺寸或滤镜。
- 本轮 Cast Coil 斜视原始 PNG 与 MP4 解码第一帧，同尺寸逐像素比较：平均绝对误差 **1.56/255**，RMSE **2.16/255**，PSNR **41.42 dB**。这些是整帧指标，只衡量本次编码差异，不单独衡量小物体边缘，也不能证明渲染本身写实；原始图中的小物体细节也有限。[比较数据](../../../runs/test_results/nyx_base_acceptance_all/encoding_comparison.json)。
- 因此当前可确认的首要限制是取景和像素覆盖。Nyx 后端一致也不保证各任务历史几何、材质、灯光、机位全部复现。本轮未擅自提高分辨率或重做材质。

### 4.2 “0 秒”是否正常

- 本次沿用 `--steps 3`：每控制步 10 个物理 tick，每 tick 0.0025 秒，主连续片段推进 **0.075 秒物理时间**。
- 30 fps 录制将这些状态映射到 3 个编码帧，MP4 容器时长为 **0.100 秒**。部分回溯、新 seed 片段只有 1 帧，为 **0.033 秒**。按整数秒显示的播放器会显示“0 秒”。
- 这不是没有执行 step，也不是把数分钟的测试耗时压缩成视频。报告 wall time 包含编译、渲染、checkpoint 与重建，不能作为物理时长。主录像只覆盖一条连续分支，回溯后另建片段。
- 这些录像适合核对场景和生命周期，但不适合观察完整动作或长期稳定性；不是 solved demo。若后续要可观看的 5 秒真实连续片段，需要至少 200 个控制步，并实际承担相应的物理、状态保存和渲染耗时，不能只重复帧冒充运行。

### 4.3 本轮报告补充

- `tests/runtime_evidence.py` 保存各相机初始 RGB PNG、SHA-256、state_id，以及实际 Nyx 相机分辨率、机位、spp、去噪、抗锯齿和色调映射参数。
- `scripts/test_base_tasks.py` 总表显示每个主片段的精确秒数、帧数、分辨率和原始 PNG 链接；每个相机、每条分支仍有独立 MP4、时间映射和完整解码校验。
- 执行命令：

```bash
TOPOGYM_VISUAL_ASSET_ROOT="$PWD/.external/nyx-assets" \
  .venv-gs121-nyx/bin/python scripts/test_base_tasks.py \
  --device cuda --steps 3 --output runs/test_results/nyx_base_acceptance_all
```

### 4.4 全量检查发现的 URDF 导出缺口

- 首批 Cast Coil、Cast Keyhole、Horseshoe Ring、Hedgehog、Interlocked Claws、Blanket 通过。Buzz Wire 的 wire/wand、Lock Picking 的 goal、Fiber Bundling 的 ring 因 `merge_fixed_links=True` 被 Nyx URDF exporter 拒绝，未得到有效录像。Buzz 显式启用该选项，后两项继承了 Genesis 的默认值。
- 已检查生成的这四个 URDF：均为 **1 个 link、0 个 joint**。它们没有可以合并的固定关节；问题是 exporter 对选项的限制，而不是任务需要改换物理模型。
- `world/genesis_world.py` 在构造 URDF 时默认 `merge_fixed_links=False`，并撤销 Buzz 的冲突选项。无 RGB 的环境也采用相同默认值，避免开关 RGB 导致不同的 link 结构。未改第三方库、未换渲染器、未修改这些资产的碰撞形状和关节内容。
- `tests/unit/test_task_definitions.py` 的 14 项检查通过，证据位于 `runs/test_results/nyx_urdf_declaration_checks/junit.xml`；三项受影响任务仍须真实 GPU 补测通过，不能以声明检查代替运行。
- 首批驱动进程在 Rope Threading 初始化期间收到 SIGTERM；保存了 `driver_interruption.json`。信号来源未确定，不能把它记为物理断言失败或任务通过。后续改为较小批次完成剩余任务与机制。
- 首批通过的六项不依赖此次修正：其 URDF 已显式关闭合并，或没有使用 URDF。汇总将保留每批源码快照与失败/中断报告，不声称全部结果来自修正后的同一次完整运行。

### 4.5 最终结果与入口

- **13/13 项基础任务通过，2/2 项公共机制通过。** 真实 GPU 测试实际使用 Nyx + compact_lab；运行中的源码未变。修正前后分批执行，来源和两份运行代码的差异在汇总中保留，未将首批失败改写成通过。
- [统一结果与主视角入口](../../../runs/test_results/base_acceptance_final/README.md) 已替换原 README 的视频链接，并提供斜视、顶视、正视与原始 PNG。[全部相机与分支](../../../runs/test_results/nyx_base_acceptance_all/videos.md) 可直接点开每段 MP4。
- 共 **103 个独立片段、737 份多视角 MP4、108 张初始 PNG**。测试收尾对 MP4 完整解码；汇总时复核视频、时间映射和 PNG 的 SHA-256，核对各视角帧数/分辨率与 manifest，并确认索引链接有效。[文件核验结果](../../../runs/test_results/nyx_base_acceptance_all/artifact_verification.json)、[机器可读汇总](../../../runs/test_results/nyx_base_acceptance_all/current_summary.json)。
- 基础任务主连续段仍为 3 个控制步、0.075 秒物理时间、0.100 秒 MP4；task_switch 每场景只执行 1 个控制步，其片段为 0.033 秒/1 帧。保留短程设置用于对照，不将录像称为完整动作展示或任务可解证明。
- 本轮未再次遇到早前代表测试中的 FEM 原生 SIGSEGV；这不等于已定位或修复第三方原生崩溃原因，也不构成长时稳定性证明。

| 批次 | 结果 | 记录 |
|---|---|---|
| 首批 | 6 项通过；3 项 URDF 导出失败；Rope 初始化受 SIGTERM 中断 | [原始批次记录](../../../runs/test_results/nyx_base_acceptance_all/README.md) |
| URDF 修正补测 | Buzz Wire、Lock Picking、Fiber Bundling：3/3 通过 | [报告与录像](../../../runs/test_results/nyx_base_acceptance_urdf/README.md) |
| 自由软绳 | Rope Threading、Knot Untying：2/2 通过 | [报告与录像](../../../runs/test_results/nyx_base_acceptance_fem_pair/README.md) |
| 带约束软体 | Orbits、Slotted Post Ring：2/2 通过 | [报告与录像](../../../runs/test_results/nyx_base_acceptance_anchored/README.md) |
| 公共机制 | FEM checkpoint/两端约束、同进程任务切换：2/2 通过 | [报告与录像](../../../runs/test_results/nyx_base_acceptance_mechanisms/README.md) |
| 任务声明检查 | 14/14 通过 | [JUnit](../../../runs/test_results/nyx_urdf_declaration_checks/junit.xml) |
