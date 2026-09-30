# VLA 零样本评测

TopoGym 上评测开源 VLA 官方 checkpoint（不微调）。设计与计划见 [`docs/IMPL_PLAN.md`](docs/IMPL_PLAN.md)。

两个进程、两个 Python 环境，本机 TCP 一对一连接：评测进程（TopoGym 环境）驱动 reset / step / 录像 / 打分；模型进程（`vla/.envs/<model>`）只回答"观测 → 动作块"。

| 目录 | 运行环境 | 内容 |
|---|---|---|
| `protocol.py` | 两侧 | `PolicySpec` / `Observation` / `ActionChunk` 与编解码（标准库 + numpy） |
| `gym/` | TopoGym | `Adapter`、`VLAAgent`、`LocalClient` |
| `models/` | 模型环境 | `BaseVLA`、`HoldVLA` |
| `tests/` | TopoGym | 不需要 GPU |

## 测试

```bash
.venv-gs121-nyx/bin/python -m pytest vla/tests -q
```
