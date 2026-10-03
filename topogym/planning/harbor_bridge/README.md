# Harbor oracle bridge

共享入口是 `scripts/oracle_runners/harbor_oracle.py`，使用仓库的 Python 3.11+ 环境。
本模块负责冻结身份、动作转换、私有依赖打包和 Harbor oracle/nop 批量执行。
策略、IK、场景和原生成功判据仍由原任务提供；执行使用任务包原有的 `Session.step`。
所有运行代码随 `solution/` 上传，不进入公共 simulator / verifier 镜像。

当前已完成公共基础设施，以及 Keyhole very_easy / easier 的候选包接入检查。
候选包仍需完整 Harbor 物理回放验收；这不表示所有任务已经接通。
原任务包、原 oracle runner、既有证据和成功资格均保留。

当前实测范围按用户要求仅为 **easy / medium / hard**，不运行 very_easy / easier。
盘点与执行都可加 `--tiers easy medium hard`；执行入口会拒绝范围外任务，避免名称后缀误匹配。
简化档已有产物保留，但不纳入本轮三档验收。

## 支持的输入

| `--kind` | 输入 | privileged | standard |
| --- | --- | --- | --- |
| `existing` | 原 `solve.sh` 中 `run-oracle --code` 指向的脚本及私有依赖 | 支持 | 不支持 |
| `session` | `topogym.planning.*` 内的 `callback(session, output, **kwargs)` | 支持 | 不支持 |
| `public_trajectory` | 同一冻结实例的公开关节/夹爪宽度轨迹 | 支持 | 通过原 HTTP client 提交 |
| `native_trajectory` | 同一冻结实例的原生关节/夹爪目标 | 逐行预检转换后执行 | 不支持 |

现有创建 Env、reset 或自行录制的独立 runner 不能直接作为 `existing` 输入。
这种 runner 应提取接收外部 Session 的薄回调，保留原策略及原 CLI 默认行为。
公共 `SessionExecutor.step(action, mode=...)` 复用现有动作编译器，支持显式控制模式；
`step_public(row)` 可提交公开布局。两者都不拥有场景或 recorder 的生命周期。

`session` 依赖收集会遍历 Python 静态导入及包初始化文件；动态导入和数据文件用
`--include topogym/planning/<相对文件>` 显式补齐。仅允许私有 planning 依赖，
不打包 `scripts`、`legacy`、`calibration_tools`、`deferred`，也不覆盖公共物理模块。
第三方运行库仍须由已有镜像提供；打包检查不代表这些库已在镜像中实际导入成功。

## 身份及执行约束

- 精确绑定完整 `instance.json`、源码身份、资产身份、`instance_assets/` 文件哈希及 task tooling。
  缺少身份信息的旧包会报告 `blocked_identity`；先从正确版本生成新冻结包，不能补写虚构身份。
- 参考来源与目标包的 seed、场景、判据、机器人、物理时序及辅助抓持必须一致。
  soft-state 相对路径只允许按现有 tooling 解析到同一份绑定资产。
- 不自动重排、裁剪、重采样动作或修改夹爪目标。原生夹爪经过公开宽度转换再反解，
  误差须不超过 1 µm；关节 float32 转换误差须不超过 1e-6 rad。
- 每行执行一个原控制周期。只接受最后一行因 Task 结束而缩短的 tick 记录；
  不把任意 `_physics_steps` 覆盖传给 Session。轨迹结束不追加保持或静置动作。
- wrapper 统一开始/结束轨迹记录；回调不能 reset、rewind、替换配置或 recorder。
  结束时核对 Session 记录、Env 控制计数和物理 tick，发现绕过 Session 推进时失败。
- 脚本异常、仅策略完成、原生 Task 未成功均返回失败；尽可能保留部分轨迹与失败报告。
  原生成功报告为 `native_success_pending_harbor_verifier`，仍须独立 verifier 通过。
- standard 模式只使用公开 HTTP。断连后按服务确认的控制步前缀续传，不重复已确认动作；
  HTTP 本身不提供完整实例哈希，因此身份保证来自绑定的 task 包及后续 verifier。

公开 NPZ 必须包含 `actions`（可精确表示为 float32 的二维数组）、`action_layout`、
`task`、`instance_sha`（对应冻结 `state_sha`）和 `scene_seed`，可附带
`physics_steps_per_action`。原生 NPZ 使用 `targets`、`layout`、可选 `physics_steps`；
夹爪列必须显式命名为 `<arm>_native_gripper`。两种轨迹都必须另传 `--source-instance`，
不根据数组形状推断来源或控制语义。

## 使用

从仓库根目录执行。所有候选输出为 `<output>/<原任务目录名>`；已有目录不覆盖。
`environment/` 和 `tests/` 保持字节一致，仅生成新的私有 solution 和候选元数据。
候选包始终标记 `oracle = "none"`、`harbor_qualified = false`，不继承来源的 full 资格。

