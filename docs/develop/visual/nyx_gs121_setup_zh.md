# Nyx 与 Genesis 1.2.1：固定环境与验证

2026-09-13 完成固定版本安装，2026-09-16 起默认使用 Nyx + 封闭实验室。
当前安装脚本为 `env_setup_gs121.sh`，约束文件为 `requirements/uv-topogym-gs121-nyx.txt`。

本机已实测组合：Python 3.11.15、Genesis 1.2.1、gs-nyx-plugin 0.1.4、gs-nyx 0.1.3、
NumPy 2.3.5、PyTorch 2.12.0+cu126；GPU 为 RTX 4090，驱动 570.153.02。
这是已有本机验证记录，不代表上游所有版本或所有 Nyx 功能的兼容承诺。

```bash
# 默认安装 Nyx 环境 .venv-gs121-nyx。
bash env_setup_gs121.sh

# 下载并核验项目使用的 HDRI/木纹资源；已有完整缓存时无需网络。
.venv-gs121-nyx/bin/python scripts/prepare_nyx_studio.py

# 项目场景的实际 GPU 渲染、腕部跟随、录像及 HDF5 RGB 检查。
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.presentation_preview

# 需要原光栅环境时显式选择。
INSTALL_NYX=0 bash env_setup_gs121.sh
```

插件与 Genesis、NumPy 的版本必须成套使用；安装器通过固定约束建立独立环境，
保留原 `.venv-gs121`。Nyx 的 sensor 应在 `gs.init()` 后由 Genesis 注册，避免提前导入求解器。
资产缓存在 `.external/nyx-assets/`，出处与许可保存在其中的 `CREDITS.txt`。

[当前渲染说明](default_nyx_lab_zh.md) 列出了后端限制与验证范围；
[共享场景报告](../../../runs/environment_bootstrap/default_presentation/report.json) 保存实际检查结果。
安装探索阶段的官方示例包装脚本、渲染图与安装日志已清理；
[原安装记录](../../../legacy/docs/develop/visual/nyx_gs121_setup_zh.md) 作为历史资料保留，旧命令不再维护。
