# 开锁初态可视性调整

日期：2026-09-16。需求：解释 `environment_bootstrap` 的用途，增大锁片间距，使每片锁眼图案能看清。

| 子步骤 | 状态与证据 |
| --- | --- |
| 解释目录职责 | 已在 [源码说明](../../topogym/tasks/README.md) 和 [review 汇总页](../../runs/environment_bootstrap/index.html) 加入源码、配置、运行产物的区别。 |
| 联动修改几何 | 新 [配置](../../configs/lock_picking_spaced_preview.yaml)：盘间距 / 钥匙凸片间距 85 → 150 mm，握柄偏移 300 → 495 mm，桌面 x 尺寸 1.5 → 1.8 m；保留原角度与限位。 |
| 检查理论通路 | 重新计算两次必要回退证书；1,717 个几何路径采样状态的孔道与盘角限位检查通过；加长底座仍在桌面范围内。 |
| 建场与初态静置 | 新版 `LockPickingSceneBuilder` 实际建场，Genesis CUDA / rasterizer；静置 200 步、1 s，钥匙由实体支撑承重。见 [检查报告](../../runs/environment_bootstrap/lock_picking/spaced_initial/inspection_report.json)。 |
| 渲染与人工查看 | 已生成同一初态的六张原始图片；检查了三片锁眼正视近景、机构斜视及机器人全景，锁眼可辨认。 |
| 接入 review | [新初态页面](../../runs/environment_bootstrap/lock_picking/spaced_initial/index.html) 已加入汇总页及原初态页；[理论解法文档](../develop/tasks/lock_picking_two_retreats_solution_zh.md) 追加新间距的范围说明。 |
| 黄色锁眼描边 | 按用户要求，在三片锁眼边缘添加宽 1.5 mm、RGB `(1.0, 0.95, 0.0)` 的黄色轮廓；生成于锁片正反面纹理，随盘转动。已重新渲染并查看正视 / 斜视图。 |
| 描边物理一致性核对 | 比较描边前后 8 份 URDF 的碰撞、惯性及关节节点，以及 1,657 个碰撞网格引用的 SHA-256，均相同。见 [描边核对记录](../../runs/environment_bootstrap/lock_picking/spaced_initial/outline_verification.json)。 |

实例目录：`runs/environment_bootstrap/lock_picking/spaced_initial/`，包含完整配置、URDF / 网格、图片和检查报告。

复现命令（仓库根目录）：

```bash
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking_inspect
```

新间距只完成初态与几何检查。全插入行程由 340 增至 600 mm，机器人抓取 / 全行程可达性与完整动力学待验证；三张近景相机用于人工查看。原 85 mm 实例的执行成绩仍只对应原几何。
