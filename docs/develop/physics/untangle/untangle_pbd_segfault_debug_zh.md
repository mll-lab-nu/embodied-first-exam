# Untangle PBD Segmentation Fault 调试记录

本文记录 Untangle demo 中 Genesis PBD elastic rope 出现 `Segmentation fault (core dumped)` 时的排查经验。核心结论是：这类崩溃通常不是 Python 层异常，而是 PBD 求解器在 `scene.step()` 时收到了几何或约束上过于极端的状态。

## 这次的关键修复

| 改动 | 作用 |
| --- | --- |
| manual demo 中关闭 `anchor_endpoints` | 避免 Genesis 固定端点粒子后，又被脚本手动移动同一批粒子。 |
| 默认不调用 `set_particles_vel` | 避免“固定端点粒子 + 手动写速度 + 下一次 PBD solve”的不稳定组合。 |
| 端点固定桩保留可视化，但默认关闭碰撞 | 避免 rigid pin 和 PBD rope 初始深度重叠。 |
| 拖动完成后 `commit()` 新端点位置 | 避免 hold 阶段把已移动端点重新钉回旧位置。 |
| terminal 判定加入 endpoint/pin overlap | 端点放到已有固定桩位置不再算成功。 |
| manual demo 可选冻结非移动 rope | 这是 `--motion-model kinematic` 的备用展示策略，不作为物理优先方案。 |
| 移动中的 rope 可选整条 rope kinematic pose | 这是 `--motion-model kinematic` 的备用展示策略；物理优先时关闭。 |
| 最新修复：按 rope 局部坐标旋转 tube 截面 | 目标从 `[0,1]` 改到 `[0,2]` 后，绿绳会接近 90 度转向；旧实现只移动轴线、不旋转截面，可能把 3D tube 压成退化体，PBD 下一步直接 segfault。 |

最新一次真正解决问题的是最后一条：`_set_kinematic_rope_pose()` 现在先建立 rope 的局部轴线坐标系，再把每个粒子的轴向位置和截面偏移映射到新轴线。这样 tube 的圆截面会跟着 rope 方向一起旋转，不会在大角度端点移动时被压扁。

## 我们已经排除过的误判

| 现象 | 结论 |
| --- | --- |
| `libEGL warning: failed to open /dev/dri/... Permission denied` | 通常不是 segfault 根因；headless/offscreen 渲染仍可继续。 |
| TetGen 输出很多 `Delaunay / Writing nodes` | 这是 PBD elastic tube tetrahedralize 的正常日志。 |
| `quadrants ... cannot create weak reference to tuple` | 是缓存 warning，不是这次 native crash 的直接原因。 |
| 录制分辨率高 | 可能导致卡顿或内存压力，但这次手动无录制也能复现，所以不是主因。 |
| 磁盘空间不足 | 会影响写视频，但这次释放磁盘后仍复现。 |
| `drag_steps=1` | 单步大位移确实危险，但后来 `drag_steps=320/380` 仍复现，说明根因不只是“瞬移”。 |

## 有效的定位方法

| 测试 | 用途 |
| --- | --- |
| `--settle-steps 0 --drag-steps 0 --hold-steps 0` | 只 build 场景，不调用 `scene.step()`；如果通过，说明 mesh 生成和场景搭建基本没问题。 |
| `--settle-steps 1 --drag-steps 0 --hold-steps 0` | 验证静态 PBD rope 第一帧求解是否稳定。 |
| `--settle-steps 1 --drag-steps 1 --debug-print-drag-steps` | 精确判断是否在第一次拖拽后的 `scene.step()` 崩。 |
| `--debug-disable-anchor-endpoints` | 隔离 Genesis `fix_particles` 对端点约束的影响。 |
| `--debug-enable-set-particles-vel` | 只在诊断时打开；如果打开后崩，说明手动速度写入不可用。 |
| `--debug-strands rope_red` | 单独构建某条 rope，判断是不是 rope- rope 交互触发。 |
| `--viewer --viewer-lite` | 用低成本 viewer 观察崩溃前是否有穿模、过度拉伸、固定桩重叠。 |

排查时最有价值的是最后一行日志。例如 `before_scene_step` 后立刻崩，说明上一行脚本写入的粒子位置/约束状态触发了下一次 PBD solve 崩溃。

## PBD rope 容易崩的触发机制

| 触发模式 | 直观解释 | 处理方式 |
| --- | --- | --- |
| 固定粒子又被手动移动 | 一边把 rope 端点钉住，一边把同一端点拖走。 | manual demo 中不要同时使用 `fix_particles` 和手动 `set_particles_pos`。 |
| 手动写速度 | PBD 下一步会用这个速度预测位置，固定粒子和写入速度可能冲突。 | 默认关闭 `set_particles_vel`。 |
| rigid pin 和 PBD rope 初始重叠 | 固定桩和绳子在同一空间里互相挤压。 | 端点 pin 先作为可视化/抓取把手，collision 关闭。 |
| 单步移动太远 | rope 被一帧拉出很长距离，约束修复过猛。 | 增大 `drag_steps`，保持每步位移小。 |
| 路径贴着另一条 rope 拖 | rope-rope contact 和拓扑约束同时强烈变化。 | 增加 `endpoint_lift`，让上方 rope 跨过去。 |
| 目标端点和已有 pin 重叠 | 两个端点或固定桩占同一个 hole。 | topology state 中记录 `endpoint_overlaps`，有重叠不算 terminal。 |
| 管状 mesh 被错误变形 | 只移动轴线、不旋转截面，会把 tube 压成退化体。 | 用 rope 局部坐标变换整条 rope，保持截面形状。 |

