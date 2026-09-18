# 模块 C — Embodiment & 动作接口

> 把机器人加到场景里，定义"一个动作长什么样"，并把上游 policy 的输出翻译成 Genesis 听得懂的关节命令。
>
> 这是**最关键的适配层**：不同 policy（PPO / OpenVLA / VLM）输出的动作形式完全不同，C 把它们统一规约到物理可执行的关节命令。

---

## 1. 输入

**构造期**
- **机器人 AssetRef**：URDF / MJCF 路径
- **动作模式选择**：joint / EE-pose / primitive 三选一（或更细分）
- **ControllerConfig**：PD 增益、阻尼、力矩限位、积分时间
- **HomePose**：机器人初始关节角

**每步**
- `action[B, action_dim]`：上游 E 输出的、**符合 ActionSpace 声明的**张量

**Episode 边界**
- reset 信号（不带新参数；C 内部只把机器人摆回 home）

---

## 2. 输出

**构造期**
- **ActionSpace 声明**：告诉上游"你必须输出形如 \[B, k\] 的张量，含义为 …"。例如：
  - joint mode → `Box([-1, 1]^7)`，归一化关节角增量
  - EE-pose mode → `Box([-1, 1]^7)`，6D 末端位姿增量 + 夹爪 open/close
  - primitive mode → `Dict({"primitive_id": Discrete(K), "params": Box(...)})`
- 把机器人加进 Scene（通过 A 的 `add_entity`）

**每步**
- 直接调 Genesis 的关节控制 API（不经过其它模块返回值）
- `action_ok[B]`：哪些 env 的动作合法地落地了（IK 成功、未超工作空间）—— 返回给 F 进 info

**Episode 边界**
- 机器人回 home（通过 Genesis 的 set_qpos）

---

## 3. 与其他模块的连接

- **谁读它的 ActionSpace 声明**：E 在构造期需要知道要输出什么形状
- **谁喂它 action**：E（通过 F 转发）
- **它怎么读 Scene**：通过 A 的 Entity Manifest 拿 `"robot"` 句柄
- **它写谁**：Genesis 关节控制 API（set_dofs_position / control 等）
- **不直接和 B/D 通信**：成功判定、观测拼装与它无关

---

## 4. 内部逻辑概述

**构造期**
1. 通过 A 把机器人 URDF add 进 scene
2. 配置 joint 控制器：PD gains、damping、力矩 limits（通过 `set_dofs_kp / set_dofs_kv` 等 Genesis API）
3. 如果动作模式是 EE-pose 或 primitive：初始化 IK 求解器（Genesis 自带 IK，或外挂 cuRobo / PyRoboKin）
4. 把 HomePose 缓存起来（reset 用）
5. 暴露 ActionSpace（按所选模式生成）

**每步（按动作模式分支）**

- **Joint mode**：
  1. 反归一化 action 到关节角/力矩
  2. 直接 `set_dofs_position_target` 或 `control_dofs_torque`
  3. `action_ok = (action 在限位内)`

- **EE-pose mode**：
  1. 反归一化 action → 6D 增量 + 夹爪开合
  2. FK 算当前 EE 位姿
  3. 合成目标位姿 = 当前 + 增量
  4. IK 求关节角目标
  5. `set_dofs_position_target` + 夹爪命令
  6. `action_ok = IK 成功 ∧ 关节限位 ∧ 工作空间`

- **Primitive mode（pick-place 等）**：
  1. 解析 action `{primitive_id, params}`
  2. 启动**子循环**（C 内部多个物理 step）：
     - 例如 pick-place：开爪 → 移到 pre-grasp → 下移 → 闭爪 → 抬起 → 移到 pre-place → 下放 → 开爪 → 抬起
     - 每个子步给 Genesis 关节命令，等若干 substep 物理推进
  3. 子循环结束才返回 F；**上层 F.step 看起来只发了一个动作**

**Reset 时**
- 通过 A 的 manifest 拿 robot 句柄，`set_qpos(home_pose)`；开爪

**关键纪律**
- 三种动作模式都要支持，但**默认实现先做 EE-pose mode**（与大部分 VLA / 模仿学习数据对齐）
- 高层 primitive 的"内 loop 步数"必须对 F 透明：F.step 内 Genesis 物理步数可以是 1 或 N，对外只有"一次决策"
- 失败的 IK / 越限动作**不要崩溃**：返回 `action_ok=False`，物理上保持原状或最近合法姿势

**外部依赖**
- Genesis 的关节控制 + Entity API
- 可选：IK 库（cuRobo / PyRoboKin / Genesis 自带）
