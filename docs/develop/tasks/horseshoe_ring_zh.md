# Horseshoe Ring：官方教程结构、可解路径与 ALOHA 演示

后续已实现[由新 IK 轨迹反推可解场景](horseshoe_ring_trace_scene_variants_zh.md)。
新实例的关节、抓点、换抓路径和场景参数共同变化；保留的固定 trace 变体仅用作几何族与对照。

完整入口：`runs/environment_bootstrap/horseshoe_ring/aloha_full/index.html`。
采用共用实验室和 ALOHA 双臂，展示预置抓持、翻转马蹄、双臂折合、交接支撑、
换抓圆环、调整脱出及终态；包含近景、实验室视角和四路同步观测。

这是完整取环的**运动学预演**：谜题内部的连续几何路径已验证，机器人逐帧关节位姿及零件位姿
由脚本设置，物理步数为 0。预置抓持不包含从桌面自主拾取；交接时保持零件姿态属于运动学假设。
还不能作为力驱动机器人任务成功，摩擦、夹持稳定性、重力下的换抓及抗扰动需要后续验证。

## 教程与双臂判断

参考 [Professor Puzzle Ltd：Puzzle and Perplex - Horseshoes Solution](https://www.youtube.com/watch?v=LAE1w1VNIZg)
（2017-06-07）。查看高清教程后，将早期每跨三链节的照片原型调整为：
两只马蹄、两只独立中间链环、一只目标环，共五个自由刚体。四个端部连接眼与马蹄为同一刚体，
连接眼平面垂直于马蹄扁带；没有将链环固定为一个整体。

教程先翻转并收拢马蹄，再换抓、调整圆环并使其越过靠拢的弯曲端。
不添加夹具时，这一操作需要同时控制两个对象，适合使用双臂。
这是针对当前操作流程的判断，不是“任何单臂方案均不可能”的证明；桌面支撑或夹具可以改变操作条件。
演示使用已有 ALOHA 模型、控制器和实验室布置，保留上游关节限位。

教程用于结构与动作顺序参考，不提供商品的精确尺寸或可直接复制的机器人轨迹。
本地模板是可解性原型，并非照片商品的实测 CAD。

## 已验证的原型

模板：`assets/tasks/horseshoe_ring/tutorial_solvable_v3/template.json`，统一放大两倍。
目标环中心线半径 31 mm、线半径 1.4 mm，在场景中内径为 118.4 mm；
马蹄外宽约 131.99 mm。初态沿长轴直接拉环的路径被连续碰撞检查拒绝。

完整独立刚体路径有 3365 帧，包含两轴翻转折合及目标环的独立调整。
所有十组零件对都参与检查；初始连接、初态与模板一致、全程间隙及最终完全分离均通过。
连续区间的最小保守间隙下界为 **0.1006086 mm**，
终态环与装配包围盒分离 **54.8865 mm**。
证据位于 `runs/environment-solvability/horseshoe_ring/tutorial_solvable_v3/`。

检查使用实际扁带凸段，以及外切多面体覆盖 URDF 中圆柱和球体；没有把带孔零件变成实心凸包。
每个刚体 COM 线性移动、四元数按最短 SLERP 插值。
以端点表面距离扣除区间中最大表面移动上界，不能保证正间隙时自适应细分。
这是保守几何覆盖和浮点距离计算形成的数值证据，不是精确实数形式化证明。
修改尺寸、碰撞网格、尺度或插值规则后，必须重新验证。

## 双臂预演和碰撞检查

为避免六自由度机械臂的腕部限位，将相对旋转均分给两臂，并给全部五个谜题零件施加同一连续刚体变换。
这保持全部谜题内部相对距离。接触目标位于实际指垫中心，而非指垫后方的原始末端 site。
右臂换为合并支撑后，左臂从下方接近圆环，再沿完整几何见证取出圆环。

空手换位使用碰撞检查过的关节路径；直线路径受阻时使用 OMPL RRTConnect。
最终全部视频帧检查机器人自身、机器人与谜题以及桌面穿透。
容差分别为 0.1 / 0.3 / 1 mm，实际结果记录于 `replay_report.json`。
这是采样碰撞检查，不是机器人全连续路径的无碰撞证书，也未覆盖所有实验室背景设施。
实际 Genesis 渲染还逐帧核对指垫跟随误差；超过 0.5 mm 则中止导出。

## 四路相机

命名对应 [ALOHA 官方采集代码](https://github.com/tonyzhaozh/aloha/blob/main/aloha_scripts/robot_utils.py)：

| 输出 | 上游相机 | 用途 |
| --- | --- | --- |
| `cam_high` | `overhead_cam` | 双臂和整体布局 |
| `cam_low` | `worms_eye_cam` | 高度、遮挡与穿越关系的补充 |
| `cam_left_wrist` | 左腕相机 | 左指垫附近 |
| `cam_right_wrist` | 右腕相机 | 右指垫附近 |

安装姿态取自 [固定提交的 Menagerie ALOHA](https://github.com/google-deepmind/mujoco_menagerie/tree/8161bba264d7fa7c99ca301e91e7fb44737676ad/aloha)。
固定相机与机器人使用同一来源坐标转换，包括共享机器人适配器的 20 mm 下移；
腕相机绑定左右 `gripper_base`。实现为 `topogym/world/aloha_cameras.py`。

四路均为 1280×720，垂直视场角约 58.0083°。
来源内参 fx≈634.086、fy≈649.346；Genesis 单一垂直视场角产生 fx=fy≈649.346，
水平焦距差约 +2.4065%。保留并报告这一差异，不宣称完整硬件标定等价。
检查发现原低位朝向会截掉抬高的任务区，因此保留其上游安装位置、额外上仰 20°；这是明确记录的任务适配，不是原始上游朝向。
`detail`、`oblique` 和 `room` 提供展示覆盖。
每帧实际四相机位姿保存为 `camera_poses.json`，实际初态内参保存为 `camera_report.json`。

## 复现

以下命令从仓库根目录运行。规划环境 `.venv-gs121` 包含 FCL、MuJoCo、OMPL；
Genesis 渲染环境为 `.venv-gs121-nyx`。

```bash
# 重验保存的完整几何路径
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. .venv-gs121/bin/python \
  -m topogym.tasks.horseshoe_ring.independent_motion \
  runs/environment-solvability/horseshoe_ring/tutorial_solvable_v3/body_poses.json \
  --output runs/environment-solvability/horseshoe_ring/tutorial_solvable_v3/certificate.json

# 生成双臂运动学预演，检查 IK、换抓避障及全部视频帧的碰撞
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. .venv-gs121/bin/python \
  -m topogym.tasks.horseshoe_ring.robot_motion

# CPU / EGL 导出全过程、四路原始视频、拼图和 HTML
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=. \
  .venv-gs121-nyx/bin/python -m topogym.tasks.horseshoe_ring.aloha_demo \
  --backend cpu --renderer rasterizer

# 相关回归
OPENBLAS_NUM_THREADS=1 PYTHONPATH=. .venv-gs121/bin/python \
  -m unittest discover -s tests -p 'check_horseshoe*.py' -v
PYTHONPATH=. .venv-gs121/bin/python -m unittest discover -s tests -p 'check_aloha*.py' -v
```

页面可直接用浏览器打开，也可从仓库根目录运行 `python -m http.server 8000 --bind 127.0.0.1`，
访问 `http://127.0.0.1:8000/runs/environment_bootstrap/horseshoe_ring/aloha_full/`。
源模板和几何见证哈希用于防止拿旧证书验证新尺寸。

## 保留的早期对照

- `photo_reference_v1`：九刚体照片原型；R29 的局部折叠没有取出，整体可解性仍未知。
- `tutorial_structure_v2`：五刚体较小环探索模板，没有完整取出证书。
- 早期九刚体 R35 / R36 的内径为 132.8 / 136.8 mm，可直接滑出，仅作大环正对照。
- 更小环的有限搜索失败只否定指定路径，不证明无解；也没有声称某个连续尺寸区间全部有解。

原尺寸对照页面仍在 `runs/environment-solvability/horseshoe_ring/index.html`。
新 v3 的几何与证据单独保存，不能把新模板的证书套用到旧模型。
