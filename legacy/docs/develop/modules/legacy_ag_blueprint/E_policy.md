# 模块 E — Policy（策略）

> 接收 D 拼好的 obs，输出符合 C 声明的 ActionSpace 的 action。**统一插槽**：所有 policy 类型——VLA / RL 网络 / VLM / 脚本——都实现同一个接口。
>
> E 的存在不是为了"自己实现 OpenVLA"，而是为了**让 OpenVLA 这种外部模型能被插进来用**，同时让别的算法/模型也能等价插入。

---

## 1. 输入

**构造期**（按子类不同）
- **OpenVLAPolicy**：HF checkpoint 路径 / 模型 ID
- **TorchPolicy**：`nn.Module` 实例（或定义 + 权重路径）
- **VLMPolicy**：API endpoint + API key + 提示模板
- **ScriptedPolicy / OraclePolicy**：规则函数 / 搜索算法配置
- **公共输入**：D 暴露的 **ObservationShape** + C 暴露的 **ActionSpace** —— 用来知道 I/O 形状

**每步**
- `obs[B]`：D 产出的 dict
- 可选 info（含 `topology_state`，OraclePolicy / ScriptedPolicy 会用）

**Episode 边界**
- reset 信号（清空内部缓存：RNN hidden、action chunk buffer、对话历史）

---

## 2. 输出

**构造期**
- 一个可调用的 policy 对象（暴露 `act / reset / save / load`）

**每步**
- `action[B, action_dim]`：满足 C 声明的 ActionSpace
- **可选**（RL 训练需要）：`log_prob[B]`、`value[B]`、`entropy[B]`
- **可选**（debug）：内部决策痕迹（VLM 的原始 JSON 响应、scripted 选了哪条规则…）

**Episode 边界**：无（内部清状态即可）

---

## 3. 与其他模块的连接

- **被谁调**：F 在每步调 `act(obs)`；G1 在训练时额外读 `log_prob/value`
- **它读谁**：D（每步 obs）+ B 的 topology_state（仅 oracle / scripted 子类）
- **构造期对齐**：必须知道 D 的 ObservationShape 和 C 的 ActionSpace（接口契约的核心）
- **训练时**：G1 通过 rsl-rl 反向修改 E 内的网络权重（仅 TorchPolicy 子类）
- **不直接和 A / Genesis 打交道**：E 只看张量，不知道仿真在哪

---

## 4. 内部逻辑概述

E 是**多子类**，每个子类内部逻辑差别很大；这里给每类的精简骨架。

### 4.1 RandomPolicy（baseline / smoke test）
- `act(obs) → ActionSpace.sample()`

### 4.2 ScriptedPolicy（人写规则）
- 每个 task 配一份 `rule_fn(obs, info, topology_state) → action`
- 用作 sanity check + 数据生成 baseline

### 4.3 OraclePolicy（求最优）
- 用搜索 / 规划算法（BFS / A* / SAT solver）基于完整符号状态找最优下一步
- 主要用途：G2 离线数据生成的"教师"

### 4.4 TorchPolicy（被 RL/IL 训出来的网络）
- 内含 `nn.Module`：图像编码器（CNN/ViT）+ proprio 编码器（MLP）+ 融合头 + action 头（Gaussian / Categorical / Diffusion …）
- `act(obs)`：preprocess → forward → distribution → sample（rollout）或 mode（eval）
- 同时返回 log_prob / value（PPO 要的辅助输出）
- 支持 train/eval mode 切换

### 4.5 OpenVLAPolicy（包预训练 VLA 模型）
- 构造期：`AutoModelForVision2Seq.from_pretrained(...)` 加载 HF 权重
- 每步：
  1. 从 obs 里挑出指定相机的 RGB（按 ObservationSpec 配的字段名）
  2. resize 到 224×224 + 归一化
  3. 拼提示词（任务语言描述，task-specific）
  4. `model.predict_action(image, prompt)` → 归一化的 7-D action
  5. 反归一化到 C 的 ActionSpace 实际范围
  6. （可选）action chunking：缓存 K 步动作，下 K-1 步直接出 cache

### 4.6 VLMPolicy（GPT-4V / Claude / Gemini）
- 构造期：初始化 HTTP client + 系统提示
- 每步：
  1. base64 编码 obs 里的相机图
  2. 拼 user message（图 + 任务描述）
  3. HTTP 调远端
  4. 解析返回的 JSON / 结构化输出
  5. 转成 ActionSpace 形式（如果 ActionSpace 是 primitive dict，正好对得上）
- 失败重试 + 限流 + key pool 在这一层实现

### 4.7 HierarchicalPolicy（planner + executor）
- planner（VLM / 大模型）每 K 步出一个 subgoal
- executor（小网络 / 脚本）执行 subgoal 到完成
- E 内部把两层连起来，对外仍是 `act(obs) → action`

**关键纪律**
- 所有子类对外接口完全一致：`act / reset / save / load`
- E 不知道自己在 train / data / eval 哪条 path（path 由 G1/G2/G3 决定）
- 子类内部的特殊状态（RNN hidden、action chunk、对话历史）只通过 reset 清；F 不感知

**外部依赖**
- 因子类而异：HuggingFace transformers（OpenVLA）/ PyTorch（TorchPolicy）/ OpenAI/Anthropic SDK（VLMPolicy）/ 无（Scripted）
