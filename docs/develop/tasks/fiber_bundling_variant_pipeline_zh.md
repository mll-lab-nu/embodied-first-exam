# 光纤收束：变体生成与 seed 接入检查

2026-09-19。本次只检查和开发实例生成，不生成数据集、H5 或新的机器人执行录像。

## 家族的实际含义

当前的 `sparse / standard / dense` 是线数密度家族，并不是三种明显不同的 IK 解法。它们符合参数随机化的设计：共享固定终端、被动细线、闭环和只抓粗护套的规则，变化线数及环内半径。

用户于 2026-09-19 确认本任务不要求 IK 的本质区别，正式采用上述密度家族定义。家族内继续通过线数和环半径生成变体；三种不同动作机制不再是验收条件或待开发项。实例自身的 IK 可达、禁碰、物理稳定性与完整穿环检查仍然保留。

重新检查三个 R=13.5 mm 代表的实际机器人指令与接触整理记录：

| 代表 | 整理事件数 | 轴向翻转整理 | 完整仿真时长 |
| --- | ---: | --- | ---: |
| 稀疏 4 芯 | 6 | 同一侧转腕 −70°，1 次 | 114.614 s |
| 标准 8 芯 | 11 | 同一侧转腕 −70°，1 次 | 174.904 s |
| 密集 16 芯 | 15 | 同一侧转腕约 −66° / −70°，2 次 | 235.094 s |

三者都使用 `whole_bundle_greedy_hybrid_IK`。可以看到线数、整理次数与用时不同，但主要仍是相同的接触按压、转腕、回正、送入动作。**这些证据不支持把它们标为三种动作机制明显不同的 IK 家族。** 不能靠增加无必要动作或随机扰动关节角来制造家族标签。

任务卡记录 `distinct_motion_families_required: false`，实例继续使用 `family_semantics: density_only_not_motion_family`。原审查中的 `distinct_motion_families_verified: false` 保留为事实记录，不再表示验收缺口。此次确认不改变生成参数、seed 映射或已有实例身份。

## 已实现的生成接口

任务卡登记了 [generation.py](../../../topogym/tasks/fiber_bundling/generation.py) 的三个入口：

```python
from topogym.tasks.fiber_bundling.generation import (
    build_episode, save_instance, load_instance,
)

# 返回完整配置和共享的 EpisodeSpec，不写磁盘，也不启动物理或录制。
cfg, spec = build_episode(42, family_id="standard", mode="parameterized")

# 生成供现有 runner 使用的独立实例包。
save_instance("runs/fiber_instance_42", 42, family_id="standard")

# 加载已保存的具体实例；校验文件哈希，绝不重新抽样。
cfg, spec = load_instance("runs/fiber_instance_42")
```

两种模式共用实例契约：

- `fixed`：选择预先定义的 4 / 8 / 16 芯代表，孔径固定 R=13.5 mm、线形 seed 固定 7。不同请求 seed 可以选中同一个形状，不会重新随机设计它；几何与配置身份相同，episode 请求身份不同。
- `parameterized`：在线数家族范围（4–6、7–10、11–16）内选线数，独立采样 R∈[12.8,15.0] mm。保持细线尺寸、材料、初始曲线生成规则、场景 pose 和配色不变。未加入未经验证的位置、朝向或外观随机域。

默认 family 使用 `seed % 3`，也可以显式指定。继续使用共享 `VariantRng` 的具名独立随机流，版本仍为 1，旧 `sample_parameters(seed, family)` 的映射不变。新增参数轴不会消耗其他轴的随机序列。拒绝重试使用具名 `retry`，固定请求 family，有次数上限，并保存每次拒绝的参数、原因和最终接受编号；输入错误直接拒绝，不偷偷换 family。

命令行示例，输出必须选新的目录：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.fiber_bundling.generation \
  --seed 42 --family standard --mode parameterized \
  --output runs/environment-solvability/fiber_bundling/generated_seed42
