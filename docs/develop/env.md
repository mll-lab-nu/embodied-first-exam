# TopoGym 环境依赖清单

> 状态：**初版依赖盘点**，用于建 Python 虚拟环境时一次配齐。版本约束按 2026-05 的官方文档 + 我们框架真正用到的能力推导而来；未来真要装的时候按各包的最新稳定版微调。
>
> 推荐工具链：**`uv`**（与 topobench 风格一致，比 `pip` + `virtualenv` 快十几倍，且能 lock 跨平台）。

---

## 0. 基础环境（OS / Python / GPU）

| 项 | 推荐 | 备注 |
| --- | --- | --- |
| OS | **Linux**（Ubuntu 22.04+ 推荐） | Genesis 官方推荐；macOS/Windows 也行，但渲染和性能受限 |
| Python | **3.10 ≤ X < 3.14**（推荐 **3.11**） | Genesis 硬约束 `>=3.10,<3.14`；3.11 是 CI 测过最稳的 |
| NVIDIA Driver | CUDA 12.x 配套 driver（≥ 535） | Genesis 主推 NVIDIA + CUDA；AMD ROCm / Apple Metal 可跑但非一线 |
| CUDA Toolkit | **12.1 / 12.4 / 12.6** 任选一 | 关键是和 PyTorch wheel 匹配（见 §2） |
| GPU 显存 | ≥ 24 GB（推荐） | n_envs=128~1024 训练时显存大；MVP 小批量 8 GB 也能跑 |

---

## 1. 物理仿真核心

| 包 | 最低版本 | 用途 | 谁直接 import |
| --- | --- | --- | --- |
| **`genesis-world`** | `>= 0.4.5` | 物理仿真器主体 | 模块 A / C / D |
| `taichi` | 跟随 Genesis 指定 | Genesis 内部计算后端 | 自动随 genesis 装 |
| `numpy` | `>= 1.24` | 张量基础设施 | 全栈 |
| `scipy` | `>= 1.11` | 线代 / 数值（IK / FK 数值解、随机分布等） | C / B |

**安装命令**：
```bash
# 先按 PyTorch 官方说明装 torch（见 §2），然后：
pip install "genesis-world>=0.4.5"
```

> ⚠️ Genesis 的某些可选组件（ParticleMesher、splashsurf 用于流体可视化；LuisaCompute 用于光追渲染）**MVP 阶段不需要**，等真需要 photorealistic 渲染再装。

---

## 2. RL 训练栈

| 包 | 最低版本 | 用途 | 谁直接 import |
| --- | --- | --- | --- |
| **`torch`** | `>= 2.4`，CUDA 12.x 匹配 | 神经网络 + 优化器 + 张量后端 | E（TorchPolicy）/ G1 |
| **`rsl-rl-lib`** | `>= 5.0.0` | PPO / SAC + 训练循环（Genesis 官方推荐） | G1 |
| **`gymnasium`** | `>= 0.29` | F 的标准 VectorEnv 接口 | F |
| `tensordict` | `>= 0.5`（可选） | 批量字典张量；rsl-rl 内部用 | 间接 |

