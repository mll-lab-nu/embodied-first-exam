# 真实 transition 数据

`EpisodeDatasetWriter(path, metadata=...)` 消费 Env 的不可变 `Transition`。
`.jsonl` 使用标准库，`.h5`/`.hdf5` 在打开时才加载 h5py；均流式写入。

每条记录保留真实提交的 action、前后 observation、reward、终止/截断信息、
episode/branch、前后 state_id、物理/控制计数和实际动作时长。恢复历史状态
产生新 branch，并在 info 中保留 `branch_parent_state_id` 连接历史源状态；父状态
可以仅存在于物理 history，未必有控制级 transition。writer 拒绝缺失恢复来源，
不伪造时间单调或覆盖旧数据。writer 不拍照、不读取 controller、
不推进物理、不从下一帧 EEF 位姿推断 action。

使用 context manager、`append(transition)` 和显式 `finish(result)`。只有完成
且无错误才把 `.part` 提升为目标文件；清单将数据完成与任务结果分别记录。

旧 RoboMME 风格的“下一帧姿态作为 action”格式已退出。当前 schema 为 2.0.0，
不在运行时维护旧字段别名。训练用标签应由显式外部 exporter 生成。

回溯后只保留一条有效轨迹。原始行可以保留为审计证据；读取有效数据必须使用
manifest 的 `active_transition_indices`，不能把全部 JSONL/HDF5 行都当成当前轨迹。
将 `writer.on_lifecycle` 注册到 `env.add_lifecycle_sink`，即使 rewind 后没有新 action，
废弃未来也会立即反映在清单中。管理方 reset 前应 finish/close 并解除旧 writer 订阅。
动作模式和实际执行关节目标在 Transition.info 中；机器人实测位置不冒充执行目标。
