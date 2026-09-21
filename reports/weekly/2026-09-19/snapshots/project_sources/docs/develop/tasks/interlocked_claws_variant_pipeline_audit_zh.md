# Claw 变体生成与 pipeline 审查（2026-09-19）

后续更新：已完成 [B0/C0 固定工程原型及物理 demo](interlocked_claws_authored_physics_zh.md)，另存为 `authored_compound_v1`。
以下审查记录针对冻结的 `claw_seed_v1`，其 B/C 拒绝规则未变；不能再把下文“未建模”理解为整个项目的最新状态。
新原型尚未接入 seed API，连续参数域及数据集资格也未因此开放。

结论：两级设计符合“固定结构 family + family 内参数随机化”的思路，但原实现不满足三族可运行生成器。
此前 `family_space.py` 是规划检查与展示工具；B0/C0 没有实体和配套 IK，不能据概念图认定三种动作已经肉眼可辨。
本轮补上了可复现的实例采样、真实 A0 资产构建、场景适配、恢复接口及拒绝规则。
**三族完整生成器尚未完成，当前没有可发布的数据集实例。**

| 用户要求 | 实际结果 |
| --- | --- |
| 三个固定 family 的 IK 有明显视觉差异 | 尚不满足：只有 A0 有真实模型、原关节轨迹和完整辅助抓持执行；B0/C0 未建模、未解 IK |
| 在 family 内做尺寸、位置、外观微调 | A0 的材质模式可实际加载；正比例尺寸、平移、yaw 模式可构建几何与配套目标位姿，但机器人 IK、支架与物理执行需重新验证 |
| 接入现有 seed 机制和后续 pipeline | 接口已实现并测试，复用具名 RNG 和 EpisodeSpec；未实现或未合格实例明确拒绝，不能当作合格数据返回 |

## 两种生成方式

`fixed`：seed 选择固定的 family 模板，再抽样材质。几何、功能结构、抓点和动作不随机重造。
材质分布在所有 family 间一致；色板、粗糙度和金属度实际写入网格与 Nyx 最终覆盖规则。

`similarity_candidate`：在已实现的 A0 上，对两个局部网格统一缩放，并对两件的完整期望运动施加同一空间变换。
候选范围为统一倍率 `[0.99, 1.01]`、共同 x/y 平移各 ±2 mm、yaw ±1°。
这只是一段可检查的初始候选域，不代表连续参数域已通过机器人或动力学验收。
此版没有独立扰动杆半径、非均匀缩放或任意逐帧 pose 噪声，以免无意封闭窄通道。

局部点与位姿一起满足：

```text
v' = s v
R'(t) = Q R(t)
p'(t) = c + Q s (p(t) - c) + delta
```

`c=(0,0,0.3)m` 在原参考坐标系；所有位移单位为米，yaw 参数单位为度。
这个共同正比例相似变换将理想件间间隙乘以 s，因此可继承绑定哈希的源连续件间路径证书。
缩放后的抓持局部平移也乘以 s，不能保留原抓持偏置。
该结论不覆盖新关节插值路径、机器人碰撞、固定支架、质量变化后的控制或物理接触。
运行器会明确拒绝把此类候选直接套进旧 A0 关节轨迹。

## API 与 seed 约定

任务卡 `configs/task_cards/interlocked_claws.yaml` 的 `variant_generation` 提供采样、构建和恢复入口，供 pipeline 发现。
`baseline_manifest(task_id, seed)` 仍只描述固定基线，不会因带有 seed 就自动随机化；应调用任务卡声明的采样入口。