```bash
.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py inventory

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py inventory --tiers easy medium hard

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py compare \
  --reference-instance <参考-instance.json> --target-instance <目标-instance.json>

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py package \
  --task tasks/topogym-cast-keyhole-very-easy-i00-privileged \
  --output runs/test_results/oracle_bridge_new --kind existing

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py package \
  --task tasks/topogym-cast-keyhole-easier-i00-privileged \
  --output runs/test_results/oracle_callback_new --kind session \
  --source-root tasks/topogym-cast-keyhole-easier-i00-privileged/solution \
  --entrypoint topogym.planning.cast_keyhole.public_session:run_feedback_policy

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py package \
  --task tasks/topogym-cast-keyhole-very-easy-i00-standard \
  --output runs/test_results/oracle_standard_new --kind public_trajectory \
  --source-instance tasks/topogym-cast-keyhole-very-easy-i00-privileged/environment/instance.json \
  --trajectory <同一实例已验收的-trajectory.npz>

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py check \
  --task runs/test_results/oracle_bridge_new/topogym-cast-keyhole-very-easy-i00-privileged

.venv-gs121-nyx/bin/python scripts/oracle_runners/harbor_oracle.py run \
  --task <已绑定参考的原三档候选目录> \
  --tiers easy medium hard \
  --output runs/test_results/oracle_jobs_new
```

`run` 默认只输出完整 Harbor 命令，不创建 job；加 `--execute` 顺序运行 oracle/nop，
无需模型或模型凭证。宿主需要可用 Docker、匹配镜像和 NVIDIA GPU。
受限沙箱中的 `nvidia-smi` 失败或 Docker socket 不可访问，不能据此判断宿主 GPU/驱动不可用；
应在有宿主设备和 Docker 权限的执行环境复核。实际作业还需留出足够显存，保留其他会话的运行。
复用 `process_limits.run_guarded` 监控 CPU/内存，在系统内存达到 90% 时停止本轮 worker；
保存 `plan.json`、`results.json`、各 job 日志及资源记录，非预期评分或基础设施错误即停止队列。
退出成功只表示本批评分符合预期；两种模式的 oracle=1、nop=0、独立回放、视觉证据和隔离检查
仍须一起审查后才能授予资格。此入口不修改现有 `difficulty_eval.py` 的模型评测流程。

## 逐任务剩余接入工作

下表是当前冻结实例的接入路线，不推断新 seed 的可解性。运行 `inventory` 获取当前任务包列表；
runner 文件存在不代表已有完整成功证据。任何物理/几何版本差异都需要另建对应版本的新 task 包。

| 任务 | 当前接入重点 |
| --- | --- |
| Cast Keyhole | 两档简化任务已有可打包脚本/反馈回调；原三档参考与现包时序不同，需绑定匹配版本 |
| Lock Picking | 两档 simplified 的 Session 回调与原生目标转换；原三档仍需区分流程完成与 Task success |
| Cast Coil | 接入现有策略回调；将已验证候选对应的实例、物理 profile 和证据成套绑定 |
| Fiber Bundling | 复用收拢策略；原三档的辅助抓持/物理 profile 与旧 Harbor 包差异需明确处理 |
| Buzz Wire | 编译动作索引与物理 tick 的语义需显式接入；不能默认等于 control step；部分包缺源码身份 |
| Hedgehog | 接入反馈回调；对齐支撑、初态及场景修订对应的实例 |
| Interlocked Claws | 对齐原三档分离停稳目标和新版几何；旧包入区目标不能沿用其成功证据 |
| Horseshoe | 沿用配方哈希约束；提取接收 Session 的执行回调并绑定相同几何/时序 |
| Knot Untying | runner 注入外部 Session，归并 recorder 所有权；保留 IPC 配置、初态及各档证据范围 |
| Blanket Flatten | 先把原 oracle 专用 material/PBD 支持变成 simulator 与 verifier 一致的运行支持，再接执行回调 |
| Rope Threading | 对齐开发参考的材质、网格、接触、辅助抓持和时序；不能直接重放到旧无辅助抓持包 |
| Slotted Post Ring | 尚缺完整机器人 oracle，公共 bridge 不能补出任务策略 |
| Orbits | 尚缺完整机器人 oracle，历史外力流程不能作为机器人参考 |
| Cube fixture | 旧包缺完整冻结身份，需从匹配版本生成新包后才能接入 |

当前实施顺序：先核对 easy / medium / hard 的参考证明与 Harbor 冻结输入，
对匹配实例运行双模式 oracle/nop；存在配置差异的刚体任务先准备对应版本的新包，
再处理 Knot / Rope / Blanket 的冻结状态及共享运行支持；缺完整 oracle 的任务单独完成策略验证。
每个任务优先只增加参数/证据声明及薄回调，共享模块不增加按任务名分支的执行逻辑。

## 检查范围

`ci_checks/test-harbor-oracle-bridge.py` 检查跨机器人动作、实例错配、私有依赖闭包、
打包完整性、隔离进程中的 wrapper 生命周期、失败证据、标准服务续传和评分分类。
隔离进程使用假的 task tooling；这些检查不运行 Genesis，也不构成可解性或物理回放证据。
源码隔离静态规则可用 `ci_checks/check-calibration-isolation.py` 检查；真实镜像验证需显式传入镜像。
