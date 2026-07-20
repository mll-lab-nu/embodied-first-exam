# `topogym/core` — 核心小工具

跨模块共享的最小公共对象，不含任何任务逻辑。

| 文件 | 提供什么 | 简单说明 |
| --- | --- | --- |
| `config.py` | `load_topogym_configs` / `add_common_config_arg` / `DEFAULT_COMMON_CONFIG` | 把 `configs/` 下的 `common` / `env` / `robot_control` / `task` 四段 YAML 读进来，合并成一棵 OmegaConf 配置树，供 prototype CLI 统一使用 |
| `manifest.py` | `EntityManifest` | 一个"名字 → Genesis entity 句柄"的登记表（`add` / `get` / `as_dict`）。`world` 在搭场景时把机器人、道具、相机注册进去，其它模块（`robot`、`primitives`、`tasks`）都通过名字来取用，不用互相传对象引用 |

**不负责**：具体任务该怎么随机化、成功判定、机器人怎么动——这些分别属于 `generation`、`tasks`、`robot`/`primitives`。
