# TopoGym Dev-Docs 索引

本目录按**工程 focus** 分类，每个子目录有自己的 `README.md` 细目。另有两组按**代码结构**（另一条轴，非 focus）组织的参考文档：`modules/`（逐代码模块说明）与 `classes_map/`（类图），本次归类未动。

| 目录 | Focus | 内容 |
| --- | --- | --- |
| [`framework/`](framework/) | 基础框架搭建 | 顶层架构、模块连接图、配置速查、Genesis 坐标系、tabletop 基线、MDP 状态/终态约定、环境依赖 |
| [`tasks/`](tasks/) | 任务设计与落地计划 | docx 20 个任务的类别归属、环境需求逐项清单、建模能力盘点、成本分档与实施顺序 |
| [`physics/`](physics/) | 物理模拟与交互 | 刚体/PBD 机械臂物理交互、仿真稳定性；大任务族 `cable_routing/` `untangle/` `peeling/` 各有子目录 |
| [`visual/`](visual/) | 观感 / 真实性 | photorealism 工作流、物理真实性准则与 metrics、stacked_plate 观感升级 |
| [`data_pipeline/`](data_pipeline/) | 数据生成 pipeline | 稳定环境生成系统、逐任务前置件核对、RoboMME benchmark 产物分析与落地路线图 |
| [`il_adaptation/`](il_adaptation/) | IL 适配性 | collision-based IL demo 合约、swap→π0.5 (OpenPI) 数据加载冒烟 |
| [`meta/`](meta/) | 过程 / review | 外部 reviewer 反馈 → 落地行动计划 |
| [`modules/`](modules/) | （代码结构参考） | 逐代码模块说明；入口 `modules/overall_module_dict_zh.md` |
| [`classes_map/`](classes_map/) | （代码结构参考） | 类图 |

> 归类只挪目录、**文件名不变**：按裸文件名（如 `cable_routing_devlog_zh.md`）grep / 跳转仍然有效；全路径引用（`docs/develop/X.md`）已更新到新子目录。
