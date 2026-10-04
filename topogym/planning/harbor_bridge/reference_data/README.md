# Harbor 私有参考输入

本目录保存三档 seed 0 oracle 运行实际读取的参考输入，可随 Git checkout 交付。
原文件从 `solvability_proof/` 的证明档案复制，字节保持一致；原目录与完整证据保留。
`manifest.json` 记录每个文件的来源、大小和 SHA-256。管理方 `references.py` 校验后，
只把所选家族／难度需要的文件放入该候选的 `solution/`。
本目录不进入公共 simulator/verifier 镜像。

| 家族／文件 | 运行用途 |
| --- | --- |
| Fiber `selection.json` | 抓取、逐根收拢、穿环等阶段选定的参数 |
| Claws `witness.json` | 实例身份、物体分离路径及几何证书；运行时重新审计 |
| Hedgehog `pickup.json` | 抓点、预抓、物体路径提示和换抓配方；medium 使用内置配方 |
| Horseshoe `recipe.json` | 模型身份、阶段顺序、参数以及五份输入的哈希 |
| Horseshoe `grasps.json` | 双手抓点、TCP 位姿和关节参考 |
| Horseshoe `reference.json` | 各刚体的参考位姿序列 |
| Horseshoe `fold.json` | 折叠／转向路线及 IK、碰撞采样记录 |
| Horseshoe `support.json` | 支撑与交接姿态参考 |
| Horseshoe `approach.json` | 接近抓点的关节参考与采样检查 |

这是按运行依赖挑选文件，不是精简后的统一 JSON schema。原文件中的历史 `config`、
`work_dir`、来源路径、`passed`、`accepted_proof`、审计链接等字段保留为出处信息，
不作为当前 Harbor 成功资格。Horseshoe 回调将实际输入路径改为当前 `solution/` 内的路径，
不会使用旧 `work_dir` 创建环境，也不加载旧审计路径。场景由当前绑定的 Session 创建；
机器人仍须执行控制动作，由当前任务和隔离 verifier 独立评分。

新增或替换参考时，显式更新 manifest 并核对来源；缺文件、错误 seed 或哈希变化均报错，
不回退到作者本机的证据目录。不能只提交 Python 修改而遗漏本目录。
