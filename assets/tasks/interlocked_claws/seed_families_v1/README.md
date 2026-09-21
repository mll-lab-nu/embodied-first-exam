# Claw 固定模板与 seed 接口 v1

`catalog.json` 定义固定 family 选择池，保持 A/B/C 的选择语义，但如实记录可用性：
A0 有真实源网格和配套原始动作；B0/C0 只有设计，尚不能构建。不可用的 family 会被明确拒绝，不会退回 A0。

固定模板模式只随机材质，不重新随机发明功能结构。
`similarity_candidate` 在 A0 上联合变换两件几何、抓持变换与期望位姿；尺寸和位置范围是待复验的候选域，不是机器人或物理可行域。
同一正比例相似变换保留理想件间路径，但不能沿用原关节数组、固定支架或物理验收结果。

`reference_pair_certificate.json` 是原连续件间路径报告的逐字节保留副本，源文件位于
`runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/evidence/reference_geometry/reference_audit.json`。
报告只支持理想件间路径；原始网格、运动和证书哈希均绑定在目录中。
可运行 `topogym.tasks.interlocked_claws.reference_audit` 对固定源路径重新计算证书。

生成逻辑位于 [`variants.py`](../../../../topogym/tasks/interlocked_claws/variants.py)，
声明配置位于 [`interlocked_claws_variants.yaml`](../../../../configs/interlocked_claws_variants.yaml)。
使用共享 `VariantRng`、声明式采样器与 `EpisodeSpec`，没有修改全局 seed 派生规则。
没有数据集或 H5 导出；当前所有实例的 `dataset_eligible` 均为 false。

实现状态、接口示例和剩余门槛见 [生成器审查](../../../../docs/develop/tasks/interlocked_claws_variant_pipeline_audit_zh.md)。
