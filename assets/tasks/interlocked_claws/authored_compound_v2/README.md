# Claw C0：紧凑等尺寸双窗修订

`orthogonal_gate_balanced_v2` 属于既有 C0 正交双窗 family，替代其当前展示基型；不是第四个动作 family。旧 `authored_compound_v1` 的 B0、较大且不对称的 C0 资产与录像完整保留，哈希未变。

两个窗口完全全等：外框各 250 × 190 mm，净开口各 220 × 160 mm，厚度 14 mm、边框宽 15 mm。整体橙色框架为 252 × 252 × 190 mm，最大尺寸接近原始 A0 的约 264 mm。两窗共用拐角，不再安装长握柄。镜头透视可能使近侧显得更大，但几何具有交换两窗的精确镜面对称。

保留先绕第一轴翻转 90°、穿窗避让、再绕正交第二轴转 90°、退出的动作。放置阶段先放蓝色件，34 秒解除左侧抓持、退手；再搬运框架，54 秒解除右侧抓持，最终两件独立落桌静置。接受计划总长 62 秒。

0.25 / 0.125 ms 两档完整机器人动力学及独立台架检查均通过；开始时已经抓住两件，使用可解除理想焊接辅助。没有验证纯摩擦抓取、自主寻找解法或实机执行。

`catalog.json` 固定模型、计划、设置与哈希。`settings.json` 中的 `settled_key_pose` 来自一次短程物理预测，仅用于松手后的规划碰撞检查；执行器不会把该位姿写回模拟器。该预测的独立证据与最终视频一起归档。

从仓库根目录复跑（输出使用不存在的新目录）：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.interlocked_claws.family_robot \
  --execute assets/tasks/interlocked_claws/authored_compound_v2/orthogonal_gate_balanced_v2/plan.json \
  --dt .00025 --output runs/environment-solvability/interlocked_claws/NEW_BALANCED_C0
```

新版本仍是固定原型；未接入旧 `claw_seed_v1` API，没有生成数据集或 H5，也没有宣称尺寸、位姿随机扰动已通过。后续生成器应选择本修订作为 C0 的结构模板，为每个几何实例重建抓点、IK、放置及顺序释放计划并逐实例验收。

[修订说明与五视角视频](../../../../docs/develop/tasks/interlocked_claws_balanced_gate_zh.md) · [独立证据归档](../../../../runs/demo_metadata/interlocked_claws/2026-09-19_orthogonal_gate_balanced_physical_v1/README.md)