## 当前 demo 的稳定策略

当前 Untangle demo 有两条路径：

| 路径 | 做法 |
| --- | --- |
| `--motion-model physics` | 只移动被抓住的 endpoint 粒子；其他端点被钉住；rope 中段、rope-rope 接触和形变交给 Genesis PBD 求解。 |
| `--motion-model kinematic` | 备用展示模式：冻结非移动 rope，并按端点位置重塑移动 rope，用于规避 PBD native crash 或制作拓扑动画。 |

物理优先时应使用 `physics`；`kinematic` 不是最终物理训练方案，只用于隔离问题或稳定展示。

## 当前 PBD rope 数值配置

这些值来自 `configs/task_configs/untangle.yaml`，我们显式设置了它们，不依赖 Genesis 默认值：

| 参数 | 当前值 | 含义 |
| --- | ---: | --- |
| `rope.model` | `pbd_elastic_tube` | 使用 Genesis `PBD.Elastic` 的 3D 体网格 rope。 |
| `rope.radius` | `0.004` | rope tube 半径，约 4mm。 |
| `rope.particle_size` | `0.004` | PBD 粒子尺度。 |
| `rope.mesh.segment_length` | `0.009` | 生成 tube mesh 的中心线采样间距。 |
| `rope.mesh.radial_segments` | `8` | 管状截面顶点数。 |
| `rope.mesh.maxvolume` | `2.5e-8` | tetrahedralize 时单个四面体最大体积。 |
| `pbd.max_stretch_solver_iterations` | `10` | 拉伸约束迭代次数，越高越不容易被拉长。 |
| `pbd.max_bending_solver_iterations` | `6` | 弯曲约束迭代次数，越高越抗弯。 |
| `pbd.max_volume_solver_iterations` | `6` | 体积约束迭代次数。 |
| `elastic.stretch_compliance` | `0.0006` | 拉伸柔顺度，越大越容易拉长。 |
| `elastic.bending_compliance` | `0.0015` | 弯曲柔顺度，越大越容易弯。 |
| `elastic.volume_compliance` | `0.00008` | 体积柔顺度。 |
| `elastic.stretch_relaxation` | `0.35` | 拉伸约束松弛。 |
| `elastic.bending_relaxation` | `0.2` | 弯曲约束松弛。 |
| `elastic.volume_relaxation` | `0.2` | 体积约束松弛。 |
| `elastic.static_friction / kinetic_friction` | `0.35 / 0.25` | 接触摩擦。 |

“固定长度但可形变”主要由 stretch constraint 控制：`stretch_compliance` 越小、stretch solver iterations 越高，长度越接近固定；`bending_compliance` 越大，绳子视觉上越软、更容易弯。

## 推荐命令

正式录制解开 crossing：

```bash
python -m prototypes.untangle_rope_drag_demo --mode manual --lite --settle-steps 10 --drag-steps 380 --endpoint-lift 0.08 --hold-steps 45 --record-video runs/demo_untangle_solve.mp4 --record-fps 60 --record-res 640 640 --record-aa --verbose
```

正式录制物理扰动/打结演示：

```bash
python -m prototypes.untangle_rope_drag_demo --mode manual --demo-goal disturb --disturb-preset wrap --motion-model physics --lite --settle-steps 10 --drag-steps 380 --endpoint-lift 0.014 --hold-steps 120 --record-video runs/demo_untangle_physics_wrap.mp4 --record-fps 60 --record-res 1280 1280 --record-aa --verbose
```

交互诊断：

```bash
python -m prototypes.untangle_rope_drag_demo --mode manual --viewer --viewer-lite --keep-open --settle-steps 10 --drag-steps 280 --endpoint-lift 0.05 --hold-steps 30 --verbose
```

注意：同一个参数在命令里重复出现时，`argparse` 会采用最后一次出现的值。例如同时写 `--endpoint-lift 0.05 ... --endpoint-lift 0.08`，实际值是 `0.08`。

`--demo-goal solve` 会选择上方 rope 的 endpoint 去消除 crossing；`--demo-goal disturb` 会故意选择下方 rope 的 endpoint，制造 knot/conflict，不要求任务完成。`--disturb-preset wrap` 当前固定选择下方 rope endpoint 并直线移动到 `[2, 0]`，用于测试直接拖拽是否形成可见缠绕；`--motion-model physics` 是物理优先路径；`--rope-slack` 只影响 `--motion-model kinematic` 的视觉松弛度。`--endpoint-lift` 太低时，端点会贴着 board/rope 摩擦移动，看起来像一边试探一边走；适当提高到 `0.014` 左右通常更顺，但过高会减少 rope-rope 接触。

## 后续如果继续做更真实物理

| 目标 | 建议顺序 |
| --- | --- |
| 真 rope-rope 接触 | 先做两条 rope 的无机器人、低速、短距离接触 smoke test。 |
| 真固定桩碰撞 | 让 pin 与 rope 初始位置留出真实间隙，再逐步打开 pin collision。 |
| 真机械臂抓 pin | 先让 rigid pin 稳定插拔孔，再把 rope endpoint attachment 接到 pin 上。 |
| RL/VLA 训练 | 高层 terminal/reward 仍用 topology state，底层物理逐步替换 demo 里的 kinematic assist。 |

经验原则：先让拓扑状态机和任务语义稳定，再逐层打开真实物理接触。PBD native crash 往往没有 Python traceback，所以每次只打开一个变量，并让日志打印到 `scene.step()` 前后，是最高效的排查方式。
