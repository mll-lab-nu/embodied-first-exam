# 模块 D — Observation（观测打包）

> policy 每一步**能看到什么**——RGB / 深度 / 本体感受 / 物体姿态 / 符号拓扑——全部在这里拼出来。
>
> D 不知道下游 policy 怎么用这些数据，只按 ObservationSpec 拼。

---

## 1. 输入

**构造期**
- **ObservationSpec**：声明要哪些字段，例如：
  - `cameras`: `[{name: "topdown", res: (224,224), fov: 60, pose: ...}, {name: "wrist", ...}]`
  - `proprio`: `["joints", "ee_pose", "gripper"]`
  - `objects`: `["rope_vertices", "tile_orientations"]`（任务相关）
  - `topology_state`: `true/false`（要不要把 B 算出来的符号 state 也塞进 obs）

**每步**
- Scene 句柄（A 提供）+ Entity Manifest（取相机和物体）
- B 缓存的本帧 `topology_state`（如果 ObservationSpec 要）

**Episode 边界**
- reset 信号（D 渲染初帧并打包初 obs）

---

## 2. 输出

**构造期**
- 把构造期需要的**相机注册请求**回传给 A（"我要这几个相机，请加进 scene"）
- **ObservationShape**：告诉上游 obs 的字典结构 + 每个字段形状（E 在构造期用这个 spec 自配输入头）

**每步**
- 一个 dict（按 spec 决定字段），例：
  ```
  {
    "rgb_topdown": [B, 224, 224, 3],   # uint8
    "rgb_wrist":   [B, 224, 224, 3],
    "joints":      [B, 7],             # float32
    "ee_pose":     [B, 7],             # xyz + quat
    "gripper":     [B, 1],
    "topo_state":  [B, ...]            # 任务相关 schema
  }
  ```

**Episode 边界**：同上格式的初帧 obs

---

## 3. 与其他模块的连接

- **谁读它**：E 每步消费 obs；F 把 obs 放进 TimeStep 转发给 G1/G2/G3
- **它读谁**：A（Scene 句柄 + 相机句柄 + 物体句柄）+ B（topology_state 缓存）
- **构造期回路**：A 在 build 之前需要知道有哪些相机 —— 由 D 在构造期把 CameraSpec 提前回传给 A
- **关键契约**：`ObservationShape` 必须和 E 的输入期望对齐（OpenVLA 要 224×224、PPO 网络要某个固定 dim）

---

## 4. 内部逻辑概述

**构造期**
1. 解析 ObservationSpec
2. 把相机 spec 回传给 A（A 在 add_entity 阶段把相机摆好）
3. 决定每步要读的 proprio / 物体字段
4. 预分配输出 buffer（按 n_envs × spec dim）
5. 暴露 ObservationShape 给 E

**每步**
1. **触发相机渲染**：对 ObservationSpec 里列的每个相机调 Genesis 的 render → 拿 RGB / depth / seg
2. **读 Scene 状态**：
   - 通过 A 的 manifest 拿 `"robot"` → 关节角 / 速度 / EE 位姿（FK）/ 夹爪开合
   - 拿 props → 世界坐标 / 朝向 / 顶点位置（DLO）
3. **复用 B 的 topology_state**（如果 spec 要）—— 不重复计算
4. **可选预处理**：resize / channel reorder / 归一化（这部分也可以推到 E 里做，按 task 偏好）
5. 拼成 dict 返回

**Reset 时**
- 同样的 pipeline 跑一遍，产出初帧 obs

**关键纪律**
- **lazy render**：ObservationSpec 没要的相机不渲染（渲染是开销大头）
- **不重复计算 topology_state**：从 B 缓存读取
- **数据类型一致**：RGB 用 `uint8` 节约内存，到 E 内部再 `float / 255.0`（VLA preprocessing 标准做法）

**外部依赖**
- Genesis（相机 render + 状态读取 API）
- 可选：torchvision transforms（若 D 内做 VLA-style preprocessing）
