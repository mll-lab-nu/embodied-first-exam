# 统一 limited / unlimited 任务修订报告

本轮只整理、配置检查及小规模无模型 smoke；没有运行模型评测。历史结果保持原版本身份。

## 实际协议

- Unlimited：privileged state，同实例任意 reset、探索；无单轨迹/累计步数、reset、token 或模型调用配额；agent 3600 秒。用户最新要求覆盖引用文档中“保留原生 horizon”条款。MetaWorld 的时长截断关闭，原生成功谓词和冻结物理状态不变。
- Limited：RGB、机器人自身状态及相机标定；单连续 episode，无 reset；四方法接口，私有 sim 完整记录；保留原任务 episode 上限（MetaWorld 500、VLABench 4000、RoboCasa 3000，旧导航1200 controls）。其中 VLABench/RoboCasa 数字是仓库轨迹协议上限，不宣称都是上游原生 horizon。
- 仿真和 agent 安装就绪后计时；60分钟独立 watchdog 停止 main，停止之后封存/收集/双重放单独计时。Unlimited 首个 Session 在可信 setup 阶段预初始化；随后 reset/新增 Session 计入探索时间。
- Limited online + 两次 fresh replay 必须成功且精确状态一致。超时不能被重放成功覆盖。Unlimited 只评分最后提交的轨迹；同容器 privileged runtime 的计数不具有 sidecar 级抗篡改性。

## 覆盖

| Benchmark | 任务族 | 实例 ID | Unlimited 已配置 | Limited 已配置 | 未就绪 U/L |
|---|---:|---:|---:|---:|---:|
| vlabench | 96 | 104 | 91 | 91 | 13/13 |
| metaworldplus | 50 | 70 | 70 | 69 | 0/1 |
| robocasa | 30 | 30 | 30 | 30 | 0/0 |
| robocasa365 | 256 | 263 | 263 | 263 | 0/0 |
| robocasa-gr1 | 24 | 33 | 33 | 33 | 0/0 |

VLABench 保留96个原生任务ID与8个历史视觉ID；91个有冻结实例，13个缺少冻结实例，两模式均保留不可运行记录。8组视觉/privileged别名对应同一物理实例，清单显式标注，不能将它们当作独立随机样本。MetaWorld limited 中原先不可观察目标的实例继续标为未就绪，不增加隐藏坐标提示。

## 验证

[配置检查](config-check.json)逐项检查 task ID、冻结实例字节、权限/网络配置、实际代码中的预算、解析及目录指纹。
[长轨迹 smoke](unbounded-metaworld/result.json)执行501个原生controls越过旧500 horizon，并在两个新进程重放，在线/重放精确一致。
[全量 CI 日志](ci-final.log)、[四项执行边界测试](unit-tests.log)、[源码与工具指纹](provenance.json)、[Harbor oracle 退出码语义审计](oracle-exit-code-audit.json)。
实际 smoke 证据按当前任务 checksum 关联；旧版本通过不自动算新版通过。其余实例只声明配置检查完成，未全量重新仿真。

| Benchmark | Mode | Oracle | Nop | 当前版本证据 |
|---|---|---|---|---|
| vlabench | unlimited | True | True | `robot-coding-bench/vlabench-select-fruit-unlimited60min-v3-i00`（suite 内 smoke_evidence） |
| vlabench | limited | True | True | `robot-coding-bench/vlabench-select-fruit-limited60min-v3-i00`（suite 内 smoke_evidence） |
| metaworldplus | unlimited | True | True | `robot-coding-bench/metaworldplus-push-unlimited60min-v3-i00`（suite 内 smoke_evidence） |
| metaworldplus | limited | True | True | `robot-coding-bench/metaworldplus-push-limited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa | unlimited | True | True | `robot-coding-bench/robocasa-close-drawer-unlimited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa | limited | True | True | `robot-coding-bench/robocasa-close-drawer-limited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa | unlimited | True | True | `robot-coding-bench/robocasa-kitchen-navigation-unlimited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa365 | unlimited | True | True | `robot-coding-bench/robocasa365-turn-on-stove-unlimited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa365 | limited | True | True | `robot-coding-bench/robocasa365-turn-on-stove-limited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa-gr1 | unlimited | True | True | `robot-coding-bench/robocasa-gr1-pn-p-can-to-drawer-close-unlimited60min-v3-i00`（suite 内 smoke_evidence） |
| robocasa-gr1 | limited | True | True | `robot-coding-bench/robocasa-gr1-pn-p-can-to-drawer-close-limited60min-v3-i00`（suite 内 smoke_evidence） |

初期 smoke 的 nft 语法错误、目录迁移期间的路径故障以及 warm Session 与旧 oracle 的兼容故障均保留在各自 jobs 目录；修复后使用新 smoke 目录，不删除失败证据。

## 目录与复现

当前任务唯一入口为 `limited_tasks/<benchmark>/`、`unlimited_tasks/<benchmark>/`；原版本位于 `archive/task_versions/pre-unified-20260929/`。`tasks/`仅剩此次范围以外的任务。
清单：[逐实例 CSV](instances.csv)、[统一 registry](../../../suites/two-modes.json)、[迁移映射](../../../suites/task-path-aliases.json)。历史 jobs、视频及离线网页未重新评分/重命名。
运行命令见 [统一使用说明](../../TWO_MODES.md)。旧模型运行器仅保留历史 report 入口；新实验使用统一 runner。

## 未就绪记录

以下记录保留在覆盖分母；本轮不重采样、不补造冻结实例。完整 source、seed 与哈希见统一 registry。

| 实例 | 受影响模式 | 原因 |
|---|---|---|
| `metaworldplus-sweep-privileged-i00` | limited | 原始目标在允许的视觉观测中不可确定；不添加隐藏目标坐标 |
| `vlabench-cluster-dessert-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-find-fruit-to-make-juice-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-insert-power-cord-to-make-juice-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-plug-cord-and-heat-food-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-put-box-on-painting-semantic-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-replace-wilted-flower-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-select-billiards-semantic-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-select-drink-spatial-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-select-painting-by-style-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-set-dining-chopstick-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-set-dining-chopstick-left-hand-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-simple-cuestick-use-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
| `vlabench-weight-qa-i00` | unlimited, limited | 缺少已冻结的实例文件，不能保持原始初态进行可信重放 |
