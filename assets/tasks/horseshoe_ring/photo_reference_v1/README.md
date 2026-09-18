# Horseshoe Ring 完整装配原型

结构以用户提供的银色双马蹄照片为依据：两个开口马蹄件、两条短链和一个独立圆环。
目标是保留马蹄与链条装配，将中央圆环取下。此前的三链环悬挂试验继续作为接触回归，不能代表本谜题。

`template.json` 使用毫米；展示默认统一放大 2 倍。所有尺寸、每条链 3 个链节及端部连接孔形状
都是明确记录的原型假设，没有照片对应商品的实测 CAD。马蹄表面的钉孔装饰未重建。

当前生成 9 个自由刚体：两个带闭合端部连接孔的马蹄、六个交替朝向的椭圆链节、一个目标圆环。
端部连接孔与各自马蹄属于同一刚体；相邻零件通过真实互套及接触连接，没有跨零件固定、球铰或隐藏焊接。
链节和圆环用连续胶囊复合碰撞体，马蹄带用凸分段，禁止对整个开口结构取单个凸包。
视觉使用带倒角的马蹄带和光滑银色金属管；质量按组件体积及密度近似，端孔焊接处重叠保留。

初始摆放是展开的无交叠装配姿态。它会在桌面上方留出最低点 1 mm 的间隙；默认不走仿真时间，
因此部分零件悬空。所有零件仍保留 6 个自由度。`run.settle_seconds` 可单独检查自由落桌，
其结果与静态展示、完整取环任务的验收分开记录。

几何检查包括跨零件保守间隙、8 处相邻闭环链接数、额外误串排查，以及目标环孔包含两条链跨度。
目标圆环与每个独立链环的两两链接数应为 0；这一必要检查**不能证明完整取环路径存在**。
原尺寸目前通过了完整折叠候选路径的连续间隙复核，但没有取下圆环。
模板圆环中心线半径 35 / 36 mm 的大环通过直接滑出路径检查；它们是过大的正对照，不是谜题验收版本。
原型的完整取环验证、链条松弛到拉紧的全程验证及双臂操作仍未完成。

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.horseshoe_ring

# 将同一装配放入共用实验室、桌面和机械臂场景：
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.horseshoe_ring \
  --config-name horseshoe_ring_lab

# 无 CUDA 时的实际场景光栅预览：
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.horseshoe_ring \
  env.genesis.backend=cpu env.renderer.type=rasterizer

# 追加短时重力落桌检查，保存独立运行目录：
PYOPENGL_PLATFORM=egl LIBGL_ALWAYS_SOFTWARE=1 .venv-gs121-nyx/bin/python \
  -m demos.environment_bootstrap.horseshoe_ring \
  env.genesis.backend=cpu env.renderer.type=rasterizer \
  run.settle_seconds=1.0 run.record_video=false \
  run.output=runs/environment_bootstrap/horseshoe_ring/assembly_settling
```

输出在 `runs/environment_bootstrap/horseshoe_ring/assembly_initial/index.html`，包含三视图、相机绕行视频、
每个零件的 URDF / GLB / 碰撞网格、完整 `assembly.glb`、参数快照和检查报告。

结构与折叠原理另参考 [J. A. Storer 实物收藏记录](https://www.cs.brandeis.edu/~storer/JimPuzzles/ZPAGES/zzzHorseShoes.html)
与 [Triple S Games 实物解法演示](https://www.youtube.com/watch?v=qgI7h2Gyk1w)。
这些参考对应不同版本，不作为本照片的精确尺寸来源。

本轮进一步核对了 [Professor Puzzle Ltd 官方解法视频](https://www.youtube.com/watch?v=LAE1w1VNIZg)
（Puzzle and Perplex - Horseshoes Solution，2017-06-07）：转动并收拢两只马蹄，将圆环移过靠拢的弯曲端，再取下。
官方视频可指导动作顺序，但没有提供本原型的尺寸、接触容差或机器人可执行性保证。

实验室 demo：`runs/environment_bootstrap/horseshoe_ring/lab_initial/index.html`。
尺寸对照与证据：`runs/environment-solvability/horseshoe_ring/index.html`。
更多运行命令和本轮结论见 [`horseshoe_ring_zh.md`](../../../../docs/develop/tasks/horseshoe_ring_zh.md)。
