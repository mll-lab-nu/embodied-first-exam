# Claw B0 / C0：冻结工程原型

`catalog.json` 保存两个固定原型的入口、物理步长、证据目录与文件 SHA-256。每族的 `assets/` 包含两个 OBJ、URDF 和同源碰撞盒体、质量惯量、抓点及相对路径；`plan.json` 是已执行的完整双臂关节计划，`settings.json` 保存对应世界摆放与 IK 种子。

| 原型 | 动作 | 全流程物理复验 |
| --- | --- | --- |
| B0 `helical_crown` | 同步旋转 100° / 上升 40 mm，再抬高侧退 | 0.5 / 0.25 ms 通过 |
| C0 `orthogonal_gate` | 第一轴翻转 90°、穿窗避让、第二轴转 90°、退出 | 0.25 / 0.125 ms 通过 |

两者都是从预抓取起点开始的辅助抓持执行，末段解除辅助、张爪、退臂并独立桌面静置；没有验证纯摩擦抓取。C0 第二窗口为机器人前臂扩大了开口，实际结构和行程以此处冻结资产为准，早期概念比例不是已验证参数域。

在仓库根目录执行：

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 .venv-gs121-nyx/bin/python \
  -m topogym.tasks.interlocked_claws.family_robot \
  --execute assets/tasks/interlocked_claws/authored_compound_v1/helical_crown/plan.json \
  --dt .0005 --output runs/environment-solvability/interlocked_claws/NEW_B0_RUN
```

C0 将 family 路径换成 `orthogonal_gate`，步长设为 `.00025`。半步长复验分别使用 `.00025` / `.000125`。输出目录必须不存在。执行器检查当前模型与冻结几何、质量惯量、抓点是否一致，拒绝新模型重用旧 IK。

完整报告、五路 MP4 直链和生成边界见[物理验证说明](../../../../docs/develop/tasks/interlocked_claws_authored_physics_zh.md)。证据副本保存于 `runs/demo_metadata/interlocked_claws/2026-09-19_<family>_physical_v1/`，包括可独立加载的场景、机器人网格、状态、台架对照及双步长报告。

这个目录不是新的随机生成器版本。旧 `claw_seed_v1` 清单和拒绝行为未修改；新原型尚未接入其 API。任意尺寸、位姿或几何扰动都需重新求解验收，数据集资格保持关闭。本轮没有生成数据集或 H5。原版 A0 资产和接触资格限制也没有被这些新测试覆盖。