```

输出包括完整 `config.yaml`、共享 `EpisodeSpec`、资产、生成规则／来源代码快照、依赖版本、文件 SHA-256 和验证状态。身份包含生成版本、展开配置与来源哈希；存储路径不参与场景身份。`load_instance` 支持目录搬移和完整性核对。文件丢失或被修改会拒绝加载。

场景/控制器可直接消费返回的 `cfg`；现有 `variant_demo` 和 `variant_trial` 使用的 `load_run_config` 已接入实例包校验，因此不是仅供不同 demo 使用的另一套随机函数。后续 pipeline 可以从任务卡加载 `episode_factory / instance_writer / instance_loader`，得到同一份已解析实例，再分别接执行器、录制器或数据 writer。共享 RNG 与 EpisodeSpec 无需修改。

公共 `build_variant_episode` 依赖任务的 `variation:` 声明，当前旧 preview YAML 仍未声明该块，直接调用它仍不会自动生成这些实例。**本任务应使用任务卡登记的 factory**，避免 seed 只改变 ID、配置却不变。此次没有修改其他任务的公共入口。

## 验证与资格边界

[审查报告](../../../runs/demo_metadata/fiber_bundling/2026-09-19_variant_generation_audit/report.json) 保存来源哈希和三个代表的运动统计。`sample_summary.json` 是生成器审查参数记录，不是机器人训练数据。

- 300 个 seed：密度三类各 100 个，300 个不同参数实例，初态几何检查全部通过，均无需重试。
- 13 种线数 × 最小／中间／最大环半径：39 个组合全部通过根部间距、线间分离、护套间隙与初始环距检查。
- 4 个进程生成后，抽取 5 个 seed 逆序单进程重建，配置和实例身份一致。
- 固定与参数模式各 3 个实例实际导出资产，并通过实例重载与现有 runner 的配置加载入口。
- 另外将 3 个随机实例交给现有 Genesis 物理加载器，各做 0.2 秒无载静置：3/3 通过，初态漂移、接触穿透及速度均为 0。该短时检查不包含机器人操作、轻载或完整路径稳定性。
- 相同固定模板、不同 seed 的网格／碰撞资产字节相同；报告中的请求 seed 不同，所以报告及其哈希清单按预期不同。相同 seed 重新生成时，所有资产文件字节均一致。初次审查误把来源报告差异当作几何差异，该原始报告保留为 `initial_audit_report.json`，修正解释记录在最终报告。
- 15 项单元／回归检查通过，覆盖原 seed 黄金值、独立参数轴、固定模板选择、失败重试、非法输入、输出不覆盖、目录搬移、资产篡改拒绝和任务卡协议。

每个新实例明确记录 `geometry=passed`，`kinematics / loading_stability / full_physics / timestep_convergence=not_run`，`dataset_ready=false`。初态可构造不等于机器人可达或完整物理穿环成功。未来执行器需要对当前实例运行静置/轻载、连续控制、细线禁碰、完整穿环与时间步对照，并绑定具体配置和资产身份，才可升级验收状态。任何尺寸或 pose 改动都不能直接继承旧 demo 的证据。

## 现有基础视频

以下仍是 `2026-09-18_standard_08_r13p5mm_clean_v1` 基础实例的 177 秒无 UI 录像，由同一次完整物理轨迹重渲染；本轮没有新增随机实例录像。这些视频不能为上述随机参数域背书。

- [全景 MP4](../../../demos/fiber_bundling/agentview/2026-09-18_standard_08_r13p5mm_clean_v1_agentview.mp4)
- [前侧近景 MP4](../../../demos/fiber_bundling/front_oblique/2026-09-18_standard_08_r13p5mm_clean_v1_front_oblique.mp4)
- [腕部 MP4](../../../demos/fiber_bundling/wrist/2026-09-18_standard_08_r13p5mm_clean_v1_wrist.mp4)
