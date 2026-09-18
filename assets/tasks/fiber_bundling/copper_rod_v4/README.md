# 光纤收束：细铜杆支架版

本目录 `geometry/` 是 8 芯、环内半径 13.5 mm、形状种子 7 的实际资产副本。粗护套半径 12 mm；细线半径 1.2 mm、长度 80 mm；细线和粗电缆的材料参数保持原版。

环由直径 5 mm 的固定铜杆连接到底座，杆顶嵌入环外缘下方 2 mm。铜色 PBR：金属度 0.85，粗糙度 0.32。场景中的碰撞杆也为半径 2.5 mm 圆柱，不保留旧矩形柱的碰撞体。铜杆作为固定夹具，不模拟其自身弯曲。

- `geometry/bundle.xml`：固定终端、余量电缆、工作护套和全部被动细线的动态 MJCF。
- `geometry/ring.urdf`：闭环的复合碰撞体，视觉读取 `ring.glb`。
- `geometry/ring_fixture.glb`：铜环、铜杆、底座的静态检查资产。
- `geometry/scene_initial.glb`：终端、电缆、线托和环支架的完整静态资产。
- `geometry/asset_report.json`：尺寸、根部间距、实际孔径和支架签名。
- `geometry/sha256.json`：资产文件哈希。
- `preview_config.yaml`：本次预览使用的解析配置；正式入口为 `configs/fiber_bundling_copper_preview.yaml`。

支架真实碰撞在 `topogym/tasks/fiber_bundling/ring_mount.py` 中按同一组参数创建。`scene_initial.glb` 只用于检查外观，不能替代 MJCF / URDF 的动态环境。

场景预览及短时物理报告：`runs/environment_bootstrap/fiber_bundling/2026-09-17_copper_rod_v4_cpu/`。0.5 s 静置无可测漂移；相机视频已解码检查。新支架的全流程机器人穿环尚未验证，旧矩形支柱 demo 不能直接为此版验收。

三类变体通过线数与环内半径控制，规则在 `configs/task_variants/fiber_bundling_density_v1.yaml`。已生成的九个几何代表及截面图在 `runs/environment_bootstrap/fiber_bundling/2026-09-17_density_radius_v1/`。完整说明见 [材料与变体设计](../../../../docs/develop/tasks/fiber_bundling_density_radius_zh.md)。

当前材料是零刚度、带阻尼、重力补偿的被动关节链，可以保留接触后的形变；不是经过标定的铜线弹塑性模型。
