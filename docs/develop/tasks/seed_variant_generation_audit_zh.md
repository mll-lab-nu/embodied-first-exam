# 十项任务的 seed 变体生成审查

检查日期：2026-09-17。范围为当前 `topogym/tasks/catalog.py` 的十项任务，以及对应配置、实验脚本和运行证据；不包含 legacy 任务。

## 结论

尚无覆盖十项任务的统一完整随机生成模块。现有能力分为：Keyhole 的受限范围端到端批次采样；Horseshoe 的有连续几何证书采样；Fiber 的初态几何采样；其余任务的固定代表、参数化生成或规划。Lock Picking 另有旧版角度随机化，但没有接入新 family × S/M/L 空间。

本审查区分三个层次：参数由整数 seed 决定；参数能生成可用资产；生成实例连同对应解经过验证。物体几何路径有解、机器人 IK 可达、实际物理执行通过分别记录。代表 demo 通过，不能替代其他随机实例的验证。

| 任务 | 已有模块与能力 | 尚缺什么 |
| --- | --- | --- |
| cast_keyhole | [family_pipeline.py](../../../topogym/tasks/cast_keyhole/family_pipeline.py) 支持 `sample --seed --count --vary-ik`，采样动作与外观，反推几何、检查 IK/几何、双时间步物理执行与审计、拒绝失败并保存结果 | 尚未接入统一逐实例 API；family 按配额轮换，默认 `count=1` 总是从 F1 开始；默认关闭 `vary_ik`；需要现有源资产与运动证据 |
| horseshoe_ring | [shape_sampler.py](../../../topogym/tasks/horseshoe_ring/shape_sampler.py) 按批次 seed 采样形状、椭圆比例、链尺寸，通过联合收缩保留连续几何路径证书 | 不含机器人 IK、场景障碍或动力学验证；[family_space.py](../../../topogym/tasks/horseshoe_ring/family_space.py) 的新九宫格采样器仍关闭，六个新形状组合尚未配对机器人运动 |
| fiber_bundling | [variants.py](../../../topogym/tasks/fiber_bundling/variants.py) 按 seed 选择密度 family、线数与环半径，生成资产并检查初态几何；底层线形 seed 固定为 7 | 有独立 [variant_demo.py](../../../topogym/tasks/fiber_bundling/variant_demo.py) 执行流程，但随机入口未串成自动求解、物理验收、失败重采样的闭环；生成报告明确不承诺完整穿环有解 |
| lock_picking | [family_space.py](../../../topogym/tasks/lock_picking/family_space.py) 生成固定九代表与参数角点；旧 [_staged_lock_geometry.py](../../../topogym/tasks/lock_picking/_staged_lock_geometry.py) 对部分模式按 seed 扰动初始角度 | 新 1/2/3 回退 family × S/M/L 没有整数 seed 采样入口；物理数据生成开关为 false；当前 oracle 仍针对两次必要回退。保持三齿、盘距至少 150 mm 的约束 |
| cast_coil | [inverse_design.py](../../../topogym/tasks/cast_coil/inverse_design.py) 和实验脚本支持参数化动作与反推结构；有九个可见几何/IK 代表 | [family 空间文档](cast_coil_family_space_zh.md) 明确通用随机采样器及连续域接受率未完成；固定代表不等于随机实例模块 |
| hedgehog_in_cage | [family_motion.py](../../../topogym/tasks/hedgehog_in_cage/family_motion.py)、[family_geometry.py](../../../topogym/tasks/hedgehog_in_cage/family_geometry.py) 提供参数化运动与结构，已有 A/B/C 物理代表 | [规格](../../../configs/task_variants/hedgehog_in_cage/family_space_v2.json) 明确是不可执行的随机生成规划；九种外观和 seed 采样闭环未完成 |
| interlocked_claws | [family_space.py](../../../topogym/tasks/interlocked_claws/family_space.py) 审查与展示设计规划 | 规划中 `generator_implemented=false`、`random_generation_enabled=false`；新 family 几何/运动合成与验证尚未落地 |
| rope_threading | [geometry.py](../../../topogym/tasks/rope_threading/geometry.py) 支持参数化布局与资产生成 | 未发现当前任务的 seed → family/参数 → 对应解验证的生成入口 |
| knot_untying | [geometry.py](../../../topogym/tasks/knot_untying/geometry.py) 提供参数化绳结；物理 probe 有 seed | probe seed 用于仿真初始化，不是绳结结构随机生成器；没有 family 采样与可解性筛选闭环 |
| buzz_wire_3d | [probe.py](../../../topogym/tasks/buzz_wire_3d/probe.py) 支持固定/参数化探针场景 | 未发现完整路线与场景的 seed 变体生成、机器人求解与拒绝流程 |

## 共享框架的实际接入情况

- [variant_rng.py](../../../topogym/generation/variant_rng.py) 有具名随机流，Fiber 已使用。
- [layout_randomization.py](../../../topogym/generation/layout_randomization.py) 和 [variant_episode.py](../../../topogym/generation/variant_episode.py) 有声明式采样与 EpisodeSpec；当前 `configs/` 未发现 `variation:` 声明，当前任务和 demo 未发现这套入口的实际调用。没有声明时，`randomize_task_cfg` 原样返回配置。
- [catalog.py](../../../topogym/tasks/catalog.py) 的 `baseline_manifest(task_id, seed)` 只记录 seed，明确返回 `sampling: fixed_baseline`，不会随机化任务。
- 各模块对 seed 的约定不同：Keyhole/Horseshoe 是批次随机流；Fiber 是逐实例 seed；某些 IK 函数中的 seed 则是参考关节状态或已解运动，不能作为随机采样能力的证据。

