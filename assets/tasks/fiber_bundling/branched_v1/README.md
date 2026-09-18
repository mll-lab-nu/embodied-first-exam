# 光纤收束：分叉绳资产

**历史自由电缆版本。当前默认已改为 [固定终端与承托支架 anchored_v2](../anchored_v2/README.md)。本页 demo 与通过结果不能用于新版验收。** 重建本历史版本须显式使用 `prepare_assets --legacy-free --output assets/tasks/fiber_bundling/branched_v1/geometry`。

这是按 2026-09-16 用户定义生成的机器人尺度原型：一根较粗绳的末端连接多根细绳，机械臂只能抓粗绳，通过固定闭环的接触整理分叉。

当前基线为直径 24 mm、长 240 mm 的粗绳，8 根直径 2.4 mm、露出长度 **80 mm** 的细绳。各线从护套出口先沿轴向伸出约 **16 mm**，随后逐渐自然外弯，曲率和侧向偏转略有随机差异；末端切线角在 **28–50°** 内采样。该角度指线头方向，出口方向仍与护套相同；seed=7 的整体横向包络半径约 32.46 mm。环孔半径 13.5 mm，环管半径 4 mm。粗绳端面上的连接位置不随随机种子变化。

外观采用黑色低光泽电缆护套、红/蓝/绿/棕/白/黄/黑/灰绝缘线；护套切口有薄壁与填充层，各线末端露出约 3 mm 的七股铜丝。颜色仅用于视觉区分，不赋予电气接线含义。切口、填充层和铜丝是随各自实体运动的视觉细节，碰撞仍采用原半径的粗绳与细绳外包络。

- `geometry/bundle.xml`：可模拟的 MJCF 树，粗绳 6 节、每根细绳 10 节；主绳自由基座，全部细绳为被动球关节胶囊链，无细绳执行器。
- `geometry/jacket_lip.obj`：护套切口网格，供动态模型引用。
- `geometry/jacket_segment.obj` / `jacket_end_segment.obj`：护套侧壁网格，消除分段端盖法线造成的珠节状明暗。
- `geometry/ring.urdf`：64 段圆柱加球端组成固定闭环，保留真实孔洞。最小净孔半径约 13.479 mm。
- `geometry/bundle_initial.glb` / `.obj`、`ring.obj`：供其他工具查看的初始几何；动态场景直接加载 MJCF / URDF，网格预览不替代碰撞模型。
  OBJ 的颜色贴图由同目录 `material.mtl` / `material_0.png` 提供；GLB 自带材质。
- `geometry/centerlines.json`：初态中心线与固定连接点，坐标原点在粗绳后端，+x 朝向分叉。
- `geometry/asset_report.json` / `sha256.json`：参数、初始间距、抓取白名单与产物哈希。

重建：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.prepare_assets --legacy-free --output assets/tasks/fiber_bundling/branched_v1/geometry
```

Genesis 场景必须给整个 cable 实体设置 `gs.materials.Rigid(gravity_compensation=1)`；文件里的 `gravcomp` 同时说明 MJCF 原生语义，不能假设 Genesis 会按 body 自动读取它。世界保留正常重力。
首版将粗绳也设为重力中性，使无接触初态不靠隐藏固定夹具悬停。关节为零弹性刚度与正阻尼，碰撞可改变形状，停止运动后不主动恢复随机初态。

初始弯曲仅写入初始化的关节坐标系，不是永久曲线或弹簧恢复目标。局部配对试验已验证：接触环口后只移走环，不改写电线状态，继续被动模拟 1.5 s；残余弯曲保留，最后 0.3 s 未测到形状漂移。见 [形态对比与卸载报告](../../../../runs/environment_bootstrap/fiber_bundling/contact_probe/index.html)。这是零刚度阻尼关节的塑性形状保持近似，不包含铜材的弹性恢复、屈服阈值或硬化本构。

这是离散杆链近似，不模拟真实玻璃光纤的弹性、断裂或微米尺度接触。球关节允许三维转动；无接触时的形状保持不等于全程碰撞稳定，也不保证未经调整的直推一定无法穿环。
完整说明与运行入口见 [任务文档](../../../../docs/develop/tasks/fiber_bundling_zh.md)。

[单根红线整理过程](../../../../runs/environment_bootstrap/fiber_bundling/single_strand_demo/index.html)：通过粗绳夹持端的偏移、推进、回拉及朝向调整，利用固定环整理红线。全部细线保持被动；该 demo 验证局部整理动作，尚未执行机械臂实际抓取或整束穿环。

数值稳定性补充检查已通过：自由基座静置 10 s、接触动作后静置 5 s，以及 2 ms / 1 ms 时间步独立复跑。检查连接约束、段长、接触穿透、独立线间距离、有限状态与末期漂移；CPU 和 GPU 的具体结果分别见 [CPU 报告](../../../../runs/environment-solvability/fiber_bundling/stability_cpu/index.html)、[GPU 报告](../../../../runs/environment-solvability/fiber_bundling/stability/index.html)。这些结果限定于当前 seed 和离散模型，不代表真实铜材力学已标定或机械臂抓取已验证。

[逐根整理八根电线，再整束穿环](../../../../runs/environment_bootstrap/fiber_bundling/full_bundle_demo/index.html)：使用环外侧逐个轻压线头，转动和移动粗绳来选择受压方向；细线始终被动。33.95 s 的完整物理轨迹通过细线及整段粗绳穿环检查，已整理线累计最大形变约 0.080 mm（阈值 0.5 mm）。视频含各根电线与最终穿环的跳转按钮；仍为显式粗绳夹持端演示。
