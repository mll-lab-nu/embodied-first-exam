# 公共双臂接入：ALOHA 2

这项能力属于共享 `topogym/robot` 和 `topogym/world`，不属于某一个任务。
单臂默认仍为 Panda + Robotiq；双臂使用独立的机器人控制配置和桌面预设。
参考是 [Qineng Wang 的演示说明](https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html)
中注明的 ALOHA 2，使用相同固定版本的开源模型，资产来源见
[资产 README](../../../assets/robots/aloha/README.md)。

## 运行与查看

仓库根目录执行：

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab
# 在静态图片之后额外执行 100 步保持位姿检查（1 s 仿真时间）。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab --check-steps 100
# 交互查看；Genesis 窗口为光栅显示，保存的图片仍使用 Nyx。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab --viewer
# 只查看四路观测（高位、低位、左腕、右腕），保留共享 base_camera。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.aloha_lab \
  --camera-preset aloha_observation --output runs/environment_bootstrap/aloha_observation
# 显式 CPU / 光栅路径：
.venv-gs121/bin/python -m demos.environment_bootstrap.aloha_lab --backend cpu --renderer rasterizer
```

默认产物：[demo 页面](../../../runs/environment_bootstrap/aloha_lab/index.html)、
[验证报告](../../../runs/environment_bootstrap/aloha_lab/report.json)、配置快照和十路 PNG。
图片为原始 home 姿态，在任何仿真步之前采集；可选保持检查不改变展示初态。
正视、斜视和房间相机全部位于封闭实验室内部。

## 共享接口

| 位置 | 职责 |
| --- | --- |
| `robot/assets.py` | 资产选择与原始 ALOHA 桌面适配缓存 |
| `robot/aloha.py` | 左右臂具名关节分组、home、位置伺服、夹爪、每臂 IK 和状态读取 |
| `robot/factory.py` | `initialize_robot_controller` 按配置初始化 Franka 或 ALOHA |
| `env_configs/world_tabletop_aloha_v1.yaml` | 双底座安装、占地；继承完整实验室和四路观测预设 |
| `camera_configs/aloha_observation.yaml` / `aloha_demo.yaml` | 可复用的四路观测、操作员／协作者展示位及实验室展示 |
| `robot_control_configs/aloha_position_ik.yaml` | 6+6 臂关节、夹爪、原始控制增益、限位和 home |
| `configs/aloha_lab_preview.yaml` | 可运行的双臂实验室组合 |

ALOHA 作为一个 Genesis articulation 注册为 `manifest.get("robot")`；
内部保留 `left/…`、`right/…` 原生名称。
`controller.left` 和 `controller.right` 通过具名关节查找本臂索引，
右臂不会错误地使用整个模型最前面的六个关节。
原生手指 equality 保留，每侧仅驱动第一个手指。

```python
from topogym.robot import initialize_robot_controller
from topogym.world import StandardTabletopSceneBuilder

# cfg 由 Hydra compose(config_name="aloha_lab_preview") 得到；先调用 gs.init。
builder = StandardTabletopSceneBuilder(cfg.env, cfg.robot_control)
base = builder.create()
# 任务可以在这里追加自身实体。
builder.finalize(base)
controller = initialize_robot_controller(
    scene=base.scene, manifest=base.manifest,
    robot_cfg=cfg.robot_control, settle_steps=0,
)
state = controller.state()  # {left: {...}, right: {...}}
# 两臂先各自提交目标，然后只推进一次共同场景。
controller.left.set_arm_qpos(cfg.robot_control.home.left[:6], steps=0)
controller.right.set_arm_qpos(cfg.robot_control.home.right[:6], steps=0)
controller.step(20)
```

`move_ee_to(pos, quat=..., steps=0)` 的位置是该臂 `gripper_link` 的世界坐标，
四元数顺序为 wxyz；`grasp_center_pos()` 对应原模型的夹持 site。
`set_gripper` 参数是手指在导轨上的米制位移（软件范围 0.002–0.037 m），
不能套用 Panda/Robotiq 的开口语义。

`wrist` 绑定左 `gripper_base`，`wrist_right` 绑定右 `gripper_base`；
使用上游 D405 的局部位姿和垂直视场角，输出分辨率为 640×360，保持原 16:9 比例。
高位 `overhead` 和低位 `worms_eye` 也已接入；`teleoperator` / `collaborator`
沿用官方模型的两个展示位。所有相机参数现集中在
[相机预设目录](../../../configs/camera_configs/README.md)，demo 按预设列出的相机出图。
`base_camera` 与公共桌面坐标保持原规范。
机器人配置和环境配置必须配对选择；不匹配时共享 builder 在建场景前报错。

## 验证范围与后续工作

```bash
.venv-gs121-nyx/bin/python -m unittest tests.check_aloha_shared
.venv-gs121-nyx/bin/python -m unittest discover -s tests -p 'check_*.py'
```

单元检查核对上游文件哈希、源模型的惯量/限位/增益、基座网格占地、
左右臂命令隔离、右臂 IK 索引和双臂同时 reset 后统一步进。
实际 demo 检查 16 DoF、两个安装面高度、home、所选预设的全部 RGB、双腕绑定、背景无碰撞；
可选保持检查记录实际漂移，阈值 0.15 rad 只用于发现短时发散，不是精度验收。

这次完成静态仿真接入与基础控制接口；未完成双臂避碰规划、协作抓取、
任务成功验收、实机通信或控制器标定。Genesis 会采用自己的碰撞近似与默认接触过滤，
不能将该结果视作 MuJoCo 原生动力学的复现。
现有任务中直接调用 Franka 初始化或单末端 primitive 的路径仍是单臂；
要执行双臂任务，需要明确分配左右臂及协作逻辑。
现有 `EpisodeDatasetWriter` 的单末端状态 schema 未扩成双臂；本 demo 通过
`controller.state()` 将两臂状态分别写入报告，不把两臂压入一个单臂 observation。
