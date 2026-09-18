# 旧版只读存档

2026-09-16 按项目整理要求收录。这里保留旧版项目与已有成果，**不再维护运行入口、依赖兼容或旧测试**。
不将本目录加入 `PYTHONPATH`，不从当前模块导入此处实现。

| 目录 | 收录内容 |
| --- | --- |
| `topogym/tasks_legacy/` | 旧 connectivity、deformation、entangle、routing 任务 |
| `topogym/planning/`、`verification/` 等 | 对应旧规划器、判定器、监督器、回放和任务登记表 |
| `demos/`、`configs/`、`tests/`、`bash_scripts/` | 旧入口、参数、回归检查和批处理 |
| `docs/` | 旧架构、任务实现、开发记录和进度表 |
| `runs/` | 旧任务实验结果、配置快照与媒体证据 |
| `reports/weekly/` | 已交付周报及其媒体资源，原 `topogym_weekly_report/` |

除周报外，基本按原仓库相对路径收录。例如原 `topogym/tasks_legacy/connectivity/staged_lock.py`
现在位于 `legacy/topogym/tasks_legacy/connectivity/staged_lock.py`。
已有工作区修改一并保留；没有恢复整理前已经删除的文件。

源文件正文保持归档时的状态，历史文档和运行配置中的旧命令、导入路径、绝对资产路径可能已失效。
这些记录不构成可运行的发行版本。`snapshot` 类文件是本次改写公共入口前的快照，含义见清单。
一次性探索草稿、探针和原始调试日志已清理，不作为旧版实现继续收录。

当前仍使用的开锁执行、规划、证书和判定代码已迁入
[`topogym/tasks/lock_picking/`](../topogym/tasks/lock_picking/)，当前主线见 [根目录说明](../README.md)。

`runs/` 和 `reports/` 含大体积本地媒体，继续由 `.gitignore` 排除；旧版源代码、配置和文档可纳入版本控制。
具体路径、分类原因和清理前哈希见 [机器可读清单](../docs/maintenance/cleanup_20260916.json)。
