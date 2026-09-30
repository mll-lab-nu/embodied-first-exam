# 重复建场景原生崩溃与同 seed RGB 复现差异

记录日期：2026-09-25。原始失败批次：2026-09-24。最新状态：**五项公共机制复验通过；后续静态 GPU 实验已确认，同一个已建好的场景在零物理步进下重复渲染仍会出现像素差异，重建不是必要条件，具体渲染根因未定位**。最新实验见第 10 节；前七节保留首次交付时的背景与计划。

本次核对已有报告与测试源码，补充 RGB 诊断采集和用户运行脚本；没有运行模拟器或 GPU 测试。旧结果对应当时的冻结源码，不代表当前工作区已经复验。本记录承接此前讨论，后续把新结果追加到本文。

## 1. 两类问题及应用场景

| 问题 | 使用场景 | 实际失败 | 影响 |
|---|---|---|---|
| 重复创建/释放场景后原生崩溃 | 同一进程不断开始新 episode，或依次运行不同 Task | Panda 生命周期第 8 轮建场景时 SIGSEGV；跨任务切换第 4 个场景退出 -11 | Python 进程退出，后续任务无法继续；普通 `try/except` 无法恢复 |
| 同 seed 的初始 RGB 不一致 | 管理方先 reset(A)，经过物理操作/回溯，再 reset(B)、reset(A) | Cast Coil、Blanket、Rope 的部分或全部相机未通过逐像素相等 | 严格初态视觉复现合同未通过；现有证据不足以判断差异是否肉眼可见 |

“三个任务失败”指 RGB 检查失败，不是这三个任务都发生了原生崩溃。两类问题可能涉及生命周期/渲染状态，但目前没有证据证明它们共享根因。

## 2. 崩溃的复现路径与证据

### 2.1 Hedgehog + Panda/Robotiq：连续重建

实际入口：[test_lifecycle_stability.py](../../legacy/research_tools_20260929/tests/integration/test_lifecycle_stability.py)。以下为测试语义的伪代码，省略证据接口和断言细节：

```python
env = Env(task="hedgehog_in_cage", robot="panda_robotiq", max_physics_steps=17)
for cycle in range(10):                 # 同一个 Python 进程、同一个 Env
    observation, info = env.reset(seed=cycle % 2)
    actor = env.interaction(privileged=True)
    actor.step({})                     # 10 个 tick
    actor.step({})                     # 剩余 7 个 tick，达到上限
    actor.rewind_to(initial_state_ref)
    inject_one_post_integration_error()
    assert_step_faults_and_blocks_further_steps(actor)
    actor.rewind_to(initial_state_ref)
    actor.step({})                     # 恢复后继续积分
    finish_recording()
env.close()
```

原始 [Panda 报告](../../runs/test_results/simulator_contract_20260924/isolated_core_validation/stability_panda_robotiq/report.json)中 `reset_cycle_0` 至 `reset_cycle_6` 通过，`reset_cycle_7` 停在 running，即第 8 轮。原始 [崩溃日志](../../runs/test_results/simulator_contract_20260924/isolated_core_validation/stability_panda_robotiq.log)留下 `Fatal Python error: Segmentation fault`，栈经过：

```text
Env.reset
  → GenesisWorld.build / Tabletop.finalize
  → Genesis Scene.build / Simulator.build / SensorManager.build
  → NyxCameraSensor.build
  → NyxRenderer.build
  → 原生加载调用处崩溃
```

测试有意注入的 Python 异常是验收步骤；它不等于后续意外的原生崩溃。原生加载处的栈只能定位“在哪里暴露问题”，不能单独定位先前哪个对象或释放操作破坏了状态。

### 2.2 同进程跨 Task 切换

实际入口：[test_task_switch_runtime.py](../../legacy/research_tools_20260929/tests/integration/test_task_switch_runtime.py)：

```python
for task in ["cast_coil", "rope_threading", "blanket_flatten",
             "hedgehog_in_cage", "cast_coil"]:
    env = Env(task=task)               # 仍在同一个 Python 进程
    env.reset(seed=0)
    env.step({})
    finish_recording()
    env.close()
```

[原始切换报告](../../runs/test_results/scene_presets_20260924_lifecycle_01/task_switch/report.json)显示前三项通过，第 4 项 `3_hedgehog_in_cage` 留在 running，进程退出码 -11（SIGSEGV），最后一次 Cast Coil 未执行。该次缺少完整崩溃栈，不能把它直接归为上一个 Nyx 加载位置的同一缺陷。

单独运行 Hedgehog 基础生命周期曾通过；ALOHA 十轮生命周期曾通过。因此应重点检查反复创建/释放或混合任务切换后的状态，但尚不能断言是 Hedgehog 模型、Panda 模型、显存不足或某一引擎缺陷。任务类型、机器人类型、切换顺序、重建次数在这些对照中没有完全解耦。

日志中的 `Timeout (0:02:00)!` 来自 pytest 的周期性 faulthandler 栈转储，不等于驱动器执行了两分钟超时终止。是否真正超时应看驱动器的 `status` 和退出记录。

## 3. RGB 失败实际比较了什么

入口：[test_base_task_runtime.py](../../legacy/research_tools_20260929/tests/integration/test_base_task_runtime.py) 的 `seed_A_B_A` 阶段。原失败批次在实际推进阶段用了 3 个 control step，随后还执行了中间状态回溯、继续积分、同 tick 缓存检查和初态恢复：

