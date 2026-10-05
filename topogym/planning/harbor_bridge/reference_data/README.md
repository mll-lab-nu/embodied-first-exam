# Harbor 私有参考输入

本目录保存三档 seed 0 oracle 运行实际读取的参考输入，可随 Git checkout 交付。
原文件从 `solvability_proof/` 的证明档案或 `runs/` 的开发输入复制，字节保持一致；原目录与完整证据保留。
`manifest.json` 记录每个文件的来源、大小和 SHA-256。管理方 `references.py` 校验后，
只把所选家族／难度需要的文件放入该候选的 `solution/`。
本目录不进入公共 simulator/verifier 镜像。

| 家族／文件 | 运行用途 |
| --- | --- |
| Buzz 各档 `recipe.json` | 完整默认策略选择、输入哈希、历史证据及布局／home／控制周期绑定 |
| Buzz easy `selection.json` | 成功执行的完整 11 段反馈配方，包含终点转正与释放 |
| Buzz medium/hard `policy_actions.json` | 已审计的完整普通关节动作序列，分别为 29,544／43,568 行；不恢复物理状态 |
| Buzz medium `medium_traverse_guide.json` | 分阶段 oracle 的持工具路线引导；1,187 个实测位姿，运行时重新连接及检查 |
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

Buzz medium 的阶段参数 `guide_file` 使用本目录下的相对路径
`buzz_wire_3d/medium/medium_traverse_guide.json`；读取位置按私有模块解析，不依赖当前工作目录。
历史 selection 若仍记录 `runs/test_results/buzz_staged_inputs_20260929/medium_traverse_guide.json`，
须在新候选配方中改为上述路径，保留原 `guide_sha256`，并重新打包。
默认 Harbor 回调已选择 easy 完整 staged selection，以及 medium/hard 完整 compiled actions；
引导文件不承担这两档默认全流程的动作输入。缺少完整策略文件时直接报错，不回退到在线搜索。
新增动作与 selection 从各 `manifest.json` 来源路径原样复制，recipe 是由源报告、审计、
源快照中的 Task 布局及初始机器人观测生成的派生记录；源布局与当前布局已核对一致。
历史报告和审计哈希只记录出处，当前环境仍须完整执行和独立评分。
