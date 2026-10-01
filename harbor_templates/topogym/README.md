# TopoGym Harbor 公共模板

这里是生成器的维护源；`tasks/topogym-cube-pick-place-i00*` 现在只是生成出来的示例任务。

- `common/rcb_topogym.py`：Session、显式 variation/scene seed、冻结实例、轨迹和 replay；`rcb_topogym_interlocked.py`
  （interlocked_claws 的 pre-weld 修复）和 `rcb_topogym_ipc.py`（四个 FEM/IPC 族的 FEM checkpoint 显存泄漏修复）是它的两个变体。
- `unlimited/`：privileged 模式的环境和独立评分器（两遍回放，第二遍同时渲染视频）。
- `limited/`：standard 模式（`eai-standard/2.2`，带崩溃恢复）的公共客户端、协议层（`scripts/eai_standard/` 的原样副本）、
  模拟器 sidecar（`server.py`、`run.sh`、collect hook `finalize.sh` + 新进程回放 `replay.py`）和评分器。
- 分档任务的目录名、字段和预算见 `docs/rcb/benchmarks/topogym.md`。

`scripts/topogym_mk_task.py` / `topogym_mk_limited.py` 将文件复制到独立 Docker build context；
生成包不依赖指向此目录的符号链接，也不从宿主公共模板 import。
Blanket 的数值初态位于各包的 `instance_assets/`，limited 只将它放在 sim sidecar。

旧 `Session(task, eval_index=0)` 和 `make-instance --eval-index 0` 继续可用。
新选择方式是 `Session(task, variation_id="seeded", seed=...)`，或
`make-instance --variation seeded --scene-seed ...`；两套选择方式互斥。
显式选择实例 JSON 的 `eval_index` 为 `null`，NPZ 轨迹用整数 `-1` 表示，避免 object/pickle 字段。

改动共享工具后须同步已提交任务包中对应副本；`ci_checks/check-tooling-identity.sh`
同时检查包间一致性和公共模板一致性。旧任务包的预算和历史实验结果不由此回写。
RCB 原样引入文件的来源及 blob 仍由 `ci_checks/rcb_vendor.json` 记录。
