# 刺球出笼：CLASSIC 三星初态演示

2026-09-17 新增：[从可解 IK 反推偏心斜窗笼](hedgehog_in_cage_inverse_window_zh.md)，包含完整提取、落桌释放、物理检查与三视角录制流程。以下保留最初的资产与初态工程记录。

同日新增：[三个动作 family 各一个完整代表 demo](hedgehog_in_cage_family_demos_zh.md)，包含单斜窗、双门槛及螺旋导向的实体结构、两档子步物理执行和三视角对照。

日期：2026-09-16。范围：参考资产准备、参数化重建、带静止机械臂的初态展示。

变体空间规划：[3 个动作 family × 3 种外形](hedgehog_in_cage_family_space_zh.md)，区分设计候选、可解性证据与完整物理演示。

## 型号与资料

按用户选择保留三套独立模板：CLASSIC 三星（10 刺）、ORIGINAL（12 刺）、Worrall 1896（13 刺）。
本次只实现第一套。刺的数量、排布与笼子结构应成套变更。

官方资料：[CLASSIC 产品页](https://puzzles.rademic.cz/classic.htm)、
[官方解法页](https://help.rademic.cz/)、
[三星版英文解法图](https://help.rademic.cz/hedgehog_in_the_cage_puzzle_classic_solution_rademic_puzzles_IMG_2432um.jpg)。
三星普通版和五星黄铜／不锈钢版的解法图不同。

已知外形为 45 × 80 mm、10 刺、一个较宽出口。未获得官方 CAD 或完整工程尺寸。
本次资产是带来源标注的重建：球径、刺位、刺长、内壁、五窗排布和圆角都是暂定值。
未套用其他型号的刺长、球径或间隙数据；不宣称已经复现 CLASSIC 的真实退出运动。

## 文件与运行

| 路径 | 用途 |
| --- | --- |
| `assets/tasks/hedgehog_in_cage/classic_3star/` | 官方参考图、来源、参数及原尺寸 OBJ / URDF |
| `topogym/tasks/hedgehog_in_cage/geometry.py` | 笼体分块、十刺球、质量惯量估计和初态几何距离检查 |
| `topogym/tasks/hedgehog_in_cage/prepare_assets.py` | 不加载 Genesis 的资产生成入口 |
| `topogym/tasks/hedgehog_in_cage/scene.py` | 共享桌面、Panda + Robotiq、固定笼和自由刺球 |
| `topogym/tasks/hedgehog_in_cage/demo.py` | 静态渲染、相机巡视视频、运行报告与本地页面 |
| `configs/hedgehog_in_cage_classic_preview.yaml` | 缩放、布局、相机和输出配置 |

从仓库根目录运行：

```bash
PYOPENGL_PLATFORM=egl .venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.demo
```

也可通过 `-m demos.environment_bootstrap.hedgehog_in_cage` 运行。
加 `run.record_video=false` 可只生成静态图片。
输出为 `runs/environment_bootstrap/hedgehog_in_cage/classic_initial/index.html`，并接入环境汇总页。

## 场景与检查范围

原型统一放大 3 倍，笼体外形 135 × 240 mm；机器人保持原尺寸。
笼体固定在桌面底座，刺球为一个保留 6 自由度的刚体。所有刺与球核共用一个 link。
球核凸块、逐刺凸块和逐段笼体凸块保留孔道，不对整件凹形物体取凸包。

确定性搜索无相交姿态，再下移到接近笼体支撑的位置。球核使用球包络，刺使用包围实际锥形刺的圆柱包络；
对中心线采样并将半采样步长计入半径，得到保守的连续间隙下界。
初态检查只涉及刺球与笼体，不代替全机器人运动可达性或装配路径验证。

机器人只在初始化时设置 home；演示不调用 `scene.step()`，不执行操作轨迹。
视频只改变相机，报告核对前后机器人和刺球 qpos 完全相同。
因此 `simulation_steps=0`，不声称重力静置、摩擦抓持、释放或求解已经通过。

后续先补几何尺寸和官方解图对应姿态，再验证接触与退出路径；“各侧等宽可退出”在此基准上另行改造并验通路。
