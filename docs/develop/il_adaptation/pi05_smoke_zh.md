# TopoGym H5 → π0.5 (OpenPI) 数据加载冒烟

> 日期：2026-07-21；2026-08-04 改为任务参数化
> 目标（明确窄化）：**一条 H5 → 转成 LeRobot 数据集 → 跑通 OpenPI 的 `compute_norm_stats` + `train.py` 几个 step，不报 shape/格式错**。不是训 baseline。
> 关系：这是 `robomme_pipeline_roadmap_zh.md` 之后、验证"我们的数据格式能否作为 IL 输入"的一步。
> 计算/训练步骤跑在用户的 Linux/GPU 机上（sim/训练由用户本人执行）。

**任务参数化。** 本链路与任务无关：三个脚本（`export_h5_lerobot.py` / `register_openpi_config.py` /
`pi05_smoke.sh`）都接受任务名，形状从 H5 首帧推断，`repo_id` 从 H5 的 `setup.attrs.task_id` 派生。
可选任务 = `bash_scripts/tests/verify_dataset_recording.sh` 的 `TASKS` 表里的键。

本文全程以 **`swap`** 为示例，因为它是首个端到端跑通的任务（纯刚体，物理不污染结论）；把命令里的
`swap` 换成别的任务名即可。swap 任务本身已归入 `topogym/tasks/legacy/`（不考察四类空间关系，
见 `../framework/task_taxonomy_zh.md`），但仍是本冒烟链路的默认任务，直到另一个任务达到同等就绪度。

---

## 0. 一句话结论（先读这个）

我们录的 H5 已经是 VLA 形态，且**关键的 state(8)/actions(7)/双图像形状恰好和 OpenPI 的 Libero 样例一致**。所以：

- 转换器只是 OpenPI `examples/libero/convert_libero_data_to_lerobot.py` 的"换数据源"版本，输出**相同的 feature 名**（`image` / `wrist_image` / `state` / `actions` / `task`）。
- OpenPI 侧因此**直接复用 `LeRobotLiberoDataConfig` + `libero_policy` 变换**，新增的 TrainConfig 基本就是 `pi05_libero` 换个 `repo_id`，**不需要写自定义 transform**。

真正的数据格式硬门是 **`compute_norm_stats`**（不加载模型，最便宜）；`train.py` 是次级验收（要下载 π0.5 基座 + GPU）。

---

## 1. 字段映射（H5 → LeRobot）

| LeRobot feature | 来源（H5） | 形状 / 说明 |
| --- | --- | --- |
| `image` | `obs/front_rgb` | uint8 HxWx3（原录制分辨率，OpenPI 内部 resize 到 224） |
| `wrist_image` | `obs/wrist_rgb` | uint8 HxWx3；**若场景无 wrist 相机则零填充** |
| `state` | `obs/joint_state`(7) ⊕ `mean(obs/gripper_state)` | float32 (8,) |
| `actions` | `action/ee_pose_action`(7) | float32 (7,)：xyz + 四元数 |
| `task`（→prompt） | `setup.attrs.task_goal` | 字符串（靠 `prompt_from_task=True` 变成 prompt） |

转换器：本 repo `scripts/export_h5_lerobot.py`。它**不 import topogym**（跑在 OpenPI 的 uv 环境里，只用 `h5py`+`numpy`+`lerobot`），H5 读取内联，形状从首帧自动推断。

---

## 2. 端到端命令

> 一键版：装完 OpenPI（步骤 0）后，`bash bash_scripts/tests/pi05_smoke.sh [task]` 会把 stage 0..5 串起来跑并逐段检验（不给 task 则默认 `swap`；`TO_STAGE=4` 停在便宜的数据门、不 train；改完 config 后 `FROM_STAGE=3` 续跑）。产物按任务分目录落在 `runs/pi05_smoke/<task>/`。下面是等价的手动分解命令。
>
> 约定：本 repo 根 = `$TOPOGYM`；OpenPI 装在 `$TOPOGYM/.external/openpi`（`.external/` 已 gitignore）。
> 命令里的 `swap` 可替换为任意已登记任务。