```python
obs_a, info_a = env.reset(seed=0)
rgb_a = copy_all_rgb(obs_a)
assets_a = asset_hashes(env)
physical_a = measured_physical_arrays(env)

exercise_real_steps_and_rewinds(env)    # 不是单纯连续 reset 的缩减用例
finish_recording()
env.reset(seed=1)
finish_recording()
obs_a_again, info_a_again = env.reset(seed=0)

assert asset_hashes(env) == assets_a
assert every_camera_array_equal(rgb_a, obs_a_again["rgb"])
```

这里比较两个 episode 的 seed=0、physics_step=0 初态，不是要求运动前后画面相同，也不是把 rewind 的画面直接当作第二次 reset 的画面。

| 任务 | 物理类型 / 机器人 | 原始 RGB 相等结果 | 失败后独立比较的物理测量 |
|---|---|---|---|
| Cast Coil | 刚体 / ALOHA | 四路均 false | 720 个数组，最大绝对误差 0 |
| Blanket Flatten | PBD / ALOHA | 四路均 false | 702 个数组，最大绝对误差 0 |
| Rope Threading | FEM / ALOHA | cam_high 为 true，其余三路 false | 795 个数组，最大绝对误差 0 |

来源：[failed_case_analysis.json](../../runs/test_results/scene_presets_20260924_lifecycle_01/failed_case_analysis.json)。三项资产哈希检查通过，前序物理推进和回溯阶段通过；RGB 断言之后的合同检查没有完整执行，因此不能标为完整验收通过。物理数组对比是在失败后对保存状态的独立复核，**上述数组数量和误差不是图像误差统计**，也没有覆盖引擎所有内部缓存。

本次只读复核三个任务的 `steps.jsonl`：`initial` 和 `seed_A_again` 的 `camera_metadata` 均完全相同。此前讨论也记录了 presentation 配置相同。这削弱了“记录中的相机位姿或配置被改动”的解释，但不证明渲染器内部实际状态完全一致。

### 3.1 为什么别的任务没有失败

同批基础生命周期为 10/13 通过，另有 FEM checkpoint 专项通过，见[批次索引](../../runs/test_results/scene_presets_20260924_lifecycle_01/README.md)。已有对照足以排除一些普遍化解释：

| 简单解释 | 与它不符的对照 |
|---|---|
| 所有 ALOHA 场景都无法复现 | Keyhole、Horseshoe、Claws 以及其他三个 FEM 任务的全部相机通过 |
| 所有 FEM 都无法复现 | Knot、Orbits、Slotted Post Ring 通过 |
| 只有软体会出问题 | Cast Coil 为刚体，也失败 |
| Nyx 每次重建必定变化 | 同批另十个任务通过严格像素检查 |
| 原测试是视频压缩误差 | 原断言直接比较编码前的 RGB 数组 |

**还不能解释为什么恰好这三个任务触发差异。**场景特定的视觉几何、材质、渲染采样或历史状态仍是候选方向；“其他任务通过”只描述该次执行，不证明这些任务永远不会触发问题。

### 3.2 为什么旧产物不能给出准确差异热力图

旧报告只保存逐相机 `np.array_equal` 的布尔值。第一次初态有无损 PNG，第二次同 seed 初态只有录像，没有保留对应原始 PNG。一个通道仅差 1 也会使检查失败，所以“四路不一致”不等于“四路场景明显变化”。

此前录像离线比较中，Rope 的 cam_high 原始 RGB 判为完全一致，解码两个视频初帧却产生大量不同像素；两个视频片段的帧数/编码上下文不同。因此 MP4 解码差异混合了有损编码影响，不能用来反推这次原始 RGB 差异位于绳子、机器人还是背景。本文不把视频差异当作原始像素证据。

## 4. 本次补充的采集

[rgb_repro_evidence.py](../../legacy/research_tools_20260929/tests/rgb_repro_evidence.py) 已接入原生命周期用例，在第二次 seed=0 的 `evidence.sample` 之后、资产和 RGB 断言之前采集所有相机。保留原严格相等断言，不加容差、不跳过失败相机。录像仍由公共 `RuntimeEvidence` / `RecordingSession` 生成，诊断只保存已有 observation 数组，不新增渲染调用或物理步进。

每任务在 `rgb_repro/` 下生成：

| 文件 | 含义 |
|---|---|
| `<camera>/A.png`、`A_again.png` | 本次复验两次初态的 uint8 原始 RGB，无损保存 |
| `<camera>/absdiff.png` | 每通道绝对差，原始 0–255 尺度 |
| `<camera>/changed_mask.png` | 任一通道不同的像素为白色，其余为黑色 |
| `<camera>/max_error_x16.png` | 每像素最大通道差乘 16 并截断至 255；固定尺度灰度误差图，不按各相机最大值归一化 |
| `comparison.json` | 所有相机的布尔结果、差异像素数/比例、平均/最大通道差、阈值比例、差异包围框和 PNG 哈希 |

阈值比例定义为 `max(abs(A - A_again), RGB通道) > t`，`t ∈ {1, 2, 5, 10}`；比例取值为 0–1。平均通道误差以全图所有通道为分母。坐标原点在左上，包围框为 `[xmin, ymin, xmax_exclusive, ymax_exclusive]`；完全一致时为 null。计算前提升到 int16，避免 uint8 减法溢出。

