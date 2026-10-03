# 共享录制

`RecordingSession` 只消费 simulator 提供的不可变 `SensorFrame`，不创建场景、
相机或机器人，不包装 `scene.step`，不修改物理状态，也不判定任务成功。

调用方式：在 context manager 内调用 `append(frame)`，结束时显式调用
`finish(result)`。多相机使用同一份源状态及时间标识；视频抽样记录源时间与
目标媒体时间，重复帧沿用源 state_id。

RGB 由运行时 Nyx 相机生成，背景统一为 compact_lab。RecordingSession 不选择另一种
renderer，也不负责恢复历史状态。应先完成并关闭 RecordingSession，再关闭
Env 或重建 episode；使用嵌套 context manager 时，让 RecordingSession 位于
Env 的上下文内部，以便先写完视频与帧索引，再释放 Nyx 场景资源。

一个 session 对应一个 episode 的一个 branch。历史状态恢复后必须结束当前
session 并建立新输出目录，不能把回退前后的视频拼成一次连续物理执行。
退出时未 finish 或出现错误，清单标记 `incomplete`。媒体完成不表示任务成功。

旧任务录制/重建适配器、各任务 archive/render、MuJoCo 渲染、历史 demo
迁移和独立状态重渲染入口已退出。历史状态恢复统一由 Env/World 管理。
ffmpeg 仅在实际写视频时需要，不是核心安装或环境运行的前置条件。

`rigid_replay.record_rigid_history` 为完整刚体 articulation 历史提供管理方重渲染：
仅在临时 Env 恢复所有已记录关节坐标（含被动夹爪关节），不推进物理；逐帧
核对每个 link 的位姿，强制刷新同 tick 的可视几何，再把带原始时间身份的
SensorFrame 交给 RecordingSession。要求来源从 birth 连续且没有 rewind，
拒绝缺失坐标及粒子/FEM 场景。重渲染不增加物理成功次数。

`archive.archive_recording` 将至少三路同源同步 MP4 及独立证据复制到新归档：
全量解码、帧数/帧率/尺寸同步检查、复制前后哈希核对；已有目录不覆盖。
任务方提供实际资格和来源元数据，媒体工具不自行判定任务成功。
