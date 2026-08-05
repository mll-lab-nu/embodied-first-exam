# tasks/legacy —— 四分类之前的任务

这里的任务先于 `docs/develop/framework/task_taxonomy_zh.md` 的四类能力轴存在，尚未在该轴上定位。

**`legacy` 在本目录的含义是「未在能力轴上定位」，不是「已废弃」**，与
`docs/develop/modules/legacy_ag_blueprint/`（那份 README 写明「已过期，别拿它理解现在的代码」）
语义不同。下表逐任务记录实际状态。提升到类别目录只需移动单个 `.py` 文件并改一行 import。

| 任务 | 实际状态 |
| --- | --- |
| `swap` | 框架成型前的刚体滑块任务，不考察四类空间关系中的任何一类。**仍是 `bash_scripts/tests/pi05_smoke.sh` 与 `verify_dataset_recording.sh` 的默认任务**，也是唯一有 episode split、被 `dataset_generation_prerequisites_zh.md` 标为「完全就绪」的任务；`SwapMdpEnv` 被 `docs/develop/framework/env_format_zh.md` 引为 env 接口契约的参考实现。在另一个任务达到同等就绪度之前，它继续承担数据管线验证。 |
| `onestroke` | 五层实现齐全（tasks / verification / planning / generation / envs），未接入数据管线（缺 episode split）。判据是网格图上两色区域的连通性，定义在预设离散图上而非连续 C_free，与类别 4 的判定契约不同形。 |
| `maze_wall_removal` | 同上：五层齐全、缺 split、判据定义在预设网格图上。`docs/develop/data_pipeline/robomme_benchmark_deliverables_zh.md` 把它与 swap 并列为立 schema/合约的低风险载体。 |
| `peeling` | 在 `bash_scripts/tests/stability_sweep.sh` 的扫描矩阵与 `topogym/generation/layout_randomization.py` 的随机化注册表中，与已归类的四个任务并列。归类未定：当前判据（`blocked_by` 覆盖关系门控的剥离顺序）属可达性，倾向类别 4 的遮挡顺序变体；若改造为可形变薄膜则属类别 1。 |
| `peeling_physical` | `peeling` 的 PBD 物理执行层，共用其 planner / generator。归类随 `peeling` 一并确定。 |