相机参数、状态身份、资产哈希和渲染配置继续保存在 `steps.jsonl`、episode/录制元数据和 `report.json` 中。若 reset、采样或原生引擎在到达比较前就失败，可能没有 `rgb_repro/`；这种情况应先读日志，不能记为 RGB 通过。

### 4.1 拿到分布后怎样判断

| 实际差异分布 | 优先验证的方向（不是根因结论） |
|---|---|
| 全图零散，差值很小 | 采样种子、累积/降噪历史、数值路径 |
| 物体轮廓附近出现双边缘 | 视觉几何变换、渲染时相机姿态、帧同步 |
| 金属高光或阴影区域为主 | 光照、反射、材质或采样状态 |
| 只在布/绳表面 | 软体视觉网格、法线更新或上传状态 |
| 全图系统性亮度变化 | 曝光、色调映射、灯光或背景状态 |

掩码不会自动给出物体语义，需要和 A/A_again 叠对观察。差值小也不能直接关闭严格复现问题；是否修改合同是独立决策，本轮不修改。

## 5. 请用户运行的 GPU 测试

两个脚本使用现有 `.venv-gs121-nyx/bin/python` 和 `.external/nyx-assets`，保持 CUDA + Nyx + compact_lab。均复制源码、配置和仓库资产到新的结果目录并记录 SHA-256，再从副本执行；外部 Nyx 资源和引擎安装共享，未完整冻结。复制期发现文件内容变化则在测试启动前失败。

**先跑 RGB 诊断，再跑原有五项；两个脚本请串行运行。**每个脚本内部也串行，每个用例由独立进程承载；同一用例内部的反复 reset / Task 切换仍保持同一进程。单项失败会继续后面的用例，Ctrl+C 会中止。默认单项超时 3600 秒；失败时脚本非零退出是正常的失败回报，不代表后续用例一律未跑。

### P0：RGB 证据补齐（三个失败项 + 两个通过对照）

```bash
bash /home/jianwen/topogym/scripts/run_rgb_repro_checks.sh
```

执行 Cast Coil、Blanket、Rope、Cast Keyhole（ALOHA 刚体对照）、Knot（ALOHA FEM 对照）。沿用原完整生命周期测试路径、3 个 control step 和 seed 0→1→0，不把缩减 reset-only 用例冒充原失败路径复验。两个对照只用于初步区分场景相关性，不足以单独定位根因，也没有提供已知通过的 PBD 对照。

默认结果：`runs/test_results/rgb_repro_<UTC时间>_<PID>/`。优先回传：

- `checks/summary.json` 和 `checks/README.md`。
- 三个失败任务的 `checks/<task>/rgb_repro/comparison.json`；如路径仍在共享工作区，只需给结果目录。
- 若仍失败，保留完整目录中的 `A.png`、`A_again.png`、差异图、`report.json`、`steps.jsonl`、`.log` 和 `snapshot_manifest.json`，方便继续离线定位。

### P1：此前剩余五项公共机制验收

```bash
bash /home/jianwen/topogym/scripts/run_pending_simulator_checks.sh
```

| 用例 | 目的 |
|---|---|
| `stability_panda_robotiq` | 十轮重建、tick 上限、回溯、故障恢复、资源增长与关闭；复验第 8 轮崩溃 |
| `outputs_aloha` | RGB/录制/数据输出开关对 ALOHA 物理结果的影响 |
| `outputs_panda_robotiq` | 单臂版本的输出无干扰检查 |
| `installation` | 构建 wheel、源码目录外安装与运行/渲染 |
| `task_switch` | 同进程刚体→FEM→PBD→Hedgehog/Panda→刚体切换 |

默认结果：`runs/test_results/pending_five_<UTC时间>_<PID>/`，回传顶层 `summary.json` 或整个结果目录路径。如果已经执行过这五项，先提供现有结果，无需仅为本文再跑一次。这五项本身不覆盖三个 RGB 失败任务的像素诊断。

两个脚本均支持 `--help`、可选的新输出目录，以及 `TOPOGYM_TEST_PYTHON`、`TOPOGYM_VISUAL_ASSET_ROOT`、`TOPOGYM_TEST_TIMEOUT` 覆盖。正式回传时保留完整日志；原生崩溃可能没有完整录像或 Python finally 结果，不能因为缺少最终报告就丢弃该次运行。

## 6. 首轮结果后再决定的定位测试

以下是候选实验，**本轮没有新增相应可运行脚本，不需要现在全部运行**：

1. RGB 若重现：比较 reset-only A→A、reset-only A→B→A 与原完整生命周期路径；固定其他配置，每个实验独立进程。区分重建本身与前序推进/回溯历史的影响。
2. 对同一冻结源码重复同一试验，及比较两个全新进程的 seed=0 初态；记录所有相机原图。先估计复现频率，避免单次通过便认定修复。
3. 怀疑同状态重复渲染时，先确认确实触发新的 Nyx 渲染。普通 `observe()` / `render()` 可能复用 SensorFrame；重复读取同一个缓存帧不能证明渲染确定性。采样、降噪等参数的干预须逐项记录，并与标准配置结果分开。
4. 崩溃若重现：增加每轮 build/close 前后的记录，比较纯 reset、加入 rewind、加入故障注入、加入录制四种路径；再改变 Task 切换顺序或次数。无 RGB 对照只用来缩小渲染依赖范围，不能替代 Nyx 验收。
5. 内存定位同时记录进程 RSS、文件描述符、GPU 进程显存及已有 PyTorch 分配统计。PyTorch 的 CUDA 统计可能不覆盖原生渲染器全部分配，不足以单独排除显存问题。有新原生栈后再决定是否采集 native backtrace/core。

