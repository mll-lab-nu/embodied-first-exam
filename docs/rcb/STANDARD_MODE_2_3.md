# TopoGym standard 2.3 与 tooling v5 合同

本页记录合并后修复的实际接口变化。通用请求、相机、proprio、RCB1 和进程模型沿用 [2.2 协议](STANDARD_MODE_2_2.md)。旧任务包保留原协议与工具字节，新生成包使用 `eai-standard/2.3` / tooling v5。运行镜像版本由 `images/topogym/VERSION` 决定，不能单独替换镜像就认为旧包获得了工具修复。

## 1. 输入与实例资格

- privileged 评分先检查 NPZ 和数组头，再创建模拟器。缺键、非法形状、非数值类型、非有限动作及越界长度是 `bad_trajectory`，收集为 `invalid_submission`；宿主读盘、可信实例损坏及模拟器故障不转嫁为提交错误。
- `joint_position.dt` 必须是控制周期的整数倍，容许有限的浮点表示误差。40 Hz 下 `0.025`、`0.05` 合法，`0.0375` 会在执行前被拒绝。
- 两种评分模式均要求实例匹配。新创建实例记录生成资产身份与软体节点位置/速度；资产身份只归一化本次构建的临时目录前缀。软体不能只凭质心匹配通过。
- 新工具读取旧软体实例时，如果没有完整节点参考，就不能用质心替代失配的精确状态哈希；应使用新生成器重新创建实例。旧冻结包继续由旧工具读取。
- GPU 的最终状态哈希仍是诊断项。实例不匹配会输出 `instance_mismatch`，收集为 `not_evaluable`，不会获得成功成绩。

## 2. 动作、轨迹与时间

`Session.step` 只有完成实际执行后才追加轨迹。拒绝动作不入执行记录；任务终态后的调用返回结束状态，不再增加动作数或时钟。原生执行故障不提交整行，不能把未知的部分推进冒充完整控制步。

轨迹仍以 float32 `actions` 为主，新增可选 `trajectory_version=2` 和整数 `physics_steps_per_action`。`record_stop()` 后保存同一组动作时会保存实际 tick 账本。任意传入的计划数组不自动冒充已执行轨迹。

正式 standard 导出只保存实际执行前缀。共享读取器兼容旧 `meta.live_rows`；读取旧轨迹时，没有记录的 tick 精度仍然未知。实际 tick 元数据只由可信 standard 回放和管理方回放使用；privileged 外部提交不能通过填写该数组改变官方控制周期。

`control_steps` 是实际执行的控制调用数，`physics_steps` 是完成的物理 tick 数，`sim_time_s` 来自实际物理推进。控制周期中提前终止于 3 tick 时，默认配置下时间是 `0.0075 s`，不能按完整周期报成 `0.025 s`。standard 的响应帧时间也使用该实际时钟。

协议历史字段 `physics_substeps` 仍表示每控制周期的物理 tick 数，不是 Genesis solver 的内部子步数。子步接触合同见第 5 节。

## 3. 请求与崩溃恢复

- 新 client 自动生成 `operation_id` 和请求截止时间；最近的 ID 在 `Robot.last_operation_id` 中，`Robot.operation_status(id)` 查询 `/operations/<id>`。
- 相同 ID 已被接收后，再提交会返回 409 并提供查询位置，不会再次执行。状态可以是 admitted、completed、error、interrupted；超时不意味着动作完全没有执行。
- 超时后先查询进度，不能自动换新 ID 重发相同动作。服务没有缓存完整视频响应供重取；completed 表示操作结束，其动作进度仍需看 `committed_rows` 和响应/状态记录。
- 过期请求在首次执行前返回 408。服务在控制步边界检查期限和断连；客户端读取时限至少覆盖服务预算加 120 秒余量。原生调用不能被安全地在线抢占，另有服务拥有的硬 watchdog；逾期未完成调用被归为基础设施故障。
- journal 保存动作及实际 tick 数，在调用 checkpoint 前同步落盘；恢复以最后完整 checkpoint 为准。原生推进与记录提交之间仍存在不确定窗口；approximate resume 不是物理 exactly-once。
- 新 TopoGym 服务恢复需要对应的 tick journal。不能将旧 run 的目录直接交给新版本恢复；运行身份和预检必须一致。

## 4. 评分与录像

正常评分保持两遍：privileged 两次 replay，standard live 加一个独立进程 replay；最后一遍同时录像。

privileged 先提交 `verdict.json`，其中包括数值 reward、每次 replay 的结果、输入哈希和提交 ID，再关闭视频。父级 verifier 脚本可从它恢复 `reward.json/txt`。standard 的 `replay.verdict.json` 在媒体收尾前落盘，finalize 读取该文件，不再只依赖回放进程的末尾 stdout。

Harbor reward 保持数值字段。privileged 的 `submitted_actions` 表示提交行数，`n_actions` / `sim_steps` 表示最后一次评分实际执行量；完整各次结果在权威 verdict 中。媒体故障不改写已完成的评分；评分结果还未提交就退出的进程不能获得成功成绩。

正式 Harbor 录像使用当前 `topogym.recording.RecordingSession`，保持多相机合成画面；reset 后采首帧，最后 PNG 对应真实末态。采样按模拟时间进行，不再用 `round(control_hz / fps)` 当作媒体时钟。`render_video` 的相机与布局参数继续生效，旧 `every` 不再覆盖 fps 对应的时间轴。

输出包括 MP4、末帧 PNG、`*.frame_map.jsonl` 和 `*.recording_manifest.json`，可在收集后的目录独立核对文件和哈希；完成状态前执行完整解码并检查帧数。帧索引记录源物理时间与呈现时间，末态可能需要一帧额外呈现填充；不能将 MP4 容器的总时长直接当作物理时间。

当前仓库的公开录制接口是 `RecordingSession`；旧文档中的 `prepare/session/validate/archive` 函数不是当前可调用接口。任务不新增 writer 或独立编码循环。

## 5. 显式子步判据版本

`SimulatorConfig.terminal_contract_version` 默认为 1，保持原有 tick 末接触判据。版本 2 是待完整资格验证的可选刚体合同，仅允许 Coil、Keyhole、Hedgehog、Horseshoe、Claws 的配置：保存各 solver substep 的 contacts 与当时抓持状态，以原有 1 mm / 2 mm 阈值判定，缺少完整覆盖时明确失败。

IPC/FEM 不能选用该版本，也不能把未采集的事件解释为“没有违规”。真实四子步采集通过，不等于所有任务的短暂违规接触已验证；历史成绩和默认判据不追溯改变。

## 6. 交付与版本

不完整 Blanket 准备保留原目录，使用编号 attempt 重试，最多三个 attempt；完整清单、负载哈希及可读权限通过后才发布准备指针。耗尽次数会明确报告，不删除原始证据。后续实例构建和预检继续检查实际物理兼容性。

local 容器创建与清理共同使用 workspace、run_id、owner 和 role；删除前 inspect 复核。旧的无归属标签容器不被宽泛清理。新版本预检身份为 5。

tooling v4、v3 和历史无版本包按冻结清单验证，v5 按当前模板验证。共享协议的本地修改记录在 `ci_checks/rcb_vendor.json` 的 adapted / local_adaptations 中，保留上游 blob 身份，不伪装成上游原样文件。
