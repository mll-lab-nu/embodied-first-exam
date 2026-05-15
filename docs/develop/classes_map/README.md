# TopoGym Class Map：建议实施顺序

> 目标不是按“理论最底层”排序，而是按**最容易先定接口、最不容易把外部耦合一起拖进来**排序。

---

## 1. 第一优先级：`B_task.md`

`B_task` 适合作为第一个实施模块，原因有三点：

- 它是**纯逻辑层**，不直接依赖 Genesis、相机渲染、机器人控制、HF/VLM、rsl-rl。
- 它只消费 A 暴露的**只读场景契约**，因此可以先用伪造 scene snapshot 或 mock state 做单元测试。
- 它会反向约束后续模块最关键的数据协议：`initial_config` 的 schema、`topology_state` 的 schema、`info["reward_terms"]` 的结构、`max_episode_steps` 的来源。

如果先做 A/C/D/F，容易过早把“场景怎么摆”“相机怎么配”“动作空间长什么样”这些问题绑死；先做 B，则可以先把**任务语义**钉牢。

---

## 2. 推荐顺序

1. `B_task.md`
2. `A_world.md`
3. `D_observation.md`
4. `C_embodiment.md`
5. `F_runtime.md`
6. `G3_eval.md`
7. `G2_offline_data.md`
8. `E_policy.md`
9. `G1_online_rl.md`

这条顺序背后的原则：

- `B → A`：先定义任务状态、成功判定、初始配置 schema，再决定场景必须暴露哪些实体与 setter。
- `A → D/C`：先有稳定的 `SceneHandle` / `EntityManifest`，观测与控制才有可靠句柄。
- `D/C → F`：runtime 只是编排层，不应该倒逼底层接口长什么样。
- `F → G2/G3`：先跑通 rollout，再做数据采集和评测。
- `E/G1` 放后：policy 与训练器最容易因为前面接口不稳而反复返工。

---

## 3. 第一个 concrete slice

即使在 `B_task` 内，也不建议一开始就覆盖全部任务。首个 concrete task 建议选：

- `SwapTask`（对应 `order_swap_puzzle` 一类纯刚体任务）

原因：

- 不涉及绳子/DLO，避免把拓扑逻辑和可变形体建模耦在一起。
- `topology_state` 可以直接定义为置换或到目标置换的距离，reward shaping 清晰。
- 初始配置采样器也最简单，容易先验证 `TaskBase` 的抽象是否稳定。

---

## 4. 当前建议

本轮先把 `B_task` 的 class 图谱补到“可直接照着开工”的粒度：类依赖关系、MVP 子集、首个 concrete task 绑定方式。