## 7. 本次本地验证与后续回填

- 仅离线执行 `tests/unit/test_rgb_repro_evidence.py`：**3 passed**。覆盖 0/255 差值方向与无溢出、阈值/包围框统计、PNG 无损回读、相等相机与失败相机共同保留、相机集合不匹配显式报错。
- 两个 shell 脚本通过 `bash -n`；新增脚本 `--help` 检查通过。
- GPU、模拟器生命周期、安装运行与跨任务切换：**本次未执行**。新增采集路径尚待真实运行验证，原问题仍开放。

拿到用户结果后回填：运行目录、源码清单、硬件/驱动/引擎版本、逐用例状态、逐相机差异分布、崩溃轮次/栈、对候选原因的支持或反证，以及下一项最小定位实验。单次通过只作为该次运行证据；关闭原问题需要可解释的修复与相应回归。

## 8. 用户 GPU 复验回填：2026-09-25

用户已运行两组测试。本次分析仅读取冻结源码、报告、原始 PNG、保存状态和录制元数据，独立重算像素统计，没有重新运行 GPU/模拟器，也没有修改断言或测试门槛。

- [五项机制 summary](../../runs/test_results/pending_five_20260925T153527Z_815590/summary.json) · [完整索引](../../runs/test_results/pending_five_20260925T153527Z_815590/README.md)。
- [RGB summary](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/summary.json) · [完整索引](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/README.md)。
- [本次独立复核数据](../../runs/test_results/rgb_repro_20260925T161109Z_852934/offline_review/independent_verification.json)：PNG/哈希/统计核对、初态物理与元数据对比、新旧源码差异清单、Panda 资源记录。

### 8.1 五项通过的实际含义

| 用例 | 报告与源码核对后的结论 | 范围限制 |
|---|---|---|
| Panda stability | `reset_cycle_0` 至 `reset_cycle_9` 全部通过，tick 上限、回溯、注入故障恢复、继续积分、关闭和旧句柄失效均完成 | 原第 8 轮崩溃本次没有复现；单次十轮不证明所有长期运行都安全 |
| outputs ALOHA | 12 次 control step 中，无 RGB/无消费者基线与有 RGB/录制/数据消费者结果通过物理容差检查 | 此处 ALOHA Task 为 Cast Coil；三个输出因素一起切换，未逐个做完整组合实验 |
| outputs Panda | 同上，Panda Task 为 Hedgehog | 不等于检验 RGB 像素确定性 |
| installation | wheel 非 editable 安装，源码目录外导入、建场景、3 次 step 与渲染通过 | 复用既有引擎依赖和指定模型/视觉资产；不代表一台全新机器的离线安装已验收 |
| task_switch | Cast Coil→Rope→Blanket→Hedgehog→Cast Coil 五段全部通过 | 本次单个序列不构成任意顺序/次数的长期稳定性保证 |

所有五项返回码为 0，驱动器报告运行期间源码变化列表为空。可把这五个具体待验收项登记为“本批次通过”；历史原生崩溃登记为“本轮未复现，根因未定”，不能据此声称已经修复。

Panda RSS 从第 1 轮约 2819.3 MiB 增至第 10 轮约 4304.0 MiB；测试采用第 4 轮作为 warmup 后基线，此后增加 599,920,640 字节（约 **572.1 MiB**），低于现有 1024 MiB 门槛，因而正确判为通过。后续轮次仍逐轮上升，尚未呈现平台期。文件描述符、PyTorch CUDA allocated/reserved 的 warmup 后增量为 0；这不覆盖所有 Nyx 原生分配。它提示继续观察长期内存增长，不能仅据十个样本认定泄漏或排除泄漏。

### 8.2 RGB 三项失败是不是测试误报

**未发现此次诊断采集或比较实现导致的误报。三项均真实违反现有严格逐像素复现要求，但证据不支持把它们描述成明显场景错位或物理初态失败。**

逐项核查得到：

1. Blanket、Rope、Keyhole 都已通过 reset、实际推进、中间回溯与继续积分、同 tick 缓存刷新、初态恢复；全部在 `seed_A_B_A` 的 `assert equal` 失败，退出码为 1，没有 SIGSEGV。PNG 采集函数已完成，没有路径、dtype 或保存异常。
2. 独立读取 A/A_again PNG，使用 int32 做差，重新计算全部 20 路相机的差异像素数、比例、平均/最大误差及阈值比例，与 `comparison.json` 完全相符；各诊断 PNG 哈希也匹配。
3. 各相机的 A.png 与 reset 阶段更早保存的 `initial_frames/*.png` 逐像素相同，排除了本轮 A 参考图被后续 step/缓存写入改掉这一解释。冻结源码中 A 数组和 Nyx→NumPy 读取均有显式 copy，采集不新增物理步进或渲染调用。
4. 对比的是两个不同 episode 的 seed=0、physics_step=0；三个失败任务的相机元数据、presentation 和生成资产哈希完全相同。
5. 独立对比保存的 A/A_again 物理数组：Blanket 702 个、Rope 795 个、Keyhole 720 个，均全部相同、最大绝对误差 0。Cast Coil 720 个、Knot 705 个也全部相同。这不覆盖尚未保存的渲染几何/法线、随机状态、内部缓存或原生内存。

