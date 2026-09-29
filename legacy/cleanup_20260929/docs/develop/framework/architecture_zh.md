# 项目架构与开发约定

TopoGym 将任务实例构造、物理执行、机器人控制、agent 求解与数据导出分开维护。任务清单来自 `topogym/tasks/catalog.py`，现登记 13 项。

| 层 | 实现 | 职责 |
| --- | --- | --- |
| 配置与实例 | configs/task_cards、task_variants；generation | 任务身份、具名 RNG、EpisodeSpec、完整实例及来源哈希 |
| 任务 | tasks/<task_id> | 几何、场景、控制/规划、目标和私有判定 |
| 世界与机器人 | world、robot、primitives | Genesis/MuJoCo 接入、软体/接触、渲染、IK、共享动作和辅助抓持 |
| 执行与诊断 | runtime、planning、supervision | episode 契约、通用路径、稳定性与几何/物理检查 |
| Agent | agent_bridge、agent_rollout | 单 episode 分段接口；冻结 suite、trial/reset、权限、预算与评测 |
| 数据 | data、utils | HDF5 schema/writer、相机、录像与通用工具 |

任务生成遵循：设计固定家族 → 在有界参数域采样 → 保存完整实例 → 执行器消费同一实例 → 独立验收 → 录制/数据导出。
`sample`、几何 accepted、IK 通过、物理成功及 export_ready 是不同状态；seed 改变 ID 而配置不变不算参数随机化。
恢复已有实例必须核对展开配置与资产哈希，不重新采样。实例改变尺度、pose、材料或控制后不能继承旧物理资格。

当前 task card 的 factory 是接入依据；旧 preview 配置未声明 variation 时不能直接调用公共随机化入口来假装得到新实例。
共享模块不导入 legacy，不内置任务解法；任务 adapter 提供公开动作/相机说明和私有判定，参考轨迹不交给受测 solver。

## 文档与产物

- `docs/develop/modules/`：当前模块接口及使用；任务一项一页在 `docs/develop/tasks/`。
- `docs/progress/current_zh.md`：当前完成度、验收缺口和下一步，不追加每日流水账。
- `demos/<task_id>/<camera>/`：当前正式版本，每视角独立 MP4；每个叶子目录只保留一份 MP4；完整流程优先，未完成任务另行标注。
- `runs/demo_metadata/<task_id>/<run_id>/`：正式视频依赖的报告、配置、轨迹、资产与清单。
- 其他 `runs/`：开发中任务的最新进展、恢复依赖及必要反例；停止使用且已被替代的过程产物可清理。
- 一次性脚本在仓库外临时目录；可复用代码归入任务包、scripts 或 tests。

替换正式视频先核对帧数/时长同步、完整解码、哈希及证据对应，再删除被替代版本。新进展交付 MP4 直链，不维护展示 HTML。
清理必须检查运行/队列、代码读入路径、配置源快照与测试夹具。只按目录日期或 Git 忽略状态判断无用，会破坏当前任务。

坐标见[坐标约定](genesis_world_coordinates_zh.md)，渲染见[默认 Nyx](../visual/default_nyx_lab_zh.md)，数据见[HDF5](../data_pipeline/h5_data_format_zh.md)。
