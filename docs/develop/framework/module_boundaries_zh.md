# 模块职责边界（分层规矩）

> 日期：2026-07-27
> 来源：兑现 [`../data_pipeline/stable_il_generation_system_devlog_zh.md`](../data_pipeline/stable_il_generation_system_devlog_zh.md) §3.2 里
> 「`verification` 暂时放在各 `tasks/*.py` 旁边，等接口稳定后再迁移」那句话。接口已稳定，本文是迁移后的规矩。

这份文档解决一个具体问题：**「算不算成功」以前在仓里有三套答案**——5 个任务在 `tasks/` 判、
untangle 在 `envs/` 判、cable_routing 没人判（散在 demo）。新写一个任务时没有唯一正确答案。
下面这张表就是唯一答案。

---

## 1. 五层职责

| 层 | 一句话职责 | 放什么 | **禁止** |
|---|---|---|---|
| `topogym/tasks/` | **这局长什么样** —— 几何、资产、把 layout 搭成 Genesis 场景 | `XxxLayout` / `XxxScene` / `XxxSceneBuilder` | 任何「到没到某状态」的判断 |
| `topogym/verification/` | **判断方** —— 读场景状态回答「到没到某个任务节点」 | `XxxPuzzleState` + `XxxPuzzleEvaluator`；四种 success 的组装 | 定义 reward / action space；控制流程 |
| `topogym/supervision/` | **跑起来之后的观察** —— 稳定性监控、soft abort、HUD/UI 文本、运行指标 | `*_monitor` / metrics / HUD 行构造 | 定义终态语义（要问 verification） |
| `topogym/envs/` | **MDP 化** —— S / A / r / γ / Gt 的**设定** | obs 编码、action 编解码、reward 权重与计算、`max_episode_steps` 截断 | **自己算终态** |
| `topogym/planning/` | **oracle / 规划** | `*_planner` / `PlannedSubgoal` / `WaypointPlan` | 判断成功 |

其余模块的边界不变，简述：`world/` 通用物理世界（桌面/绳子/材质/灯光）；`generation/` seed→spec；
`primitives/` 可复用动作原语；`robot/` 控制器与机器人专属 helper；`data/` 数据集读写；
`runtime/` episode 编排（蓝图 §3.5.4，尚未接线）；`utils/` 真·跨领域杂项（录制、HUD 绘制）。

---

## 2. 终态归谁（本次重构的关键一条）

终态的**语义**属于 S，由 `envs/` 声明；但 `envs/` **不是判断方**。落到代码里只允许这一种写法：

```python
# topogym/envs/<task>_mdp.py
state = self.verifier.classify(self.scene)   # verification 是判断方
terminated = state.is_terminal               # envs 只做 MDP 语义封装
```

也就是说：**「终态是什么意思」写在 envs 的文档和 obs/reward 设计里；「现在到没到」由 verification 回答。**

`topogym/envs/swap_mdp.py` 是参考实现：它的 `_is_success()` / `_topology_state()` 只是转调
verifier，自己不算任何拓扑。

反例（重构前的 `envs/untangle_mdp.py`）：它同时是 MDP、状态定义和判断方，自己实现了线段相交
（`_segments_cross` / `_orient` / `_point_on_segment`）。这类几何/拓扑判定必须住在 `verification/`。

---

## 3. 四种 success 分别归谁

按蓝图 §F：

| success | 判断方 | 说明 |
|---|---|---|
| `task_success` | `verification/` | 拓扑或几何任务完成 —— 这是 benchmark 指标 |
| `physical_success` | `verification/` | 机械臂是否真实完成接触/夹持/释放 |
| `stability_success` | `supervision/` | 是否没有触发高风险物理状态 —— 用来**门住数据导出** |
| `recording_success` | `utils/recording.py` | viewer/video/观测导出是否完整 |

`export_ready` = 四者与，在 `verification/` 里组装。

把 `stability_success` 和 `task_success` 分开是有意的：前者决定「这条数据能不能进数据集」，
后者决定「这次任务算不算做成」。两者消费方不同——一条 episode 完全可以物理稳定但任务失败
（是合法的负样本），也可以任务成功但中途 PBD 抖了一下（不该进数据集）。

---

## 4. 文件命名

沿用蓝图 §3.4。注意 `tasks/` 是**唯一**按能力类别分子目录的层，其余层保持平铺
（理由见 [`task_taxonomy_zh.md`](task_taxonomy_zh.md) §1）：

```text
tasks/<category>/<task>.py             # Layout / Scene / SceneBuilder（category 见 task_taxonomy_zh.md）
verification/<task>_verifier.py        # PuzzleState / PuzzleEvaluator
supervision/<task>.py                  # 监控指标 + HUD 行
envs/<task>_mdp.py                     # Gym 环境
generation/<task>_generator.py         # seed -> EpisodeSpec
planning/<task>_planner.py             # plan / subgoal / waypoint
demos/<类别>/<task>_physical_<机构>_demo.py   # CLI 展示入口
```

---

## 5. 依赖方向（不允许反向）

```text
world  ──►  tasks  ──►  verification  ──►  envs
                 │            ▲
                 └──►  supervision ┘        planning ──► verification
```

具体规矩：

- `tasks/` **不 import** verification / supervision / envs / planning。
- `verification/` 可以 import `tasks/`（要读 Scene/Layout）和 `world/`，**不 import** envs / supervision。
- `supervision/` 可以 import verification / tasks / world / planning 的**公开** API。
- `envs/` 可以 import verification / tasks。
- **任何模块都不许 import 另一个模块的下划线私有符号。** 需要共享就提升为公开 API。

---

## 6. 新增一个任务时的清单

1. `tasks/<category>/<task>.py`：Layout / Scene / SceneBuilder —— 只造场景。放进哪个类别目录
   见 [`task_taxonomy_zh.md`](task_taxonomy_zh.md)；同步在 `topogym/core/taxonomy.py` 的
   `CATEGORIES` 里登记，用 `python topogym/core/taxonomy.py` 校验表与目录一致。
2. `verification/<task>_verifier.py`：`XxxPuzzleState`（含 `is_terminal` / `to_info`）+
   `XxxPuzzleEvaluator.classify(scene)`。
3. `configs/task_configs/<task>_topogym_tabletop_v1.yaml` + `configs/episode_splits/<task>.yaml`。
4. `generation/<task>_generator.py`：`build_<task>_episode_spec`。
5. `planning/<task>_planner.py`（若有 oracle）。
6. `supervision/<task>.py`（若有专属指标或 HUD 行）。
7. `envs/<task>_mdp.py`（若要 RL 面）—— 终态转调 verification。
8. `demos/<类别>/<task>_physical_<机构>_demo.py`。
9. 四个 bash 注册表：`stability_sweep.sh` / `verify_dataset_recording.sh` /
   `record_all_tasks.sh` / `collect_and_view.sh`。
10. 文档：`configs/README.md`、`configs/GEOMETRY_PARAMETERS_zh.md`、
    `docs/develop/modules/module_tasks.md`、`module_demos.md`。