当前测试足以证明“原完整生命周期路径之后，同 seed 原始 RGB 没有严格复现”。它尚不能证明 reset-only 最小用例也会失败；前序 rewind 与主动污染缓存的测试步骤是否为触发条件，仍需消融实验。严格门槛会把单个像素差 1 判为失败，这是目前明确采用的验收语义，而非统计程序的错误。若产品只要求视觉近似，需要另行定义门槛，不能直接把这些失败改成通过。

### 8.3 每路相机差异及空间分布

每幅图 848×480，共 407,040 像素。下表“最大差”指任一通道绝对差，量程 0–255；“平均差”以全图所有像素及三个通道为分母。

| Task / 相机 | 差异像素 | 全图比例 | 平均差 | 最大差 | 空间范围 / 观察 |
|---|---:|---:|---:|---:|---|
| Blanket / high、low、left wrist | 0 | 0 | 0 | 0 | 完全相同 |
| Blanket / right wrist | 6151 | 1.5112% | 0.005963 | 15 | bbox [258,17,463,239]；上方布面局部斑块 |
| Rope / high | 0 | 0 | 0 | 0 | 完全相同 |
| Rope / low | 4511 | 1.1082% | 0.004434 | 3 | bbox [385,337,559,480]；图像下方桌面及邻近绳段局部区域 |
| Rope / left wrist | 7 | 0.001720% | 0.00001146 | 2 | bbox [413,401,555,480]；底部零星像素 |
| Rope / right wrist | 9 | 0.002211% | 0.00001392 | 3 | bbox [417,401,554,480]；底部零星像素 |
| Keyhole / high | 4545 | 1.1166% | 0.004118 | 12 | bbox [545,49,719,222]；右侧机器人夹爪/臂附近区域，非中央金色任务物体主体 |
| Keyhole / low | 4 | 0.000983% | 0.00000491 | 1 | 零星像素 |
| Keyhole / left wrist | 2 | 0.000491% | 0.00000246 | 1 | 零星像素 |
| Keyhole / right wrist | 3 | 0.000737% | 0.00000246 | 1 | 零星像素 |
| Cast Coil / 全部四路 | 0 | 0 | 0 | 0 | 本次完整生命周期通过 |
| Knot / 全部四路 | 0 | 0 | 0 | 0 | 本次完整生命周期通过 |

主要差异图的逐像素最大通道差直方图还表明：Blanket 的 6151 个不同像素中 6041 个仅差 1，只有 2 个超过 10；Rope low 有 3976 个差 1、530 个差 2、5 个差 3；Keyhole high 的 4545 个不同像素中 4506 个仅差 1，2 个超过 10。整体属于**局部、绝大多数幅度很小，夹杂少数较大差值**，并非整幅画面系统性改变。

可直接对照原图和掩码（白色表示任一通道不同，不代表误差很大）：

- Blanket right wrist：[A](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/blanket_flatten/rgb_repro/cam_right_wrist/A.png) · [A again](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/blanket_flatten/rgb_repro/cam_right_wrist/A_again.png) · [mask](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/blanket_flatten/rgb_repro/cam_right_wrist/changed_mask.png)。
- Rope low：[A](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/rope_threading/rgb_repro/cam_low/A.png) · [A again](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/rope_threading/rgb_repro/cam_low/A_again.png) · [mask](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/rope_threading/rgb_repro/cam_low/changed_mask.png)。
- Keyhole high：[A](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/cast_keyhole/rgb_repro/cam_high/A.png) · [A again](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/cast_keyhole/rgb_repro/cam_high/A_again.png) · [mask](../../runs/test_results/rgb_repro_20260925T161109Z_852934/checks/cast_keyhole/rgb_repro/cam_high/changed_mask.png)。

### 8.4 为什么 Cast Coil 改为通过，Keyhole 改为失败

两个新批次的 `topogym/` 和 `configs/` 字节一致；测试差异仅为 RGB 证据接入和新增 helper/单元测试。相对旧 lifecycle 冻结源码，`configs/` 无变化，`topogym/` 有 6 个文件变化，涉及 Buzz、Horseshoe、Lock、Orbits 与共享 scene_presets；公共 simulator/world/sensors/recording 代码未变化。因此不能把整个新旧源码说成完全相同。

进一步核对这五个 RGB 任务的实际生成资产哈希、presentation、报告的包版本和 GPU 型号：新旧批次均相同。Nyx 为 gs-nyx 0.1.3 / plugin 0.1.4，Genesis 为 1.2.1，GPU 为 RTX 4090；外部视觉资源与依赖没有完整二进制冻结，不能由包版本相同推出所有外部输入都相同。