**PyTorch 安装**（必须按 CUDA 版本选对 wheel；Genesis 不替你装 torch）：
```bash
# 以 CUDA 12.6 为例（按实际 driver/toolkit 调）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

---

## 3. Policy 子类需要的库（按需选装；做成 optional extras）

E 是多子类的统一插槽——不同子类依赖完全不同的外部库。把每类做成 `pyproject.toml` 的一个 extra，**用户用什么 policy 就装什么 extra**，不强制全装。

### 3.1 OpenVLA / RT-2 / π₀ 等本地 VLA 模型（extra `vla`）

| 包 | 最低版本 | 用途 |
| --- | --- | --- |
| `transformers` | `>= 4.45`（按 OpenVLA 要求） | 加载 HF 模型 |
| `accelerate` | `>= 0.30` | 多 GPU 推理 / FP16 |
| `bitsandbytes`（可选） | `>= 0.43` | 4 / 8-bit 量化推理 |
| `flash-attn`（可选） | `>= 2.5` | OpenVLA 推理加速；编译有坑，谨慎装 |
| `peft`（可选） | `>= 0.11` | LoRA 微调 |
| `sentencepiece` | `>= 0.2` | tokenizer |
| `huggingface-hub` | `>= 0.24` | 模型下载 |

### 3.2 远端 VLM API（extra `vlm`）

| 包 | 最低版本 | 用途 |
| --- | --- | --- |
| `openai` | `>= 1.40` | GPT-4V / GPT-5 系列 |
| `anthropic` | `>= 0.34` | Claude 系列 |
| `google-genai` | `>= 0.5` | Gemini 系列（新 SDK 名 `google-genai`，不是旧 `google-generativeai`） |
| `httpx` | `>= 0.27` | 自托管 OpenAI-compatible 端点 |
| `tenacity` | `>= 8.5` | 重试 / 限流 |

### 3.3 模仿学习 / 离线 RL 算法（extra `il`，后期）

| 包 | 最低版本 | 用途 |
| --- | --- | --- |
| `torchrl`（可选） | `>= 0.5` | 备选 RL 算法库 |
| `diffusers`（可选） | `>= 0.30` | Diffusion Policy 风格的 policy |

---

## 4. 数据 I/O（extra `data`）

模块 G2 的存储后端按 Recorder 选哪种格式装哪种。MVP 先支持 HDF5 + Zarr 两种内部格式，LeRobot / RLDS 作 converter。

| 包 | 最低版本 | 用途 |
| --- | --- | --- |
| **`h5py`** | `>= 3.11` | HDF5 落盘 |
| **`zarr`** | `>= 2.18` | Zarr 落盘（更大数据集 / chunked 读取友好） |
| `lerobot`（可选） | 跟随 HF | LeRobot 标准数据集格式 |
| `tensorflow-datasets`（可选） | `>= 4.9` | RLDS 格式（如要发到 HF） |
| `pyarrow` | `>= 16` | parquet / 列存 |

---

## 5. 配置与命令行

| 包 | 最低版本 | 用途 | 谁用 |
| --- | --- | --- | --- |
| **`hydra-core`** | `>= 1.3` | YAML 组合配置 | 全栈（H：config） |
| **`omegaconf`** | `>= 2.3` | 配置对象 | 全栈 |
| `pydantic` | `>= 2.8` | 强类型 schema（spec dataclass 校验） | 全栈 |
| `typer` | `>= 0.12` | CLI 入口 | H（cli） |
| `rich` | `>= 13` | 漂亮终端输出 | H（logging） |

---

## 6. 观测 / 可视化 / 评测产物

| 包 | 最低版本 | 用途 | 谁用 |
| --- | --- | --- | --- |
| `Pillow` | `>= 10` | 图像编解码 | D / G2 / G3 |
| `imageio` | `>= 2.34` | GIF / MP4 写出 | G3 |
| `imageio-ffmpeg` | `>= 0.5` | MP4 后端 | G3 |
| `opencv-python`（可选） | `>= 4.10` | 图像 resize / 标注 | D |
| `matplotlib` | `>= 3.9` | 训练曲线 / metric 图 | G1 / G3 |
| `tensorboard` | `>= 2.16` | RL 训练日志 | G1 |
| `wandb`（可选） | `>= 0.17` | 远端实验追踪 | G1 |

---

## 7. 逆运动学（IK）

模块 C 在 EE-pose 或 primitive 模式下需要 IK。**MVP 先用 Genesis 自带 IK**（无额外依赖）；如果精度 / 速度不够再上以下之一：

| 包 | 用途 |
| --- | --- |
| `pyroboplan`（可选） | 纯 Python，基于 pinocchio，CPU |
| `placo`（可选） | 二次规划 IK，CPU |
| `curobo`（可选） | NVIDIA 出品，GPU batched IK，**性能最好但编译复杂** |

---

## 8. 开发工具（extra `dev`）

| 包 | 最低版本 | 用途 |
| --- | --- | --- |
| `pytest` | `>= 8` | 单测 / contract test / smoke test |
| `pytest-xdist` | `>= 3.6` | 并行测试 |
| `ruff` | `>= 0.6` | linter + formatter（一站式） |
| `pyright`（或 `mypy`） | `pyright >= 1.1.380` | 类型检查 |
| `pre-commit` | `>= 3.8` | 钩子 |
| `ipython` | `>= 8` | 交互调试 |
| `jupyter` / `notebook`（可选） | — | 实验性 notebook |

---

## 9. 推荐的 `pyproject.toml` extras 布局

```toml
[project]
name = "topogym"
version = "0.0.1"
requires-python = ">=3.10,<3.14"
dependencies = [
  # 核心 - 总是要装
  "genesis-world>=0.4.5",
  "torch>=2.4",
  "rsl-rl-lib>=5.0.0",
  "gymnasium>=0.29",
  "numpy>=1.24",
  "scipy>=1.11",
  "hydra-core>=1.3",
  "omegaconf>=2.3",
  "pydantic>=2.8",
  "typer>=0.12",
  "rich>=13",
  "Pillow>=10",
  "matplotlib>=3.9",
  "tensorboard>=2.16",
  "imageio>=2.34",
  "imageio-ffmpeg>=0.5",
  "h5py>=3.11",      # 默认数据后端先到位
]

