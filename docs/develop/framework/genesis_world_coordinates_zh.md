# Genesis 与任务坐标

世界坐标以米为单位：`+z` 向上，`+x` 从机器人朝任务前方，`+y` 朝机器人左侧。
相机画面中的左右不能替代世界坐标方向。`Box.pos` 表示中心，`Box.size` 表示完整尺寸。

当前公共配置入口：

- `configs/common_configs/manipulation_space_tabletop_v1.yaml`：任务坐标、机器人安装面与候选操作范围。
- `configs/env_configs/world_tabletop_v1.yaml` / `world_tabletop_fem_v1.yaml`：世界中的桌面、底座、相机与时基。
- `configs/<task>.yaml`：任务有需要时显式覆盖公共场景。

公共 task frame 原点为 `[0, 0, 0.9196429]`，`z=0` 是桌面高度。
Franka 安装面在 task frame 的 `[-0.570, 0, 0]`，换算到 world 为 `[-0.570, 0, 0.9196429]`。
原点只定义坐标转换，不保证任意任务的桌子几何中心都与它重合。

```text
world_pos = frames.task.origin + task_pos
bottom_z = center_z - size_z / 2
top_z = center_z + size_z / 2
center_z = support_surface_z + size_z / 2
```

例如：高度 20 mm 的 box 底面要落在 world z=0.9196429 的桌面，中心 z 应为 0.9296429。
当前公共底板/棋盘默认关闭，不能再套用旧版“棋盘顶面高于桌面 9 mm”的假设。

任务配置字段不一定全是 task frame；先检查其场景 builder 如何消费。
开锁的 `LockGeometry` 与刺猬场景有自身的几何约定，调参前以对应配置和实际实例 `config.yaml` 为准。

共享 preset 被锁定时，builder 会校验桌子、底座与固定相机等参数。
需要任务专用场景时应显式声明配置，而不是误改公共冻结值。
物体只隐藏视觉不会关闭碰撞；纯背景的碰撞与柔体耦合由共享 presentation 层禁用。

[旧版坐标教程](../../../legacy/docs/develop/framework/genesis_world_coordinates_zh.md) 中保留了 Swap、Maze、Cable 和 Untangle 的历史例子。