目前的变化是：Cast Coil 四路失败→四路通过；Blanket 四路失败→仅右腕失败；Rope 仍为 high 通过、其余失败；Keyhole 全通过→全失败；Knot 仍通过。它说明“固定只有三个特定任务不支持复现”这一解释不成立，也不能将 Cast Coil 一次通过视为修复。更合理的工作假设是存在随运行变化、并受场景/视角影响的渲染差异；尚未测得其发生概率。

三张主要掩码呈局部近圆形/椭圆形斑块，分别覆盖不同类型的表面，并非都沿软体轮廓或任务物体边缘分布。结合相同的已保存物理/相机数据，优先检查共享渲染状态：采样/去噪、光照相关中间量、视觉数据更新与缓存初始化/同步。当前配置为 FastPathTracer、spp=32、denoise=true、SMAA、Reinhard。**这些是排查方向，不足以断定某盏灯、降噪器、采样种子或未初始化缓冲就是根因。**

### 8.5 下一轮应缩小实验，不重复整套五项

五项机制测试已获得本批次通过证据，当前不需要原样再跑一遍。建议后续定位按以下顺序准备，以下新增实验尚未实现/执行：

1. 选 Keyhole（刚体，能避开软体因素）和 Blanket，固定本次 source 副本及外部资源身份，各自重复原用例数次，保留所有相机原图，估计差异稳定性和区域是否固定。
2. 对其中可复现的一项，比较 reset-only A→A、reset-only A→B→A、原完整路径，区分重建本身与前序 step/rewind/缓存检查。
3. 检查同一物理状态下真正重新渲染的原始输出；记录实际提交给 Nyx 的相机变换、视觉几何身份与渲染计数。普通重复 observe 读缓存不算这一实验。
4. 如前面仍指向渲染过程，固定其余条件，逐项切换 denoise、采样设置或相关光照；这些仅用于定位，标准配置的严格验收结果继续单列。
5. 生命周期作为独立支线，延长同一进程至 30–50 轮，记录 RSS 和 GPU 进程显存随轮次变化，确认是否最终平台化。当前资源增长仍值得追踪，但不应混入 RGB 根因结论。

当前结论：**五项公共机制本轮全部通过；RGB 诊断发现了真实的严格复现缺口，主要是局部小幅像素变化；尚无物理初态不同或明显几何错位的证据，具体渲染根因仍待定位。**

## 9. seed 能否控制，以及是否属于 Genesis 建场景随机变化

继续只读检查本次 RGB 测试冻结源码与本机已安装的引擎接口，没有运行 GPU 测试。

**不能由 pass/fail 变化直接推导出 Genesis 随机生成了不同模型。**同 seed 的生成资产、保存物理数组、相机元数据和 presentation 均相同，这不支持任务几何或摆位发生变化。Genesis 建场景/视觉状态更新到 Nyx 上传之间尚未被记录的网格、法线、内部状态或缓冲仍可能有变化；这种广义的初始化/运行非确定性不能排除，也尚未定位责任组件。“外观不稳定”不等于已经证明存在一个可设 seed 的随机数源。

本次实际 seed 调用链：

```text
Env.reset(seed=s)
  → seed_process(s)：Python random、NumPy、Torch、Torch CUDA RNG
  → Task / World：np.random.default_rng(s)
  → Genesis 首次初始化：gs.init(seed=s)
  → 每次构建：gs.set_random_seed(s)
  → Nyx 相机与 renderer：当前接入没有显式传递渲染 seed
```

冻结源码证据：[Env.reset](../../runs/test_results/rgb_repro_20260925T161109Z_852934/source/topogym/simulator/env.py)、[seed_process](../../runs/test_results/rgb_repro_20260925T161109Z_852934/source/topogym/utils/variant_rng.py)、[GenesisWorld.from_tabletop](../../runs/test_results/rgb_repro_20260925T161109Z_852934/source/topogym/world/genesis_world.py)、[Nyx 相机接入](../../runs/test_results/rgb_repro_20260925T161109Z_852934/source/topogym/sensors/renderers/nyx.py)。

本机 Genesis 1.2.1 的 `set_random_seed` 实现设置 Python、NumPy、Torch CPU/CUDA RNG，未调用 Nyx seed 接口。Genesis 初始化还把初始 seed 传给 Quadrants 初始化，但后续 `set_random_seed` 不重置 Quadrants RNG；实现注释称仅允许确定性 Quadrants 操作。这是调用覆盖范围的事实，不是本次像素差异来自 Quadrants 的证据。

在已安装 gs-nyx 0.1.3 / gs-nyx-plugin 0.1.4 的 `NyxCameraOptions`、`nyx_py_renderer.pyi`、`nyx_py_sdk.pyi` 中，未找到公开的渲染 seed 设置字段/方法。不能因此断言原生实现没有固定采样序列或隐藏接口；能确认的是目前未建立“episode seed 控制 Nyx 所有随机/历史状态”的显式链路。

| 假设来源 | seed 的作用 |
|---|---|
| 未接入的渲染伪随机采样 | 接入并在对应边界重置其 RNG，可能解决该来源；还需保持相同输入和采样调用序列 |
| 累积/去噪/帧计数等历史状态 | 仅重新设置 RNG seed 不足，需要对应状态清零或恢复 |
| 原生缓冲初始化、异步同步或数据竞争问题 | seed 不能替代初始化与同步修复 |
| 浮点执行顺序差异 | 仅 seed 不提供逐位确定性保证，需要另查运算路径 |

