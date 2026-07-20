# MDP 状态与终态判定草案

本文记录当前三个正式 demo 往 MDP 化推进时的状态、奖励和终态约定。核心原则是：终态只看任务本身的拓扑/排列状态，不看机械臂姿态。

## Swap

状态先用离散 slot assignment 表示：

| 字段 | 含义 |
| --- | --- |
| `assignment` | 每个方块当前属于哪个 slot；如果离所有 slot 都太远，则记为 `None`。 |
| `empty_slots` | 当前没有方块占据的 slot。 |
| `invalid_blocks` | 不在任何合法 slot 附近的方块。 |
| `duplicate_slots` | 多个方块被判到同一个 slot 的异常情况。 |
| `target_assignment` | 目标排列。当前 smoke task 是红块从 source slot 进入 empty target slot，其他块保持不变。 |

终态：

`terminal=True` 当且仅当状态有效，并且所有方块的 slot assignment 等于 `target_assignment`。

当前临时 reward：

`reward = 10` 成功奖励，未成功时按错位方块、离格方块、重复占位扣分。这个 reward 只服务于可视化和早期调试，之后可以替换成更细的拓扑距离。

当前代码中的 Swap 还是 smoke 版初始化：

| 项 | 当前做法 |
| --- | --- |
| slot 数量 | 固定 5 个 slot。 |
| block 数量 | 固定 4 个 block。 |
| 初始状态 | 从 config 读取 `blocks.*.initial_slot`，当前是 `0, 1, 2, 4`，所以 slot 3 为空。 |
| 目标状态 | 当前目标是把 `oracle.block_to_move` 放到 `oracle.target_slot`，其他 block 保持初始 slot 不变。 |
| 终态判断 | 每步把连续坐标离散化成 slot assignment，再判断是否等于目标状态。 |

正式训练版建议改成随机初始化：

| 项 | 建议做法 |
| --- | --- |
| canonical target | 固定一个目标排列，例如从左到右 `[A, B, C, D, empty]`。 |
| reset | 每个 episode 随机打乱 4 个 block 和 1 个 empty slot，作为初始 puzzle state。 |
| block label | 每个 block 保留稳定身份，例如颜色 + 字母 label。 |
| terminal | 当前 assignment 完全等于 canonical target 时终止。 |
| step timing | 低层控制可用固定 `steps_per_action`；高层动作可定义为一次“选择 block 并移动到 empty”的 macro step。 |

## OneStroke

状态用“cell 颜色 + 已经放置的 wall edge 集合”表示：

| 字段 | 含义 |
| --- | --- |
| `cell_labels` | 3x3 cell 的标签；当前约定为 `A / B / gray`。 |
| `placed_edges` | 哪些 cell-edge gap 已经有 wall block。 |
| `unused_walls` | 还在 supply tray 上、尚未使用的 wall block。 |
| `invalid_walls` | 不在任何合法 edge slot 上的 wall block。 |
| `duplicate_edges` | 多个 wall block 被判到同一条 edge 的异常情况。 |

当前已实现的终态：

`terminal=True` 当且仅当状态有效，并且在“没有 wall 阻断的 cell 邻接图”中，不存在任何从 A cell 到 B cell 的连通路径。

这意味着 OneStroke 的目标不是固定某一组 `target_edges`，而是一类合法分割：只要墙把两个颜色区完全分开，就算成功。

当前代码中的 OneStroke 仍是 smoke 版初始化：

| 项 | 当前做法 |
| --- | --- |
| grid | 固定 3x3。 |
| cell labels | 从 config 读取固定 `A / B / gray` 标签。 |
| wall blocks | 固定数量生成在 supply tray。 |
| step/demo | 当前 demo 只放置一块 wall block；完整 MDP 的高层 action 尚未落地。 |

正式训练版建议：

| 项 | 建议做法 |
| --- | --- |
| reset | 随机采样两个非空颜色区 `A/B`，剩余格子为 `gray`。 |
| action | 高层动作选一条未放墙的相邻 cell edge。 |
| supply | wall block 用完后可 refill；逻辑层只需要记录已放 edge。 |
| terminal | A/B 在 cell 邻接图中被 wall 完全分开。 |

## Untangle

建议状态分两层：

| 层级 | 含义 |
| --- | --- |
| endpoint state | 每条 rope 的两个端点分别固定在哪个 hole。 |
| topology state | rope 之间的 over/under crossing 或缠绕关系。 |

待确认终态：

先可以只用 endpoint 是否到目标 hole 作为 smoke terminal；真正任务应进一步加入 rope crossing/untangle 的拓扑判定。

## HUD

录制视频会在左上角显示：

| 字段 | 含义 |
| --- | --- |
| `task` | 当前 demo/task 名称。 |
| `reward` | 当前临时任务 reward。 |
| `terminal` | 当前状态是否已经满足终态。 |
| 额外字段 | Swap 显示 empty slot，OneStroke 显示 target edge，Untangle 显示 endpoint 到目标距离。 |
