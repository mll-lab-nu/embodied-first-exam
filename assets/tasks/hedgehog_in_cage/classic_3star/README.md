# CLASSIC 三星参考资产

原型为 RADEMIC CLASSIC ★★★ 普通铝制版本，10 刺，外形 45 × 80 mm。
`references/` 保存官方解法照片与来源记录；`template.json` 保存全部建模参数及其依据。

**本目录的 OBJ / URDF 是 TopoGym 的首版参数化重建，不是制造商发布的 CAD。**
官方公开资料尚不足以确定球径、各刺三维方向与长度、窗口宽高和内壁尺寸。
这些估计值集中登记在模板中，未混用 ORIGINAL 或 Badalec 模型的尺寸。
制造商原图保留原始归属；生成模型用于当前工程检查。

`geometry/` 为原尺寸（scale=1）的米制资产：

- `cage.obj` / `cage.glb` / `cage.urdf`：具有一个较宽侧窗的五窗圆柱笼重建，轴向孔保留。
- `hedgehog.obj` / `hedgehog.glb` / `hedgehog.urdf`：球核和十根平端圆柱，共用一个 link。GLB 默认内嵌木纹，刺球为浅木色、笼子为深木色，与 `classic_wood` 一致。
- `*_collision_*.obj`：逐块凸碰撞体。整个笼子和整个刺球均不取总凸包。
- `asset_report.json`：质量近似、碰撞块检查和无相交展示初态。
- `sha256.json`：本次生成资产的哈希。

重建命令，在仓库根目录运行：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.hedgehog_in_cage.prepare_assets
```

默认 `--finish wood`；需要金属外观时可显式指定 `--finish metal`。外观选择不改变碰撞体、密度、质量或惯量。

机器人演示使用统一三倍缩放，在运行目录另行生成对应的米制资产。
质量和惯量由缩放后的几何及铝密度估算，球与刺根交叠体积尚未扣除。
此处不把静态无相交初态认定为合法装配通路；退出解法和重力稳定性仍待验证。
