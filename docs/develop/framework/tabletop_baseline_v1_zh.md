# TopoGym Tabletop V1 基线

`topogym_tabletop_v1` 当前版本为 `1.2`，是首套冻结的桌面操作预设。它统一桌子、Panda
安装面、仿真时基和固定相机，并使用任务坐标描述 Swap 布局。

如果只是想找“哪个配置项控制哪个尺寸/位置”，先看
`configs/GEOMETRY_PARAMETERS_zh.md`。如果想理解这些数值如何换算到 Genesis world，
看 `docs/develop/framework/genesis_world_coordinates_zh.md`。

## 坐标系

- Genesis 世界坐标：`+z` 向上，地面为 `z=0`。
- 桌面坐标：原点 `[0, 0, 0.9196429]`，局部 `z=0` 是桌面表面。
- 任务坐标：V1 与桌面坐标重合。
- Swap 中的 slot 和 primitive 高度均使用任务坐标，构建时统一转换到世界坐标。

## 冻结几何

- 紧凑桌面外接长方体（AABB，即和坐标轴对齐的完整占用范围）：
  - `x=[-0.7402168, 0.4688596]`
  - `y=[-0.6000, 0.6000]`
  - `z=[0.0, 0.9196429]`
- Panda 安装原点：`[-0.570, 0, 0.9196429]`
- 操作底板：`0.70 m x 0.80 m`

桌面的 `x` 深度和高度来自 RoboMME 固定的 ManiSkill
`TableSceneBuilder`；原始 `2.418 m` 长边缩短为 `1.200 m`。操作底板
在 `y` 方向占 `0.800 m`，因此两侧各有 `200 mm` 桌面余量。

RoboMME 原本把 Panda 放在 `x=-0.615`；但 Genesis 1.1.0 的
`link0.stl` 实际足迹为：

```text
x=[-0.154079, 0.071567]
y=[-0.094614, 0.094671]
```

若直接使用 `x=-0.615`，底座会超出桌后沿。因此 V1 把安装点前移
`45 mm`。最终底座世界范围为：

```text
x=[-0.724079, -0.498433]
y=[-0.094614, 0.094671]
```

距桌后沿约 `16.1 mm`，满足配置要求的 `10 mm` 最小裕量。

## 强制校验

`StandardTabletopSceneBuilder` 在创建 Genesis 场景前检查：

1. 桌面碰撞体顶面与桌面坐标原点一致。
2. Panda MJCF 安装面与桌面顶面一致。
3. Panda 的真实非对称底座足迹完全位于桌面内。
4. 操作底板完全位于桌面内并落在桌面顶面。
5. 当 preset 为 `topogym_tabletop_v1` 且 `locked=true` 时，桌子、安装位、
   仿真时基和 `base_camera` 参数不得被覆盖。
6. `robot_mount.mobility` 必须为 `fixed`，episode 内不能移动底座。

## 相机

- `base_camera`：给学习策略/模型看的固定相机，`256 x 256`，FOV `90 deg`。
- `oblique`：斜俯视 viewer/录像调试相机，主要给人看。
- `topdown`：正上方俯视布局诊断相机。

腕部相机需要相对 Genesis `hand` link 做外参标定，不在首次 Swap
几何验收范围内。

## Swap Viewer

```bash
python -m prototypes.swap_tabletop_baseline_demo \
  --viewer --keep-open --verbose
```

启动日志会输出桌面范围、底座实际足迹、四向净空、安装高度、home
qpos、末端位置和 Swap slot 的世界坐标。若底座越界或安装面悬空，场景
会在 `scene.build()` 前直接失败。

## OneStroke Viewer

OneStroke 是第二个接入共享 builder 的任务，用来检查更宽的桌面、左右供料
区、边缘 wall slot 和机械臂视觉比例：

```bash
python -m prototypes.onestroke_tabletop_baseline_demo \
  --viewer --keep-open --verbose
```

V1.2 的桌面长边为 `1.20 m`，相对 `0.80 m` 操作板在左右两侧各保留
`0.20 m`。OneStroke 网格与 supply tray 都使用任务坐标，不再依赖绝对
世界高度。

OneStroke 初始场景不会显示任何预置 wall。为防止 wall block 落入色块
之间的缝隙，所有合法 cell 边界下方都有等价的不可见碰撞承托面；
`edge_slots.targets` 只保存 oracle 的逻辑目标，不创建可见实体，也不会
通过物理结构泄露答案。
