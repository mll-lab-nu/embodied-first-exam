# Fiber Bundling 三档独立审计（2026-10-03）

**easy / medium / hard 的 seed 0 三档均通过，正式收录 3/3。** 本次补审计 2026-09-29／10-01 的连续机器人运行，新增物理执行次数为 0。原始 `run_report.json` 的 `native_success_pending_independent_audit` 与 `accepted_proof=False` 保持原字节；验收状态以本批 [summary.json](summary.json) 及独立报告为准。

| 变体 | 原始运行 | 模拟时间 | 核对状态（含出生） | 原判据审计／当前 v4 复核 | 全程最大采样弯折 |
| --- | --- | ---: | ---: | --- | ---: |
| easy，4 芯 | [easy_02](evidence/runs/easy_02/run_report.json) | 190.075 s | 7,604 | [通过](evidence/audits/easy/audit.json)／[通过](evidence/audits/easy/current_contract_and_seal.json) | 9.843° |
| medium，8 芯 | [medium_full_01](evidence/runs/medium_full_01/run_report.json) | 344.000 s | 13,761 | [通过](evidence/audits/medium/audit.json)／[通过](evidence/audits/medium/current_contract_and_seal.json) | 9.804° |
| hard，16 芯 | [hard_full_01](evidence/runs/hard_full_01/run_report.json) | 639.125 s | 25,566 | [通过](evidence/audits/hard/audit.json)／[通过](evidence/audits/hard/current_contract_and_seal.json) | 9.929° |

三档均从 Panda + Robotiq 默认 home 开始，普通 `JOINT_ABS` 动作经统一 Env 执行。策略抓 `trunk_04` 粗护套，用固定环外缘整理细丝，再对中、整体送入并持稳；easy / medium / hard 分别执行 4／8／20 次梳丝。三档各一次实际双指接触触发 `contact_weld_v1`，获取时刻均为 tick 547，此后无失抓、无回溯。最小关节限位余量 0.4136 rad；最大抓持平移误差不超过 0.646 mm，最大旋转误差不超过 0.00682 rad。

## 审计内容

1. 在独立进程加载各运行的冻结 Task，核对源码清单、逐段日志 SHA-256 和连续状态谱系，重建全部资产，逐 tick 重算成功判据。固定终端／环保持不动；出生姿态、关节限位、一次连续健康护套抓持通过；抓持获取证据与原生双指接触一致。
2. 独立交叉核对 46,931 个状态、46,928 条完成动作：private 状态中的 world、机器人观测与已封存且带哈希的 inline segment 日志相同，动作请求与分段动作一致，执行目标与保存目标一致。同时核对配置、源码、资产、workflow 身份，以及起止状态和记录数量。
3. 核对 1,877,120 个 solver 子步的原生接触摘要覆盖；夹爪—细丝禁碰检查通过。所有细丝按 tip-to-root 顺序穿环，前护套清出，终态稳定 0.5 s。环心平面的独立线性插值统计没有圆管带内的前向穿越；整理过程中环外穿越是中间动作，不能单凭此统计判断完整穿环。
4. 用本批另行冻结的当前 v4 Task 重新计算三档完整历史，成功／终止标记与稳定窗口逐 tick 一致。保存原生数组块及其 SHA-256；未生成或替换缺失接触证据。
5. [五项反例检查](evidence/supporting/negative_probes.json)通过：完整性不足的两状态前缀被拒绝；在独立临时副本中减少子步样本、修改未封存 world、改变执行目标或配置，都得到对应拒绝原因。完整原证据不受修改。

## easy 的版本身份

`easy_02` 实际使用 `terminal_v3_fiber_contacts`，原实例 ID 为 `042d201469ceffc82dfc5f68ea6eba17328c8f8714d3379ec744664e3fce97c9`。它通过原冻结判据审计，并在第 7,603 tick 同样通过当前 `terminal_v4_fiber_ring_plane`。当前 v4 实例 ID 为 `77ceead1e0ce0a8f62cff60227132f5bac29b37c2a278d9764ddbba2ac9d612e`；差异来自删除终态专用 `aperture_margin_m` 参数。重建差异仅在 `scene_preset.json` 及记录其哈希的 `sha256.json`，全部几何文件逐字节一致，[参数对照](evidence/supporting/easy_crosscheck_v2_preset_comparison.json)保留两份配置。

medium / hard 原执行已使用 v4，资产和实例 ID 与本批当前 Task 相同。以上复核不声称用今天的完整执行栈新跑了三次物理，也不修改 easy 的历史身份。

## 环境、范围与复现

使用原 `.venv-gs121`：numpy 2.4.4、trimesh 4.12.2、scipy 1.17.1、Genesis 1.2.1。首次误用 `.venv-gs121-nyx`（trimesh 5.1.0）时三档资产重建哈希均被拒绝，失败结果保留在 `evidence/supporting/development/`；切回原环境后三档完整资产哈希全部通过，没有放宽资产检查。补充脚本首版把 workflow 的空回溯列表误按数字比较；修正后完整重跑三档，首版结果也保留。

从仓库根目录执行；输出目录及文件使用新名字：

```bash
fiber_proof=solvability_proof/fiber_bundling/2026-10-03
.venv-gs121/bin/python \
  "$fiber_proof/evidence/supporting/native_auditor/scripts/audit_fiber_bundling_robot.py" \
  --run "$fiber_proof/evidence/runs/easy_02" \
  --output runs/test_results/fiber_easy_independent_reaudit
.venv-gs121/bin/python "$fiber_proof/evidence/supporting/crosscheck.py" \
  "$fiber_proof/evidence/runs/easy_02" \
  "$fiber_proof/evidence/supporting/current_source_snapshot" \
  runs/test_results/fiber_easy_current_contract_reaudit.json
```

medium / hard 分别替换运行目录为 `medium_full_01`／`hard_full_01`，并使用各自输出路径。第一条只用冻结原判据；第二条核对封存证据并重算本批冻结的当前 v4。完整策略、IK 规划、已选参数及原执行命令均保存在每个运行的 `source_snapshot/`、`planning/`、`qualification/selection.json`、`invocation.json` 中。

资格限定默认参数、seed 0、CPU float64、25 ms World tick／40 子步／1 tick/action，Task 和辅助抓持检查频率为 40 Hz，积分子步为 0.625 ms；末态保留护套辅助抓持。其他 seed、默认 400 Hz 检查、纯摩擦抓持、连续时间 CCD、阈值标定及 Harbor 正向评分不在本批资格内。`thresholds_calibrated=False` 保留。本次无新增 RGB／视频，已有正式 demo 属于其各自历史运行。

完整证据为独立普通文件副本，原始运行保留。[归档清单](archive_manifest.json)和[完整性验证](archive_validation.json)记录路径、字节数与 SHA-256。`evidence/` 不自动提交 Git，移交证明时需同时携带；运行依赖不打包。
