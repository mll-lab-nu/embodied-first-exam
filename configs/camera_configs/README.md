# 相机视角预设

相机配置的统一消费入口是 `cfg.env.cameras`。本目录把可复用视角从环境几何和
demo 中拆出，Hydra 将所选预设合并到 `env`。

| 位置 | 职责 |
| --- | --- |
| [`topogym/world/tabletop.py`](../../topogym/world/tabletop.py) | 创建固定相机；按 `attach.entity/link` 绑定腕部相机 |
| [`topogym/world/presentation.py`](../../topogym/world/presentation.py) | 接入实验室、材质和 Nyx 相机后端 |
| [`topogym/world/nyx.py`](../../topogym/world/nyx.py) | 将相同相机配置转换为 Nyx sensor，并提供 `render()` 适配 |
| [`topogym/utils/recording.py`](../../topogym/utils/recording.py) | 选择录像相机、更新动态相机位姿、录制 |

## 双臂预设

| 配置 | 包含视角 | 默认使用处 |
| --- | --- | --- |
| [`aloha_observation.yaml`](aloha_observation.yaml) | 高位、低位、左腕、右腕四路观测 | `world_tabletop_aloha_v1` 双臂环境 |
| [`aloha_demo.yaml`](aloha_demo.yaml) | 继承四路观测，增加官方模型的操作员／协作者视角，以及 TopoGym 斜视、正视、房间全景 | `aloha_lab_preview` |

| TopoGym 相机名 | 上游模型名 | ALOHA 采集命名 | 用途 |
| --- | --- | --- | --- |
| `overhead` | `overhead_cam` | `cam_high` | 高位斜俯视，共同工作区 |
| `worms_eye` | `worms_eye_cam` | `cam_low` | 贴近桌面的低位视角，观察高度和遮挡 |
| `wrist` | `wrist_cam_left` | `cam_left_wrist` | 左腕，随左 `gripper_base` 移动 |
| `wrist_right` | `wrist_cam_right` | `cam_right_wrist` | 右腕，随右 `gripper_base` 移动 |
| `teleoperator` | `teleoperator_pov` | — | 官方模型的操作员侧展示位 |
| `collaborator` | `collaborator_pov` | — | 官方模型的协作者侧展示位 |
| `oblique` / `front` / `room` | — | — | TopoGym 自有展示视角 |

上游固定 revision：`8161bba264d7fa7c99ca301e91e7fb44737676ad`。
外部观测相机来自 [scene.xml](https://github.com/google-deepmind/mujoco_menagerie/blob/8161bba264d7fa7c99ca301e91e7fb44737676ad/aloha/scene.xml)，
腕部和两个展示相机来自 [aloha.xml](../../assets/robots/aloha/aloha.xml)。
这里的“官方模型展示位”指源模型具名相机，不表示所有官方视频都采用该固定角度。

静态相机的转换为：`p_world = p_source + [-0.1356786, 0, 0.9196429 - 0.02]`。
它与机器人桌面适配采用相同平移，因此相对机器人安装位置保持不变；朝向保持原值。
本预设针对锁定的 `world_tabletop_aloha_v1` 安装方式。改变安装位置或旋转时，
也要重新转换固定相机位姿，不能仅改机械臂底座。
低位相机光心因此位于桌面以上约 11.6 mm；它看向工作区略上方，不是远处的 `front`。
在当前 home 姿态中，抬起的夹爪大部分在低位画面上缘之外；该相机服务于贴近桌面的操作，
完整双臂初态应查看 `teleoperator` / `collaborator`。

四路观测使用 640×360，保持上游 1280×720 的 16:9 比例。
垂直视场角为 `2*atan(2.140/(2*1.930)) = 58.008335°`；
Genesis 的单一 FOV、方形像素模型不完整复现上游 D405 的标定内参。
两个模型展示相机保留 MJCF 默认 45° 垂直 FOV，以 960×540 输出。
`pos/lookat` 是世界坐标、米制；`fov` 是垂直角度；
腕部 `attach.offset_*` 是绑定连杆的局部坐标。

## 使用

```bash
# 默认：官方模型展示位、四路观测和实验室展示。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab

# 只预览四路观测（以及锁定环境要求保留的 base_camera）。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab \
  --camera-preset aloha_observation \
  --output runs/environment_bootstrap/aloha_observation
```

结果见 [双臂相机 demo](../../runs/environment_bootstrap/aloha_lab/index.html)。
页面按视角用途分组，配置和报告记录实际选用的预设、分辨率与相机世界变换。
交互 viewer 默认也采用操作员视角。

Hydra 已选择双臂环境时可使用 override：

```python
cfg = compose(config_name="aloha_lab_preview", overrides=[
    "camera_configs@env=aloha_observation",
    "env.cameras.overhead.res=[1280,720]",
])
```

`env.camera_rig.observation_cameras` 明确列出策略可用的四路相机；
`preview_cameras` 是 demo 实际建相机、出图的列表，不是数据集 schema。
双臂环境仍继承 `base_camera/topdown/front/oblique` 等公共键，加载预设会合并配置，
不会自动删除其他视角。任务可以在 `builder.create()` 前按观测列表裁剪，
但当前锁定预设要求保留 `base_camera`。保留 `wrist` 作为左腕键，避免破坏已有调用。
单臂环境仍读取原 `env_configs/world_tabletop_v1.yaml` 的相机配置。

运行配置与姿态回归检查：

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_camera_presets tests.check_configs_compose
```
