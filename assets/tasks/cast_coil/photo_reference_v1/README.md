# Cast Coil 照片参考原型

`template.json` 是本仓库编写的尺寸模板，单位 mm。它不是官方 CAD，尺寸、内侧槽口及侧桥位置均未实测。

结构来源为 [Hanayama 产品说明](https://hanayama-toys.com/product/cast-coil/)、
[官方装配和拆件照片](https://store.hanayamatoys.co.jp/items/55630234)，以及
[Eureka 发布的 Hanayama 分解示意](https://www.eureka-puzzle.eu/wp-content/uploads/2022/09/515056-Huzzle-Cast-Coil-Oct-2017.pdf)。
第三方图片和 PDF 不作为本仓库自产模型分发；生成模型由本地参数构造。

每件包含两层开口的方形回折，在右侧由跨层连接桥接成一个连续实体；两件按金、银、金、银排列。
银件基本形状由金件绕 x 轴转 180° 得到，并有额外内侧缺口。各层内侧矩形凹口是基础近似，实物圆弧转动窗口、倒角和准确槽位尚未恢复。

原型外形为 34 × 24.75 × 34 mm，宽 7 mm、层厚 6 mm、层间隙 0.25 mm。
基础场景统一放大 3 倍至 102 × 74.25 × 102 mm，间隙同步放大。
密度暂设 6700 kg/m³；放大后单件约 1.5 kg，质量按三次方、惯量按五次方缩放，尚未通过抓持承载验证。

几何导出使用正交盒体的精确布尔分区，输出连通、封闭的表面网格及不重叠的碰撞盒集合。
质量和惯量从同一实体计算。每个 URDF 仅有一个 link，无内部或跨件关节；不会将整件凸包化填孔。

运行生成的 GLB、URDF、尺寸快照与检查报告位于 `runs/environment_bootstrap/cast_coil/assembly_initial/assets/`。
`separated_inspection.glb` 是人为摆放的拆件检查布局，不是从装配态沿合法路径求解的结果。

完整复现和验证范围见 [任务说明](../../../../docs/develop/tasks/cast_coil_zh.md)。

`variants.json` 提供 3 倍基线、30° 整体旋转和 2 倍缩小实例；不修改槽口或跨层连接。
后续的连续几何证书和受力台架检查见
[可靠性与可解性报告](../../../../runs/environment-solvability/cast_coil/photo_reference_v1/index.html)。
报告中的三段原型路径与官方八步示意不是同一份解法，不能直接作为商业实物或正式机器人任务的验收。
