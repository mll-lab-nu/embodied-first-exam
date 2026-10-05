# Below-easy 难度：very_easy / easier

刺球出笼（`hedgehog_in_cage`）、马蹄环（`horseshoe_ring`）、长孔立柱解环（`slotted_post_ring`）三个任务，在 easy / medium / hard 之下各加了两档。切换方式和现有三档一样，只换 `variation_id`；对外只有难度不同。

> 2026-10-05 合并说明：Horseshoe 当前 easy 已采用 `ring_clearance_candidate_v3` 扩环版本。截面检查在 90 个采样相位中有 53 个通过（38°–142°，间隔 2°）；交接图解中旧 easy “零相位可通过”的结论不适用于当前版本。very_easy / easier 的既有几何设计检查保留，但名称不代表已验证它们比当前 easy 更容易，难度排序仍待机器人评测。

## 用法

```python
import topogym

env = topogym.make("hedgehog_in_cage", variation_id="very_easy")   # very_easy / easier / easy / medium / hard
env.reset()
```

- 五档名字：`very_easy`、`easier`、`easy`、`medium`、`hard`；也可以写全名，如 `hedgehog_in_cage_very_easy`。
- `variation_id="seeded"` 的随机抽样仍只抽 easy / medium / hard。
- 任务目标和评分与 easy 相同：把目标物整体放进绿色虚线目标区。

## 三个任务的两档

| 任务 | very_easy | easier | 难度旋钮 |
| --- | --- | --- | --- |
| 刺球 | 夹住朝机器人的那根刺，直接平移拉出笼 | 先绕所夹的刺转一下（约 80°），再拉出 | 三个等宽窗的宽度：118 / 108 mm |
| 马蹄环 | 提起马蹄，环沿链直接滑过另一只马蹄 | 先绕链转环，让长轴横跨马蹄，再沿链拉出 | 环孔：144 mm 圆 / 146 × 120 mm 椭圆 |
| 长孔立柱 | 绳从环下方穿过，环沿立柱直接提起越过柱顶 | 另一侧带珠 2 的绳圈搭在环上，先把绳圈穿下去再提环 | 绳的走向：`under_ring` / `loop_over_ring` |

部件都沿用各自的 easy；长孔立柱的绳加长（0.92 / 1.24 m），刺球的笼子加宽到内径 150 mm，使三根笼条均匀分布。设计过程、验证数据和图片见交接说明 [below_easy_variants_zh.html](below_easy_variants_zh.html)，以及各任务文档里的 “below-easy 设定” 一节：[刺球](../develop/tasks/hedgehog_in_cage_zh.md)、[马蹄环](../develop/tasks/horseshoe_ring_zh.md)、[长孔立柱](../develop/tasks/slotted_post_ring_zh.md)。

## 代码结构

```text
topogym/tasks/<任务>/
  common.py                 # 所有档共用：场景声明、评分、目标区
  <任务>_easy.py             # 现有 easy
  below_easy.py             # 继承 easy；加一个难度旋钮，覆盖一个几何钩子
  <任务>_very_easy.py        # 一行：旋钮取值
  <任务>_easier.py           # 一行：旋钮取值
topogym/config/variation_records.py         # 每档一条登记，pool='below_easy'，别名 very_easy / easier
topogym/planning/<任务>/below_easy_witness.py  # 物体层面检查 check_variant + 物理落稳 settle_check
ci_checks/test-<任务>-below-easy.py           # 登记与设计意图测试，不需要 GPU
```

新加一档：在 `below_easy.py` 的基类下写一个子类，给出旋钮取值，再在 `variation_records.py` 登记一条。

## 检查与测试

在仓库根目录、装好 TopoGym 的环境里运行：

```bash
python ci_checks/test-hedgehog-below-easy.py     # 约 40 s
python ci_checks/test-horseshoe-below-easy.py    # 约 2 s
python ci_checks/test-slotted-below-easy.py      # 约 5 s

# 单档报告（写到 --output/below_easy_check.json）；--settle-seconds 再做一次物理落稳
python -m topogym.planning.hedgehog_in_cage.below_easy_witness --variant very_easy --output runs/below_easy/hedgehog_very_easy --settle-seconds 3
python -m topogym.planning.horseshoe_ring.below_easy_witness   --variant easier    --output runs/below_easy/horseshoe_easier   --settle-seconds 3
python -m topogym.planning.slotted_post_ring.below_easy_witness --variant easier   --output runs/below_easy/slotted_easier
```

刺球和马蹄环的落稳在 CPU 上运行。长孔立柱是 FEM 绳，落稳需要 GPU 和 IPC 后端，在 TopoGym 镜像里运行。

## 其他文件

- [两档计划](two_levels_below_easy_plan_20261001_zh.md)：任务来源。
- [design_viewer/](../../design_viewer/README.md)：在浏览器里用鼠标拖动零件、理解谜题的 3D 查看器，新档会自动出现在场景列表里。它用 MuJoCo 近似，不是仿真证据。
- Harbor 任务包尚未生成。生成方法与现有三档相同：`scripts/topogym_mk_task.py <任务> --variation very_easy --scene-seed 0`，需要 GPU 和包含新代码的镜像。