```bash
# ---- 0. 安装 OpenPI（一次；Ubuntu + NVIDIA GPU）----
cd "$TOPOGYM"
bash env_setup_vla_openpi.sh
cd .external/openpi && uv run python -c "from openpi.training import config; print('ok')"

# ---- 1. 产一条干净的 H5（在 topogym 的 Genesis venv 里）----
cd "$TOPOGYM"
bash bash_scripts/tests/verify_dataset_recording.sh swap
#   -> runs/dataset_tests/<ts>/swap_seed0.h5
#   若帧数太少（<~20），降低 EVERY：EVERY=5 bash bash_scripts/tests/verify_dataset_recording.sh swap

# ---- 2. 转成 LeRobot 数据集（在 OpenPI 的 uv 环境里跑，因为要 lerobot）----
cd "$TOPOGYM/.external/openpi"
uv run python "$TOPOGYM/scripts/export_h5_lerobot.py" \
    "$TOPOGYM"/runs/dataset_tests/<ts>/swap_seed0.h5
#   --repo-id 不给时默认 topogym/<task_id>_smoke，task_id 读自 H5 的 setup attrs
#   -> $HF_LEROBOT_HOME/topogym/swap_smoke（HF_LEROBOT_HOME 由 env_setup 的 HF_HOME 派生 / 默认 ~/.cache）

# ---- 3. 注册 TrainConfig 进 config.py（自动，幂等；等价手动 diff 见第 3 节）----
cd "$TOPOGYM"
uv run --project "$TOPOGYM/.external/openpi" python scripts/register_openpi_config.py --task swap
#   --config-name / --repo-id 不给时由 --task 派生：pi05_topogym_<task> / topogym/<task>_smoke

# ---- 4. 归一化统计（第一个硬门：完整跑数据加载+transform，不加载模型）----
cd "$TOPOGYM/.external/openpi"
uv run scripts/compute_norm_stats.py --config-name pi05_topogym_swap
#   注意 config 名是 --config-name 旗标（不是位置参数）；train.py 才是位置子命令。
#   通过 = 无 shape/dtype/字段异常，assets 目录里写出 norm_stats.json

# ---- 5. 跑几个 train step（最终验收；首次会拉 π0.5 基座 checkpoint 数 GB + 需 GPU）----
WANDB_MODE=disabled uv run scripts/train.py pi05_topogym_swap --exp-name=swap_smoke --overwrite
#   WANDB_MODE=disabled 关掉 wandb（否则无 TTY/api_key 时训练前就报错）；config 里也已 wandb_enabled=False。
#   config 里已把 num_train_steps 设成 5；通过 = 打印出 step 0..4 的 loss，无 shape/格式异常
```

---

## 3. OpenPI 侧改动（`.external/openpi` 不在本 repo 版本控制）

**推荐：自动注册（幂等 + 可更新）。** `scripts/register_openpi_config.py` 把下面的 TrainConfig 以"追加到 config.py 末尾"的形式注册（`_CONFIGS.append(...)` + 更新 `_CONFIGS_DICT`，避开脆弱的列表插入）。它按**由 config 名派生的起止 marker 对**界定自己那段：**已是当前内容→no-op；是旧版本（如全参微调）→只就地更新该段；没有→追加**，所以模板变了（如全参→LoRA）重跑就会同步；OpenPI 被重新 sync/clone 冲掉再跑一次即可。marker 带 config 名意味着**多个任务的 block 可以共存**——注册 `pi05_topogym_cable_routing` 不会删掉已有的 `pi05_topogym_swap`。2026-08 之前写入的单 marker 旧块会被识别并清理，不会留下重名注册。`bash_scripts/tests/pi05_smoke.sh` 的 stage 3 默认每次都调它（`AUTO_CONFIG=0` 可关）。

```bash
uv run --project .external/openpi python scripts/register_openpi_config.py --task swap
```

**为什么是 LoRA/低显存版**：全参微调 pi0.5（~3.3B）用 AdamW 需 ~50GB（参数 + Adam m/v + 梯度 + EMA），单卡 24GB 会在 `init_train_state` OOM。LoRA 冻结基座、只训适配器（`get_freeze_filter()` + `ema_decay=None`），基座常驻但省掉那 ~40GB 优化器/梯度/EMA 状态，够在消费级卡上把"数据进训练循环 + 跑几步"证完。全参版留给多卡 / 80GB 卡。

