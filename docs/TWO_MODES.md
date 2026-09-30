# 当前任务的两种模式

五个 benchmark 的当前版本统一放在：

```
limited_tasks/<benchmark>/<task>-limited60min-v3-iNN/
unlimited_tasks/<benchmark>/<task>-unlimited60min-v3-iNN/
```

`<benchmark>` 为 `vlabench`、`metaworldplus`、`robocasa`、`robocasa365` 或 `robocasa-gr1`。
清单以 [suites/two-modes.json](../suites/two-modes.json) 为准；每个 benchmark、每种模式有自己的 dataset.toml。
不要递归扫描 archive/jobs 后把历史版本再加入当前评测分母。

协议来自 [指定文档](prompts/metaworldplus_codex_luna_high_two_modes.md)，并应用用户最新覆盖要求：
**unlimited 无任何 episode/提交轨迹/累计探索步数或 reset 次数上限，只保留60分钟 agent墙钟预算。**
这与旧文档的原生 horizon 条款不同；MetaWorld 的500步时长截断因此在 unlimited 中关闭。
原生成功条件、机器人、物理参数和冻结实例不变，limited 仍保留原 episode 上限。

| 项目 | Unlimited | Limited |
|---|---|---|
| 观测 | 完整 privileged state | RGB、相机标定、机器人自身状态；无物体/目标真值、隐藏奖励或成功谓词 |
| Reset | 任意次数，恢复同一实例 | 不允许；一个连续 episode |
| 步数 | 不设单条/累计步数配额 | MetaWorld 500；VLABench 4000；RoboCasa系列3000，旧导航1200 controls |
| Agent时间 | 3600秒 | 3600秒 |
| 评分输入 | 截止前最后提交的轨迹 | sim封存的完整服务端 episode，包含失败动作 |
| 复现 | 两次独立重放 | 在线记录与两次独立重放精确一致 |

VLABench和RoboCasa的上述limited数字是现有仓库轨迹协议上限，不能统称上游原生horizon。
Verifier单独计时；unlimited为7500秒总限时、单worker3600秒，limited保留各模拟器既有重放预算。
归档字节/内存边界防止异常分配，不是动作数配额。超时、API/订阅、仿真/评分故障与普通任务失败分别记录。

Limited main不安装模拟器/实例/专家，不挂载sim数据或Docker socket；主控经私有Unix socket start/stop/seal。
可信Harbor网络sidecar只放行sim接口及订阅TLS代理，阻断宿主机网关、公网、Docker DNS及隐藏端口。
Unlimited的初始Session由可信setup预初始化，agent通过同容器的轻量代理使用原生Session API；后续reset和新增Session均计时。
该代理不提供oracle，不改变动作/成功判定；unlimited同容器root架构不宣称防恶意篡改。

当前runner配置Codex + ChatGPT subscription、`gpt-6-luna`、`high`；不会fallback到API key、其他模型或effort。
本轮没有调用模型；配置正确不等于订阅登录或该模型已经完成实际接入测试。

```bash
cd /home/changhe/projects/robot_coding_bench
HARBOR_PYTHON=/home/changhe/.local/share/uv/tools/harbor/bin/python

# 只读列出任务，包含不能运行的记录
"$HARBOR_PYTHON" scripts/two_modes/run.py list --benchmark metaworldplus

# 检查所有配置/指纹；不会启动仿真或模型
"$HARBOR_PYTHON" scripts/two_modes/check.py
bash ci_checks/run_all.sh

# 小规模 oracle/nop smoke：该 benchmark 的一个代表实例、两种模式
# output必须新建，防止覆盖已有尝试。只运行无模型参考与空动作基线。
"$HARBOR_PYTHON" scripts/two_modes/run.py smoke --benchmark metaworldplus \
  --output "jobs/two-modes-smoke-$(date -u +%Y%m%dT%H%M%SZ)"

# 未来正式单实例命令（本轮未执行）；需要有效的ChatGPT订阅登录
"$HARBOR_PYTHON" scripts/two_modes/run.py run --benchmark metaworldplus \
  --mode unlimited --task metaworldplus-push-unlimited60min-v3-i00 \
  --output "jobs/two-modes-codex-$(date -u +%Y%m%dT%H%M%SZ)"

# 历史路径定位，保留原始任务；--mode unlimited/limited可查当前对应版本
python3 scripts/two_modes/resolve.py tasks/metaworldplus-push-privileged-i00

# 只更新整理/验收报告，不启动试验
python3 scripts/two_modes/report.py
```

正式runner强制指定一个任务，attempts=1、自动retry=0，不会因一个命令误发全量模型评测。
必须使用统一runner；普通 `harbor run -p ...` 不会安装可信网络规则或激活/封存limited episode。
未就绪记录必须保留在覆盖分母，不能把配置检查或旧oracle成绩当成本版本模型成绩。

旧任务目录及旧模式版本归档在 `archive/task_versions/pre-unified-20260929/`；旧ID和路径的映射在
[suites/task-path-aliases.json](../suites/task-path-aliases.json)。历史jobs/原始结果保持原样；其中的旧路径通过resolver定位。
VLABench保留历史视觉ID并标注同实例别名，不当作独立随机样本。详见 [整理报告](validation/two-modes-v3/REPORT.md)。