- `sample(seed, family=None, parameter_mode='fixed', attempt=0)` 返回配置和标准 `EpisodeSpec`。返回的是提案，不是成功 episode。
- `generate(...)` 构建资产和核验记录。字段 `materialized` 只表示资产构建成功；与 `dataset_eligible` 分开。
- `load_instance(instance.json)` 使用冻结的配置恢复，检查完整规格、目录和源资产哈希，不根据 seed 重抽。
- `prepare_episode(instance.json)` 是实际场景构建前的入口。固定 A0 可以进入 `scene.build_scene`；相似变换候选和 B/C 明确拒绝。
- `prepare_episode(..., for_dataset=True)` 当前明确拒绝：A0 通用接触验收未通过，B/C 缺少实际结构与动作。没有隐式 recorder 或 H5 写入。

family 只由原 seed 的独立具名流选择一次；重试只改变族内参数，不能因拒绝而换成更容易的 family。
不依赖批次长度、调用顺序、文件路径或全局 numpy RNG。
默认仍按 A/B/C 三个声明槽位采样；抽到 B/C 会得到失败记录。
显式指定 `family='claw_weave'` 才是仅对 A0 做开发检查，不能用这种测试冒充三族生成成功率。

每份规格保存 generator/RNG 版本、固定目录与源资产哈希、seed、attempt、派生 seed、完整配置与实例哈希。
材质不同但机械结构相同的样本共享 `mechanical_sha256`。
同一个固定原型及其微调邻域共享 `split_group`，避免换色和近邻副本跨训练/验证集合。
目录或算法变化应发布新版本，不能用同一版本悄悄替换结构与动作。

## 可运行示例（仅实例与资产）

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.variants \
  --seed 7 --family claw_weave \
  --output runs/environment-solvability/interlocked_claws/NEW_FIXED_INSTANCE

.venv-gs121-nyx/bin/python -m topogym.tasks.interlocked_claws.variants \
  --seed 19 --family claw_weave --parameter-mode similarity_candidate \
  --output runs/environment-solvability/interlocked_claws/NEW_GEOMETRY_CANDIDATE
```

输出目录必须是新目录，不能位于 `demos/`。
包含 `instance.json`、配置、网格/URDF 或位姿目标、检查结果及哈希；不生成视频、数据集或 H5。
B/C 的构建命令会返回非零退出码并留下明确的失败记录。

```python
from topogym.tasks.interlocked_claws.variants import prepare_episode
from topogym.tasks.interlocked_claws.scene import build_scene

cfg = prepare_episode(".../attempt_00/instance.json")
# 由调用方初始化 Genesis；场景继续读取这一份冻结配置。
scene = build_scene(cfg, "runs/.../scene_assets")
```

## 本轮验证与仍缺少的工作

验证包括重复 seed、不同调用顺序、额外随机轴、已有 Hydra 上下文、并行线程、完整规格恢复与篡改检测、材质实际生效、相似变换与抓点/位姿联动、拒绝次数上限、不跨 family 回退，以及未合格实例的导出阻断。
真实小样构建覆盖两个 A0 材质实例、两个 A0 尺寸/位置候选和 B/C 的明确拒绝。
128 个 seed 的声明家族分布为 A=45、B=43、C=40；这只是采样统计，不是三族物理成功率。
审查证据位于 `runs/environment-solvability/interlocked_claws/seed_generator_audit_20260919_v3/`。
实际场景加载和 Nyx 材质覆盖检查通过；此项检查没有物理步进、没有渲染帧，不冒充新物理执行。
全项目范围另有两项检查因 `horseshoe_ring` 任务卡的 schema 校验失败；本轮未修改该任务卡或共享 catalog。

下一步必须完成 B0/C0 固定实体、抓点和配套双臂 IK，并以真实轨迹进行同镜头动作比较；随后对每族参数调整重新求 IK、检查实际路径与完整物理执行。
A0 独立接触对照失败也仍需修复。在这些检查通过前，不能打开三族数据集生成。
本轮解决了 seed 与场景接口问题，没有将上述缺项标为完成。

已有动作参照：[A0 近景完整 MP4](../../../demos/interlocked_claws/detail/2026-09-17_reference_full_v1_detail.mp4)，158.6 秒，含理想辅助抓持；本轮没有新增物理执行录像。
