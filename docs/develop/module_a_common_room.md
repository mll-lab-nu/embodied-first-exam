# Module A Common Room Bootstrap

这一步只做 **A — World** 的最薄公共场景，不碰 task logic、reward、policy、runtime。

## 这次落下来的东西

- `topogym/world/common_room.py`
  - `init_genesis_once(...)`
  - `CommonRoomSpec`
  - `build_common_room(...)`
- `topogym/examples/common_room_demo.py`
  - 用 TopoGym 这一层构建公共试验场地并读两路相机
- `prototypes/hello_genesis_room.py`
  - 直接贴官方 Genesis 用法的 8 行原型

## 当前公共场景内容

- 地面 `Plane`
- 一张浅灰 lab bench 风格桌子
- 一块 40cm x 40cm 的操作区薄板
- 一台 Franka Panda（先用 Genesis 内置 MJCF 资产）
- 4 个彩色 cube
- 两个静态相机
  - `oblique`
  - `topdown`

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
python prototypes/hello_genesis_room.py
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