**等价的手动 block**（`AUTO_CONFIG=0` 或想自己粘时）：加到 `src/openpi/training/config.py` 的 `_CONFIGS` 里（末尾追加或列表内均可）。LoRA 变体在 `model` 和 `freeze_filter` 里要一致：

```python
    TrainConfig(
        name="pi05_topogym_swap",
        model=pi0_config.Pi0Config(
            pi05=True, action_horizon=10, discrete_state_input=False,
            paligemma_variant="gemma_2b_lora", action_expert_variant="gemma_300m_lora",
        ),
        data=LeRobotLiberoDataConfig(
            repo_id="topogym/swap_smoke",       # 必须与 export_h5_lerobot.py 的 --repo-id 一致
            base_config=DataConfig(prompt_from_task=True),
            extra_delta_transform=False,
        ),
        batch_size=4,                            # 小数据集：norm_stats 的 num_batches=len//batch_size，别设大
        num_workers=0,                           # 冒烟规避多进程 dataloader 边角情况
        num_train_steps=5,                       # 只求跑通几步
        wandb_enabled=False,                     # 冒烟不上传 wandb（否则无 TTY/api_key 时训练前报错）
        lr_schedule=_optimizer.CosineDecaySchedule(
            warmup_steps=1, peak_lr=5e-5, decay_steps=100, decay_lr=5e-5,
        ),
        optimizer=_optimizer.AdamW(clip_gradient_norm=1.0),
        freeze_filter=pi0_config.Pi0Config(
            pi05=True, action_horizon=10, discrete_state_input=False,
            paligemma_variant="gemma_2b_lora", action_expert_variant="gemma_300m_lora",
        ).get_freeze_filter(),                   # LoRA 冻结基座
        ema_decay=None,                          # LoRA 关 EMA
        weight_loader=weight_loaders.CheckpointWeightLoader(
            "gs://openpi-assets/checkpoints/pi05_base/params"
        ),
    ),
```

`pi0_config` / `_optimizer` / `weight_loaders` / `DataConfig` / `LeRobotLiberoDataConfig` 都已在 config.py 顶部 import。若 LoRA 后仍 OOM，进一步降 `batch_size`（4→1）或设 `XLA_PYTHON_CLIENT_MEM_FRACTION=0.9`。

---

## 4. 预期撞到的 schema 缺口（是发现，不是本轮要修）

1. **动作是 7 维绝对四元数位姿**。π0.5/OpenPI 惯例是 joint/ee 增量或绝对 joint；对四元数做 min-max/mean-std 归一化在数学上无意义。冒烟"跑几步不报错"不受影响，但这是我们数据 schema 与 VLA 训练约定的**真实差距**。后续选项：改导出 `waypoint_action` / joint 动作，或把旋转换成 6D 表示。
2. **图像分辨率是 demo 录制分辨率**，OpenPI 内部 resize 到 224。不阻塞。
3. **state 选了 joint(7)+gripper(1)**（比 quat 干净）。若后续想 state/action 同构，需一并重议。

---

## 5. 排障备注

- **帧数不足**：LeRobot/OpenPI 按 `action_horizon=10` 取动作块。单 episode 建议 ≥ ~20 帧；不够就降 `--dataset-every-n-steps`（脚本里 `EVERY`）重录。
- **`compute_norm_stats` num_batches=0**：说明 `batch_size` 比帧数还大 —— 保持 `batch_size=4` 或调更小。
- **wrist 全零**：若场景没有 wrist 相机，转换器会零填充 `wrist_image`；`libero_policy.LiberoInputs` 对缺失 wrist 有 mask 处理，不阻塞冒烟。
- **train 显存/下载太重**：`compute_norm_stats` 已是干净的数据格式门；`train.py` 若因显存或 checkpoint 下载受阻，不影响"数据格式 OK"的结论，按需再跑。
- **CLI 名以 clone 内为准**：`train.py` 走 `_config.cli()`（tyro over 配置名），字段即 flag（`--exp-name` / `--overwrite` / `--num-train-steps`）；`compute_norm_stats.py` 是 `main(config_name, max_frames=None)`。
