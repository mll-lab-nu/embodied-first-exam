# Module A Common Room Bootstrap

这一步只做 **A — World** 的最薄公共场景，不碰 task logic、reward、policy、runtime。

## 这次落下来的东西

- `topogym/world/common_room.py`
  - `init_genesis_once(...)`
  - `CommonRoomSpec`
  - `build_common_room(...)`
- `topogym/examples/common_room_demo.py`
  - 用 TopoGym 这一层构建公共试验场地并读两路相机
- `cli_commands.txt`
  - 当前保留的三个正式 demo 入口

## 当前公共场景内容

- 地面 `Plane`
- 一张 `1.30m x 1.00m` 的浅灰 lab bench 风格桌子
- 一块 `0.70m x 0.80m` 的操作区薄板
- 一台 Franka Panda（先用 Genesis 内置 MJCF 资产）
- 4 个彩色 cube
- 两个静态相机
  - `oblique`
  - `topdown`

Franka 的 MJCF 安装面位于 `z=0.75m`，与桌面顶面齐平。任务棋盘保持在桌面
上方，不再通过抬高机器人来匹配棋盘高度，因此底座视觉上和碰撞上都由桌面承托。

## 这里严格依赖的官方 Genesis 接口

只用了这些官方文档里明确展示过的 API：

- `gs.init(...)`
- `gs.Scene(...)`
- `scene.add_entity(...)`
- `scene.add_sensor(gs.sensors.*CameraOptions(...))`
- `scene.build(n_envs=...)`
- `scene.step()`
- `camera.read(...)`

官方文档：

- Hello Genesis
  - <https://genesis-world.readthedocs.io/zh-cn/latest/user_guide/getting_started/hello_genesis.html>
- Parallel Simulation
  - <https://genesis-world.readthedocs.io/zh-cn/latest/user_guide/getting_started/parallel_simulation.html>
- Camera Sensors
  - <https://genesis-world.readthedocs.io/zh-cn/latest/user_guide/getting_started/camera_sensors.html>

## 运行方式

先启用环境：

```bash
source /projects/bfuo/jlyu3/topogym/.venv/bin/activate
cd /projects/bfuo/jlyu3/topogym
```

直接看最小原型：

```bash
cat cli_commands.txt
```

跑 TopoGym 这一层的公共场景 demo：

```bash
python -m topogym.examples.common_room_demo
```

## 故意还没做的东西

- pegboard / rope / grid board
- task-specific reset
- slot indicator / target tray
- 机器人抓取 primitive
- reward / success / oracle

这一步的目标只是把“共同房间”先固定下来，并确认 Genesis 这条底层路径能跑通。