## 本次验证

1. 运行现有 `tests.check_fiber_variants`、`tests.check_horseshoe_shape_neighborhood`、`tests.check_task_baseline_catalog`：共 14 项，13 项通过，1 项错误。错误来自 Fiber 任务卡使用 `geometry_candidate`，catalog 校验器只允许 `candidate`，报 `Unqualified axes must remain candidate`。审查未修改生成逻辑或任务卡。
2. 逐个检查 catalog：其他九项的 seed 0/1 都返回相同任务卡；Fiber 被上述校验错误阻挡。
3. Fiber 的 seed 42/43/44 分别得到 sparse/standard/dense、4/7/16 根线；参数可复现，三个实例的初态几何检查通过。本次没有执行完整物理穿环。
4. Horseshoe 实际生成 seed 42 两次、seed 43 一次（每批一个样本）。同 seed 输出报告及几何/轨迹哈希一致；不同 seed 几何不同；三个样本均通过几何证书。没有运行机器人或动力学。
5. Keyhole 的外观参数同 seed 可复现、不同 seed 改变。核对[既有随机批次](../../../runs/environment-solvability/cast_keyhole/families_random_validation_v1/samples.json)：seed 20260917、`vary_ik=true`，三个 family 各接受一个，共拒绝一次。三个接受实例的 qualification、几何、运动、证书、两档时间步报告/审计/轨迹文件哈希全部匹配。此次未重新运行 Keyhole 完整物理流水线，也未证明跨机器物理结果逐位一致。其验收使用辅助抓持，不等于纯摩擦抓取验证。

Keyhole 当前可用的批次命令如下；输出必须使用新的目录：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.cast_keyhole.family_pipeline sample \
  --root runs/environment-solvability/cast_keyhole/new_seed_batch \
  --seed 42 --count 3 --vary-ik
```

## 下一步建议

统一 `task_id + seed + generator_version + evidence_level` 的逐实例入口；每项任务显式登记可用 family、条件参数范围和验证能力。输出保存具体参数、资产/解哈希、父证据、拒绝原因及实际验收等级。先接入三个已有采样器，再补齐 Lock Picking、Coil、Hedgehog 的 family 采样与对应解验证。不要把任意范围内的参数组合、固定九代表或单独一个仿真 seed 当成完整可解变体生成机制。

## 补充：旧版随机生成模块在当前版本是否可用

同日按用户追问检查 legacy。结论：**通用 seed 生成核心仍在主线，实测可用；旧任务配置和旧索引入口不能直接运行。** 因此无需重新实现一套 RNG；当前任务需要补的是任务参数声明、派生/验证函数，以及资产与解生成的接入。

原有链路为 `VariantRng → randomize_task_cfg → build_variant_episode → EpisodeSpec`。前三个模块仍在当前 `topogym/generation/`，不是只能在 legacy 找到的旧实现。原先按 `(task_id, split, index)` 取实例的 [episode_index.py](../../../legacy/topogym/generation/episode_index.py) 则已归档，注册表仅包含旧十三项任务。

本次使用当前 `.venv-gs121-nyx` 与主线模块，未修改生产代码、未将 legacy 加入导入路径，也未恢复旧任务。读取归档测试的独立 RNG、directive、braid 检查函数执行，避免执行其旧路径引导；另外执行了当前 `build_variant_episode` 的独立集成样例。

| 检查 | 结果 |
| --- | --- |
| 旧版 RNG 黄金值 | 通过：版本 1，seed 0 / `golden` 的首值仍为 `0.062484451052847945` |
| 同 seed、具名随机流、调用顺序与 retry 隔离 | 归档核心检查通过 |
| directive 解析、派生后验证、失败重采样 | 归档核心检查通过；无效声明按预期报错 |
| braid 的 seed 与具名随机流一致性 | 归档核心检查通过 |
| 当前 EpisodeSpec 最小生成 | 30 个 seed 全部通过；同 seed 重复一致、不同 seed 参数不同、原配置未改动、采样和派生参数完整记录、指令和 goal_id 一致 |
| choice / uniform / distinct_choice / spaced_pair | 集成样例通过；重排参数轴后 seed 7 的 EpisodeSpec 不变 |
| 拒绝次数耗尽 | 不可行样例在 3 次候选均失败后抛出 RuntimeError，没有返回未验证候选 |
| 旧十三项任务配置直接传给当前采样器 | 13/13 在加载任务派生/验证函数时失败：`No module named 'topogym.tasks_legacy'` |
| 旧 episode 索引 | 当前 `topogym.generation.episode_index` 无法导入；当前与 legacy 均没有 `configs/episode_splits/` 目录 |

完整结果与 30 份生成参数保存在 [report.json](../../../runs/environment-solvability/catalog/legacy_seed_audit_20260917/report.json) 和 [sample_specs.json](../../../runs/environment-solvability/catalog/legacy_seed_audit_20260917/sample_specs.json)。上述测试验证的是参数生成核心与实例描述，不是新任务资产合成、IK 或物理成功率。核心黄金值未变也不代表旧任务场景全部可复现，因为旧任务函数、配置和环境依赖已经与主线分离。

当前推荐复用 `build_variant_episode(cfg, task_id, seed)` 作为参数与实例描述入口：任务声明 family/外观轴，派生函数计算联动尺寸，验证函数拒绝不满足约束的候选。各任务现有的 IK 变体、结构反推和物理验收仍需在这一层之后接入；新任务没有 `variation:` 声明时，调用这个入口不会自动产生随机场景。
