# 当前工具

| 工具 | 用途 |
| --- | --- |
| `audit_task_assets.py` | 当前十项任务参数卡与资产核对 |
| `calibrate_robotiq_model.py` | 共用 Robotiq 资产与标定工具 |
| `prepare_nyx_studio.py` | 下载并核验当前渲染使用的 HDRI/纹理 |
| `export_h5_lerobot.py` | 通用 HDF5 → LeRobot 转换，需 OpenPI/LeRobot 环境 |
| `register_openpi_config.py` | 按任务名注册 OpenPI 训练配置；只在显式执行时修改指定 checkout |

Python 模块工具在仓库根目录用 `.venv-gs121-nyx/bin/python -m scripts.<工具名>` 启动。
OpenPI 工具使用 `env_setup_vla_openpi.sh` 准备的独立环境，是否支持具体新任务取决于其采集结果与数据契约。
一次性文档配图脚本和 Nyx 官方示例包装脚本已清理；当前渲染检查入口为
`demos.environment_bootstrap.presentation_preview`。