[project.optional-dependencies]
vla      = ["transformers>=4.45", "accelerate>=0.30", "sentencepiece>=0.2", "huggingface-hub>=0.24"]
vla_fast = ["flash-attn>=2.5", "bitsandbytes>=0.43"]   # 可选加速
vlm      = ["openai>=1.40", "anthropic>=0.34", "google-genai>=0.5", "httpx>=0.27", "tenacity>=8.5"]
data     = ["zarr>=2.18", "pyarrow>=16", "lerobot"]
il       = ["torchrl>=0.5", "diffusers>=0.30"]
viz      = ["opencv-python>=4.10", "wandb>=0.17"]
ik       = ["pyroboplan", "placo"]    # MVP 不必装
dev      = ["pytest>=8", "pytest-xdist>=3.6", "ruff>=0.6", "pyright>=1.1.380", "pre-commit>=3.8", "ipython>=8"]
all      = ["topogym[vla,vlm,data,viz,dev]"]
```

---

## 10. 推荐的环境创建步骤（uv 流程）

```bash
# 1. 进入 topogym 仓库根目录
cd /projects/bfuo/jlyu3/topogym

# 2. 安装 uv（如果还没装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. 创建虚拟环境（Python 3.11）
uv venv --python 3.11

# 4. 装 PyTorch（按 CUDA 版本选 wheel；以 CUDA 12.6 为例）
uv pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126

# 5. 装 topogym + 想要的 extras
uv pip install -e ".[vla,vlm,data,dev]"

# 6. 验证 Genesis 能用 GPU
.venv/bin/python -c "import genesis as gs; gs.init(backend=gs.cuda); print('Genesis OK')"

# 7. 验证 rsl-rl 能 import
.venv/bin/python -c "import rsl_rl; print('rsl-rl OK')"
```

---

## 11. 自托管模型的注意事项（可选 / 后期）

如果想跑自托管 VLM/VLA（参考 topobench 的 `bin/setup_*.sh`），每种模型常需要**独立的 venv**，因为它们的 torch/CUDA pins 会互相冲突。例如：
- BAGEL 自带特定 torch
- ThinkMorph 自带特定 transformers
- Cosmos-Reason2 需要 NIM 容器

这种情况下建议参考 topobench 的做法：主 topogym venv 之外，每个自托管 backend 单开一个隔离 venv，主进程通过 HTTP 互通即可。

---

## 12. 一键校验脚本（建议放 `bin/verify_env.sh`）

```bash
#!/usr/bin/env bash
set -euo pipefail
.venv/bin/python - <<'EOF'
import sys
print("Python:", sys.version)

import torch
print("Torch:", torch.__version__, "CUDA available:", torch.cuda.is_available())

import genesis as gs
gs.init(backend=gs.cuda)
print("Genesis:", gs.__version__)

import rsl_rl
print("rsl-rl:", rsl_rl.__version__)

import gymnasium
print("Gymnasium:", gymnasium.__version__)

# Optional
try:
    import transformers; print("Transformers:", transformers.__version__)
except ImportError:
    print("Transformers: not installed (vla extra)")

try:
    import openai, anthropic, google.genai  # noqa: F401
    print("VLM SDKs: OK")
except ImportError as e:
    print("VLM SDKs: partial -", e)

print("\n[OK] Env baseline OK")
EOF
```

---

## 13. 待定 / 等真上手再决定

- **CUDA 版本最终锁定**：等 MVP 第一台机器的 driver 确定后再敲 `cu121` / `cu124` / `cu126`。
- **是否启用 LuisaCompute 光追**：MVP 不开（默认光栅渲染够用）；要做漂亮 demo 视频再加。
- **是否上 cuRobo**：先用 Genesis 自带 IK，瓶颈出现再换。
- **离线数据格式 first-class**：MVP 默认 HDF5；后续若上 LeRobot 生态再切。
- **多 GPU**：依赖 RLinf 或 `torch.distributed`，先单 GPU 跑通。

---

## 14. 引用

- [Genesis Installation docs](https://genesis-world.readthedocs.io/en/latest/user_guide/overview/installation.html)
- [genesis-world on PyPI](https://pypi.org/project/genesis-world/)
- [rsl-rl-lib repo (ETH Robotic Systems Lab)](https://github.com/leggedrobotics/rsl_rl)
- [PyTorch installation matrix](https://pytorch.org/get-started/locally/)
- [HuggingFace OpenVLA](https://huggingface.co/openvla)
