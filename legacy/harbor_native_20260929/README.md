# 归档：09-29 上午的“独立复现”Harbor 层

2026-09-29 下午归档。这是按 robot_coding_bench `dev/qineng@fa59c1a6` 的协议独立复现的第二版 Harbor 层，特点是“不复制对方源码”。

上午用 Docker 做过两种模式的 nop 验收，都跑通了，证据在 `runs/test_results/harbor_verifier_fix_20260929/`。随后与参考仓库逐文件对照，找到约 100 处接口和功能差异，覆盖以下各层：
- limited 客户端的文件名、异常类型、深度精度；
- `/spec` 字段；
- episode 何时结束；
- sim 生命周期与 `final.json`；
- unlimited 工具的方法集；
- 轨迹格式；
- 评分字段；
- 任务目录格式；
- CI 检查；
- 模型网关；
- 批量脚本。

用户因此决定：与模拟器无关的文件按字节复制参考仓库，并按参考仓库的目录结构从头重建。本目录保留原来的相对路径，只移动、不修改。

| 原路径 | 内容 |
| --- | --- |
| `topogym/benchmark/` | 导出器、HTTP 服务、客户端、Session、评分、重放、cube fixture |
| `scripts/check_benchmark_tasks.py`、`test_benchmark.py`、`setup_benchmark.sh`、`build_benchmark_image.sh` | 检查、GPU 冒烟测试、Harbor venv 安装、镜像构建 |
| `tests/benchmark/`、`tests/benchmark_host/` | 协议与导出测试 |
| `configs/benchmark/` | cube 实例配置 |
| `docker/Dockerfile.simulator` | 模拟器镜像，新的 `images/topogym/Dockerfile` 由它改写 |
| `requirements/benchmark-host.lock` | Harbor 主机侧依赖锁定 |

新实现：
- 任务在 `tasks/`；
- 基础镜像在 `images/topogym/`；
- 模型接入在 `harbor_agents/`；
- 检查在 `ci_checks/`；
- 用法见 `docs/rcb/README.md`。

重写 `rcb_topogym.py` 时参考了这里的深度、FK/IK、夹爪开口测量和相机标定接法，但没有从本目录导入任何东西。
