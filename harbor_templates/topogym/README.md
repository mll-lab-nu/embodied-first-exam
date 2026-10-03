# TopoGym Harbor 公共模板

这里是生成器的维护源；`tasks/topogym-cube-pick-place-i00*` 现在只是生成出来的示例任务。

- `common/rcb_topogym.py`：Session、显式 variation/scene seed、冻结实例、轨迹和 replay。新包统一使用这个工具，
  包含保持夹爪原生目标、限制无梯度 FEM checkpoint 缓存和 Knot 判据向量化。`rcb_topogym_interlocked.py`
  与 `rcb_topogym_ipc.py` 保留用于追溯历史专用工具，新生成器不再按任务选择它们。
- `unlimited/`：privileged 模式的环境和独立评分器（两遍回放，第二遍同时渲染视频）。
- `limited/`：standard 模式（`eai-standard/2.3`，带崩溃恢复）的公共客户端、协议层（`scripts/eai_standard/` 的原样副本）、
  模拟器 sidecar（`server.py`、`run.sh`、collect hook `finalize.sh` + 新进程回放 `replay.py`）和评分器。
- 分档任务的目录名、字段和预算见 `docs/rcb/benchmarks/topogym.md`。

`scripts/topogym_mk_task.py` / `topogym_mk_limited.py` 将文件复制到独立 Docker build context；
生成包不依赖指向此目录的符号链接，也不从宿主公共模板 import。
Blanket 的数值初态位于各包的 `instance_assets/`，limited 只将它放在 sim sidecar。

旧 `Session(task, eval_index=0)` 和 `make-instance --eval-index 0` 继续可用。
新选择方式是 `Session(task, variation_id="seeded", seed=...)`，或
`make-instance --variation seeded --scene-seed ...`；两套选择方式互斥。
显式选择实例 JSON 的 `eval_index` 为 `null`，NPZ 轨迹用整数 `-1` 表示，避免 object/pickle 字段。

新包写入 `metadata.tooling_version = "10"`，采用 `-privileged` / `-standard` 名称，默认镜像由
`scripts/cuda_profiles.py` 和 `images/topogym/VERSION` 决定（当前配方为 `0.2.10-<cu128|cu130>`；两种 GPU 配置的实测资格分别记录）。
`ci_checks/check-tooling-identity.sh` 对 v10 包检查当前公共模板的一致性；历史无版本包及 v3–v9
按 `ci_checks/topogym_tooling_versions.json` 中的固定哈希检查。更新模板不改写历史包，旧包也不会自动获得新修复；
需要新修复时生成并验证新包。旧任务包的预算和历史实验结果不由此回写。
RCB 原样引入文件的来源及 blob 仍由 `ci_checks/rcb_vendor.json` 记录。

v5 的实际动作/tick 轨迹、实例资格、评分先于录像持久化、共享录制与请求恢复行为见
[standard 2.3 / tooling v5 合同](../../docs/rcb/STANDARD_MODE_2_3.md)。B10 新判据仅显式选择，默认仍保留版本 1。