因此：**当前 `reset(seed=0)` 已在使用，实测仍不够；这些差异将来能否通过补齐 renderer seed 解决，取决于尚未定位的来源。**不要通过换 seed 寻找恰好通过的图像来关闭问题；应保持任务 seed 固定，先区分场景重建、渲染重采样和历史状态三个因素。

## 10. 静态场景重复渲染与销毁重建实验：已实际执行

### 10.1 执行边界与证据

用户授权本实验后，在 RTX 4090 上实际运行。沙箱内无法访问驱动，经授权的沙箱外执行路径可用。实验脚本位于仓库外的临时工作目录：

- [实验脚本](/home/jianwen/tmp/topogym_rgb_repeat_20260925/run_probe.py) · [说明](/home/jianwen/tmp/topogym_rgb_repeat_20260925/README.md) · [独立离线核查脚本](/home/jianwen/tmp/topogym_rgb_repeat_20260925/analyze_probe.py)。
- [Keyhole 两组结果](../../runs/test_results/static_rgb_20260925_keyhole_02/README.md) · [summary](../../runs/test_results/static_rgb_20260925_keyhole_02/summary.json)。
- [Blanket / Rope 四组结果](../../runs/test_results/static_rgb_20260925_soft_04/README.md) · [summary](../../runs/test_results/static_rgb_20260925_soft_04/summary.json)。
- [六组独立复核结果](../../runs/test_results/static_rgb_20260925_analysis/verification.json)。

没有修改当前 `topogym/topogym/` 下的源码或已安装的引擎文件。实验读取上次 `rgb_repro_20260925T161109Z_852934/source`，核对全部 manifest 哈希后复制到本次结果目录，再从副本执行。两份有效批次均确认测试副本未变化、外部 Nyx 视觉资产运行前后哈希相同；安装的引擎库共享，未做完整二进制冻结。

重跑入口（本轮已经跑完，无需用户再跑）：

```bash
/home/jianwen/topogym/.venv-gs121-nyx/bin/python -u \
  /home/jianwen/tmp/topogym_rgb_repeat_20260925/run_probe.py
```

脚本默认串行运行三个任务的两种模式，新建独立结果目录；支持 `--tasks`、`--modes`、`--builds`、`--repeats`。

### 10.2 如何保证是真渲染且没有推进物理

每个 Task 有两个独立进程，每个进程内连续执行三次 `Env.reset(seed=0)`。reset 释放旧 World 并新建场景。未插入 seed=1，也没有 step、rewind、故障注入或参数修改。

| 模式 | 每次建场景后的操作 | 目的 |
|---|---|---|
| control | 保存 reset 初帧，然后进入下次同 seed 重建 | 只重建、不额外渲染的初帧对照 |
| repeat | 保存 reset 初帧，再强制整套四路相机重渲染 8 次 | 同一场景内部变化；以及不同重建的相同渲染序号比较 |

强制路径为 `env._sensors.invalidate(); env.observe()`，经既有 SensorSuite 刷新整个 Nyx 相机组。外部脚本仅在当前诊断进程内包装实际 Nyx Python renderer 的 `render` 方法进行成功调用计数；原方法内部调用 native `render_frame`。每次强制采样都要求四个相机索引各调用一次，普通 `observe()/render()` 则作为反向对照，要求 native 渲染调用增量为 0。计数包装在首次正常 reset 后安装，避免改变引擎插件初始化顺序，因此首次 reset 的计数明确为 null。

这里证明调用确实到达 native `render_frame`，排除了只读 TopoGym/Sensor 缓存的伪实验；没有声称清除或完整观测了 native 内部所有缓存、帧计数和历史状态。

所有有效重复帧均检查：World 对象未更换，episode/state ID 未变化，Genesis `scene.t` 与 physics_step 始终为 0，历史长度始终为 1，保存的物理数组完全一致，相机元数据相同。跨重建还检查相同 seed 的生成资产哈希、物理数组和相机元数据一致。

共完成 **6 个有效用例、18 次建场景、72 次额外四路重渲染**。独立离线检查了 90 组四路 PNG（360 张）及 90 份物理 NPZ：所有 PNG 哈希匹配，像素统计独立重算一致，每个用例内保存物理数组逐项相同。用例报告的 `completed` 表示实验操作及不变量检查成功，不表示 RGB 相等。

实际场景证据视频由已有 RuntimeEvidence/RecordingSession 生成，每次建场景只录真实 tick=0 初帧。例如：[Keyhole high](../../runs/test_results/static_rgb_20260925_keyhole_02/cast_keyhole_repeat/branch_000/videos/cam_high.mp4) · [Blanket high](../../runs/test_results/static_rgb_20260925_soft_04/blanket_flatten_repeat/branch_000/videos/cam_high.mp4) · [Rope high](../../runs/test_results/static_rgb_20260925_soft_04/rope_threading_repeat/branch_000/videos/cam_high.mp4)。这些是单帧场景证据，不是运动或任务 demo。同一 state 的重复渲染保留为无损 PNG 序列，没有伪造物理时间或 state ID 来拼视频。

### 10.3 实际结果：重建不是像素变化的必要条件

