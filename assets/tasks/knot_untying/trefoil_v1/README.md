# 解绳结：基础 Trefoil 单结

一根两端开放的绳子，中间只打一个松 overhand 结。初始曲线由 Fourier trefoil 切去外侧无交叉弧段，再平滑接出两个自由端；诊断用的外侧闭合线不加入物理场景。
结型参考：[Wolfram MathWorld · Trefoil Knot](https://mathworld.wolfram.com/TrefoilKnot.html)。

基线：绳径 **8 mm**，总长约 **1.074 m**，两端各 **180 mm**；初态距桌面至少 **1 mm**，最高处约 **25 mm**。初始三个交叉的上下关系交替，右手有向交叉数为 +3。最小非相邻中心线间距约 11.51 mm，对应绳面间距 **3.51 mm**；最小弯曲半径约 27.11 mm。

- `geometry/rope.obj`：单一封闭表面、两端封盖的开放绳管，用于生成 FEM 体网格；不代表绳的两端彼此相连。
- `geometry/rope_initial.glb`：可独立查看的初始网格，两个末端用蓝／红色区分。模拟场景采用统一橙色软绳，GLB 端部配色仅用于资产查看。
- `geometry/centerline.json`：沿绳顺序排列的中心线，局部原点在桌面，+z 向上。
- `geometry/asset_report.json`：参数、三个交叉、Gauss 顺序、保守绳面间距与网格完整性。
- `geometry/sha256.json`：上述文件的哈希。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.knot_untying.prepare_assets
```

动力学使用 FEM+IPC 自接触、正常重力、直绳材料参考态。无端点固定、无形态保持约束；四面体在直绳参考态下反转时建场直接失败。初始绳是弯曲的预加载构型，不能据静态网格宣称其已通过物理稳定性或解结验收。

[任务说明](../../../../docs/develop/tasks/knot_untying_zh.md) · [场景预览](../../../../runs/environment_bootstrap/knot_untying/trefoil_initial/index.html)