下表计数单位为“一组四路图像比较”，任一路不同就记为不同。重建初帧为第 2、3 次建场景分别对比第 1 次，共 2 次；后续相邻帧排除每次初帧→首次重渲染，共 3×7=21 次。

| Task | control 重建初帧不同 | repeat 重建初帧不同 | 初帧→首次重渲染不同 | 后续相邻重渲染不同 | 首次变化最大通道差 | 后续变化最大通道差 |
|---|---:|---:|---:|---:|---:|---:|
| Cast Keyhole | 1/2 | 1/2 | 3/3 | **6/21** | 72 | 12 |
| Blanket Flatten | 1/2 | 1/2 | 3/3 | **8/21** | 95 | 11 |
| Rope Threading | 1/2 | 1/2 | 3/3 | **8/21** | 72 | 12 |

这不是变化概率估计：比较共享同一进程和初态、样本很少，并非独立同分布试验。

本次应区分两个观察：

1. **初帧与第一次额外渲染存在较大差异。**三项的三个 episode 均发生，部分差异沿物体轮廓分布。可能涉及首次渲染/视觉更新状态；尚未确认具体机制，不能直接解释为物理位姿变化。
2. **排除第一次额外渲染后，仍有局部小幅变化。**一些 episode 后续帧完全稳定，另一些 episode 在多种像素结果间反复变化。不能以“预热一次，丢掉第一张”作为已验证修复。

Keyhole 的第 3 个 episode 中，r01→r02 的 high 图有 4525 个不同像素、最大差 12；此前 A→B→A 失败的 high 图有 4545 个不同像素、最大差 12。两张差异掩码交集 4491 像素、并集 4579 像素，**IoU=98.078%**，见[掩码重合统计](../../runs/test_results/static_rgb_20260925_analysis/mask_overlap.json)。这强烈支持本次静态重渲染捕获了与此前失败相关的局部现象，但空间重合本身还不能证明唯一共同根因。

代表性无损差异：

- Keyhole 初帧→首次重渲染：[原图](../../runs/test_results/static_rgb_20260925_keyhole_02/offline_analysis/initial_vs_first/cam_high/A.png) · [新图](../../runs/test_results/static_rgb_20260925_keyhole_02/offline_analysis/initial_vs_first/cam_high/A_again.png) · [mask](../../runs/test_results/static_rgb_20260925_keyhole_02/offline_analysis/initial_vs_first/cam_high/changed_mask.png)。
- Keyhole 后续局部变化：[原图](../../runs/test_results/static_rgb_20260925_keyhole_02/offline_analysis/later_toggle/cam_high/A.png) · [新图](../../runs/test_results/static_rgb_20260925_keyhole_02/offline_analysis/later_toggle/cam_high/A_again.png) · [mask](../../runs/test_results/static_rgb_20260925_keyhole_02/offline_analysis/later_toggle/cam_high/changed_mask.png)。
- Blanket 后续局部变化：[mask](../../runs/test_results/static_rgb_20260925_soft_04/offline_analysis/blanket_flatten/cam_high/changed_mask.png)；取第一组发生变化的后续相邻帧 b01_r01→b01_r02。
- Rope 后续局部变化：[mask](../../runs/test_results/static_rgb_20260925_soft_04/offline_analysis/rope_threading/cam_high/changed_mask.png)；取第一组发生变化的后续相邻帧 b00_r02→b00_r03。

### 10.4 对原因及 seed 的判断更新

**已经排除“必须重新随机建模/销毁重建才会变化”这一必要条件。**当前应优先检查同场景渲染调用过程及其状态：采样、去噪/其他后处理、原生帧计数或时钟、视觉数据更新/同步及缓冲状态。普通重渲染仍经过既有视觉状态刷新和上传，所以实验还没有把 Genesis 视觉更新与 Nyx native 渲染彻底拆开，不能直接将根因锁定为 Nyx 某个 shader。

物理状态固定不等于渲染器内部全部输入固定；内部帧计数、墙钟时间、随机序列位置或缓冲状态可能仍变化。本实验没有在各帧之间重新设 seed，也没有对 renderer RNG 做干预，因此**不能仅凭这些结果断言随机采样是原因，或断言 renderer seed 一定能/不能修复**。如果变化来自可控伪随机序列，需要识别并控制该序列；如果来自更新/初始化/同步，仍需要对应的代码修复。

下一项有区分力的定位是把“正常刷新视觉数据后渲染”与“保持实际上传的相机/几何数据不变，直接调用 native renderer”做对照，再单独检查帧推进、降噪与采样。上述更细实验本轮未执行；本轮没有通过增加预热次数、改图像容差或改物理/渲染配置来掩盖差异。

### 10.5 调试过程中的无效/中断批次

首次 `static_rgb_20260925T192559Z` 在提前导入 Nyx 插件时触发 Python 初始化顺序异常，没有进入正式采样，六个 worker 均失败。外部脚本改为首次正常 reset 后再取得并包装实际 renderer 类；该失败保留为诊断脚本问题，不作为 simulator 失败。

`static_rgb_20260925_soft_03` 的驱动器返回 143，未产出完整批次 summary；没有留下原生崩溃栈，终止原因未确定。确认无遗留进程后在新目录 `soft_04` 重跑，四项全部正常返回 0。中断批次不计入上面的正式统计，也不将它直接解释成原有 SIGSEGV 复发。
