## 总体结论
- **主结果是 GPT-6.1 Sol（每个任务每种模式各跑一次）**：23 个计分任务 limited 过 3 个（push、reach、sit_hard），full 过 9 个（walk、balance_simple、push、cube、maze、basketball、reach、sit_hard、kitchen）；夹具 sit_simple 两种模式都过。对照：GPT-6 Luna 同样 24 个任务 limited 0、full 3（push、reach、sit_hard）；GPT-6 Sol 和 Claude Opus 5.5 只跑了 5 个任务（walk、door、push、cube、sit_hard），Opus limited 2、full 4，Sol limited 1、full 1/2。
- **有几个是贴线过的**：limited 的 reach 12008.39（线 12000）、sit_hard 750.77（线 750），full 的 basketball 1239.38（线 1200）；只有一次运行，重跑可能翻转。
- **limited 卡在站稳和最后一局**：GPT-6.1 Sol 把 `spec()` 的连杆质量、质心和关节位置用进了代码，truck、room 能原地站满 1000 步，但 23 个任务里仍没有一个做出能前进的步态；评的是最后一局，11 个任务 60 min 超时时被评分的那局还没跑完，11 个任务被评分一局不到自己最好一局的一半。得分/及格线的中位数只有 0.067（Luna 0.061）。
- **full 靠整机控制加搜索**：GPT-6.1 Sol 多用逆动力学整机控制、站姿反馈，再用自写 CMA-ES、进化搜索调参；23 个任务 full 都高于自己的 limited，21 个高于 Luna 的 full（door、package 除外），得分/及格线中位数 0.637（Luna 0.397）。没过的多卡在抓取和多阶段（cabinet、truck、insert_normal、powerlift）以及步态（stair、hurdle）；window 618.02 只差 31.98。
- **full 的分数部分来自模型记忆**：上游 `get_reward` 已删，但 GPT-6.1 Sol 凭记忆写出的代理分和评分几乎一样（walk 920.11 对 917.19、hurdle 350.97 对 349.62、stair 159.843 对 159.84），kitchen 的 0.3 完成半径、balance 的 1.65 m 站高也是记出来的；Opus 在 walk 上也这样（834.8027 一模一样）。这拦不住，读 full 的分数时要考虑。
- **规则之内的取巧**：push 的前臂第 7 步以 5.5 m/s 把箱子扫过 5 cm 目标点（上游碰到即算成功，Luna 也是 8 步交卷）；basketball 故意抱球到第 380 步、第 500 步才投进，多挣每步分；kitchen 的水壶和旋钮越过目标就算完成，之后又被碰开。都是物理上真实的动作，说明里也写了这些规则。
- **防泄漏守住了**：审计了 GPT-6.1 Sol full 的 7 个过线运行：镜像里的 `.pyc` 和删过的源码一致，评分容器只读动作，`pip`、GitHub、Hugging Face 的请求都被网络白名单挡下，模型请求里没有服务端工具。

## GPT-6.1 Sol
主结果。24 个任务两种模式各跑一次，第 7 版说明（`com_m` 修正后重新生成的任务）。下面的数字只算 23 个计分任务；夹具 sit_simple 两种模式都过（limited 第一局就过，750.08；full 989.76）。
### limited
- **3/23**：push（951.64，15 次 reset）、reach（12008.39，线 12000，29 次 reset）、sit_hard（750.77，11 次 reset）；三个都在 16 min 内过线，花费 $0.42–$1.13。
- **新数据用进了代码**：walk、stair、maze、reach、cube、door、truck、room、window 等都用 `links` 的质量、质心或关节位置算重心、做正运动学，再配相机位姿定位；truck、room 靠重心反馈原地站满 1000 步，cube ep11 之后不再倒。
- **被评分的那一局常不是最好的那一局**：11 个任务 60 min 超时（walk、stair、cube、powerlift、package、bookshelf_simple、highbar_simple、insert_normal、spoon、cabinet、kitchen），被评分的是超时时还在跑的最后一局；11 个任务被评分一局不到自己最好一局的一半，如 bookshelf_simple 75.82 对 767.48、truck 673.05 对 1287.41、walk 171.06 对 366.99。
- **和 Luna 比**：得分/及格线的中位数 0.067 对 0.061，只有 13/23 个任务被评分一局高于 Luna；用时中位数 59.9 对 20.9 min，花费 $59.20 对 $5.18。
- **想找外援**：walk、hurdle、stair、maze、room、truck 向 GitHub、Hugging Face 要 H1 策略，balance_hard、cube、door、kitchen、reach 试 `pip install opencv`，全部被网络白名单挡下。
### full
- **9/23**：walk 917.19、balance_simple 918.75、push 998.17、cube 478.13、maze 1386.71、basketball 1239.38、reach 19929.58、sit_hard 976.10、kitchen 4.00；balance_simple、maze、basketball、kitchen 是所有模型第一次在 full 上过（cube 第 4 版时 GPT-6 Sol 过过）。
- **整机控制加自写搜索**：walk、maze、reach、door、room、truck 用逆动力学整机控制，cube 用质心踝反馈加四元数雅可比转腕，balance 用质心与板的状态反馈；参数靠自写 CMA-ES 或进化搜索（`pip install cma` 都被挡下）。
- **没过的**：stair 交的是原地站立（159.84），hurdle 跑满 1000 步但只有约 1.4 m/s（349.62），door 把手开锁后前臂打滑、门最多开 26.5°（171.94），cabinet、truck、powerlift、insert_normal 卡在抓取和多阶段；window 618.02、spoon 507.43 离线最近。
- **用时和花费**：24 个运行都用满约 60 min，交卷时多数还在搜；23 个计分任务 $62.40（Luna $8.86）。push、door、hurdle 的 `gen.py` 只是回放存好的动作，不是生成它们的代码。
### 两种模式
- **full 23/23 高于 limited**：差在能不能站住、能不能离线试错；limited 用 `spec()` 算重心也只够原地站，full 用仿真状态做整机控制能走起来（walk 约 1.0 m/s、maze 走完全部检查点）。
- **两边都过的只有 push、reach、sit_hard**：其余 limited 失败的，full 多靠整机控制和搜索补上；limited 被评分的常是超时时还没跑完的那一局。
### 和 GPT-6 Sol 比（同样 5 个任务）
- **2/5 对 1/5**：push 都过；sit_hard 6.1 用髋偏航转向椅子后入座过线（750.77 对 383.12）；cube 338.91 对 96.06（线 370），walk 171.06 对 52.65，door 164.48 对 164.16。
- **full 4/5**：walk、push、cube、sit_hard 过，door 没过；6 Sol full 只跑了 walk、sit_hard（过 sit_hard），Opus full 也是 4/5（cube 没过）。
- **花法不同**：6 Sol 一条命令扫多个参数点，4 个任务 9.6–35.5 min 用完 50 次 reset；6.1 在 walk、cube 上跑满 60 min，5 个任务共 $10.60 对 $6.55。

## GPT-6 Luna
24 个任务两种模式都跑了，都是第 7 版说明。下面的数字只算 23 个计分任务；夹具 sit_simple 两种模式都过了（limited 第 978 步到线，750.57）。
### limited
- **0/23**：离及格线最近的 spoon（0.52）、window（0.47）、bookshelf_simple（0.31），都是站满全程、手停在物体旁边拿的分，物体都没放到位；push 一次没碰到箱子（−224.09）。
- **站不住、走不动**：walk、hurdle、stair、maze、room、truck 都没做出能前进的步态；reach、package、stair、sit_hard 被评分的那一局都倒了。
- **新数据只打印**：23 个任务都在开头打印过 `spec()`；只有 push 在最后两局把关节位置用进了手臂正运动学，但手点取的是偏了 0.31 m 的 `com_m`（见"各版的改动"），还是没碰到箱子。
- **看错了也不知道**：spoon 前 40 分钟一直在合错的那只手，truck 以为约 3 m 外的包裹就在手边，cabinet 把图上的一道缝当成门开了，hurdle 把侧躺说成 "stayed alive"。
### full
- **过了 push、reach、sit_hard**：push 用右手 IK 加躯干扭转，8 步推进（997.80）；reach 先蹲出能站满全程的低姿，再用雅可比逐步修正左臂（19184.07）；sit_hard 用 55 步快速下蹲落座，再换成静坐（946.31）。
- **离线最近的是 basketball**：1091.75，差 108.25；球在第 125 步进筐，但进筐前那段只挣了约 90.8 分。
- **步态仍是瓶颈**：walk 交的步态第 360 步左右就扑倒（128.52）；hurdle 越过第一道栏后在约 9.4 m 处倒下，stair 前冲约 1.1 m 就倒；room、truck 原地站满全程，没碰到物体；maze 是扑到第一个拐角，之后贴着地面爬。
- **代理分有偏差**：walk 的代理分直到第 51 分钟还给原地站立打分；cube 按线性点积挑方案（325.05）；spoon 自估约 603，实际只有 406.60。用时中位数 59.1 min。
### 两种模式
- **full 的优势来自看得到状态**：站稳（reach 4 分钟就搜到能站的蹲姿，room、truck 靠踝部反馈站满全程）和对准（IK）在 full 里做得到，limited 只有 IMU 和二维画面，做不到；full 不比 limited 高的只有 cabinet 和 kitchen。
- **同样的难点两边都卡**：步态、抓握、多阶段串接两种模式都没做成；full 多出的分多半来自站得更久。

## GPT-6 Sol
跑了 5 个任务：walk、door、push、cube、sit_hard，都是第 7 版说明。door、push、cube 的 full 因为 OpenRouter 余额用完没有跑。
### limited
- **过了 push**：两踝定在 −0.65 让身体前倾，双手搭到桌边，再用右肩横扫箱子；只用了 7 次 reset 就过线（969.31）。
- **reset 用得最快**：一条命令连扫多个参数点，每点花一次 reset；除 push 外 4 个都用完了 50 次，sit_hard 7.05 min 就用完。
- **坐上了却坐在前沿**：sit_hard 有 7 局坐满 1000 步，但骨盆一直停在座面前沿（383.12）；walk、cube 最长只站 223、283 步。
- **新数据用得少**：只有 door 用关节位置做了正运动学，手点同样取了偏掉的 `com_m`；cube 没读 `spec()` 里 IMU 的方向说明，把前后读反了。
### full
- **过了 sit_hard**：4.9 min 就有一条坐满 1000 步的轨迹，之后 54 min 细调；交的版本开头把两侧髋偏航转到 −0.43 的限位，再入座，离椅子中心约 0.3 cm（963.90，三家 full 里最高）。
- **walk 没过**：走满 1000 步、前进 13.03 m，但平均只有约 0.65 m/s（546.55）；它的代理分给原地站立也打分，自估约 702，比回放高约 155。
### 两种模式
- **full 能量出落点**：sit_hard 两种模式都是定时切换关节目标的开环方案，full 每个候选都量骨盆到椅子的距离，limited 坐住的 7 局都在座面前沿，也没试过髋偏航；walk 在 full 里靠速度反馈站满全程，limited 最长 223 步。

## Claude Opus 5.5
经 Claude Code 跑了 Sol 那 5 个任务，两种模式都跑，第 7 版说明。
### limited
- **过了 push、sit_hard**：push 靠 IMU 反馈控制踝部，让身体靠在桌边，再用正运动学、IK 加看图一小段一小段地推（913.15，9 次 reset）；sit_hard 用房间相机把椅子投影到地面，蹲下后踮踝让身体后倒落座，扫网格参数到第 21 局过线（750.22）。
- **新数据用得最好**：walk 用关节位置和轴做足端正运动学估速度（估约 0.26 m/s，实际约 0.27），站满全程（369.24）；door 用连杆质量算质心做平衡，此后一局没倒。
- **被偏掉的手点误导**：door 把 `left_hand` 的 `com_m` 当成手尖，得出 "The arms go through the door"，于是停手；push 看图后才把手点校正回来。
- **提前收工**：cube 5.8 min、door 14.3 min 就结束了，当时分别还剩 13、16 次 reset；cube 当时 `status()` 显示只用了 325.6 s。
### full
- **4/5**：walk 用 MPPI（10.9 min，834.80），sit_hard 用自写 ES 调 3 个关键帧（5.1 min，951.04），push 先调平衡再用左手从箱后推（3.9 min，966.99），door 用采样 MPC 先把门拉开约 1.25 rad 再走过去（48.8 min，676.02，交的是几个随机种子里最好的一个）。
- **cube 没转动方块**：3 min 就用 `subtree_com` 做平衡站满 500 步，但 CEM 没把方块转起来；它以为时间快用完，17.3 min 就停了（247.48）。
### 两种模式
- **有仿真器才能规划**：full 里在完整模型上做 MPPI、MPC、ES，4 个过线；limited 只能手调控制器、看图校准，过了 2 个，walk、door 都差在速度或手点上。

## 模型对比
同样 5 个任务，同一版说明。
- **limited：Opus 2、Sol 1、Luna 0**：离及格线的中位数分别是 0.52、0.25、0.01；分界在于能不能先找到站得住的姿势（push 上 Sol、Opus 都在 2.8 分钟内找到前倾站姿，Luna 到 24.7 分钟才找到，而且一伸手就后仰）。
- **full：Opus 4、Luna 2（push、sit_hard）、Sol 1/2（sit_hard）**：Opus 在完整模型上规划，Luna 和 Sol 靠自拟代理分去搜；三家都过的 sit_hard 上，Opus 5.1 min，Luna、Sol 都用了将近 60 min。
- **用新数据的程度**：Opus 3/5 用进了代码，其中 1 个算了质心；Sol、Luna 各 1/5 只做了正运动学；三家都把手的 `com_m` 当成了手的位置。
- **花 reset 和时间的方式**：Sol 和 Opus 一条命令扫多个参数点；Sol 在 4 个任务上把 50 次 reset 用光，Opus 常常自己提前停；Luna 一局一局地试，18.5–47.6 min 用完 50 次。
- **花费**：limited 5 个任务 Opus $8.90、Sol $6.55、Luna $1.21；full Opus 5 个 $5.36、Luna $1.96，Sol 只跑 2 个就是 $9.56。下面是三家 limited 运行的整段录像。

## 各版的改动
每一版只改说明文字、`spec()` 里的机器人事实和我们自己的服务，没动上游的 reward、终止条件和及格线。每条是起因 → 改了什么 → 效果；下面的表是每版的 commit 和运行数。
- **第 1 → 2 版**（06b0ab3）：第 1 版有几处和上游评分不一致，漏了速度目标和头部高度，full 有 5 次没解出就在 23–46 分钟停下 → 逐个对照上游改说明，写明不要提前停。
- **第 2 → 3 版**（e95d382）："800 out of 1000 steps" 被读成撑满 800 步；limited 每次都先花 reset 摸动作尺度；0.1.5 镜像里 reward 的辅助函数和注释还透露了 reward → 及格线写成奖励的总和，`spec()` 给舵机范围、关节轴、IMU 坐标系和相机位姿，镜像升到 0.1.6。效果：摸尺度的回合几乎消失，但 IMU 和画面方向照样读反。
- **第 3 → 4 版**（8e09011）：`spec()` 里的 `wall_clock_s` 和服务的时钟并存，让 agent 算错剩余时间 → 去掉 `wall_clock_s`；服务记下每次返回的图。
- **第 4 → 5 版**（e897737）：躺着、坐着没过线的一局会一直跑到第 1000 步，有运行把倒地的控制器当成好的；IMU 前后和画面左右常读反；服务时钟比 agent 早 52–96 s → 说明补上"没结束不等于没倒"，`spec()` 写明读数的正负号和相机的 right 轴，时钟从 agent 第一次请求算起，头部相机近裁剪面改为 1 cm，maze 写明起点。效果：IMU 方向多数读对，过线数不变；同版对照里 reset 加到 100 只多过了 push，打开头部深度一个也没多过。
- **第 5 → 6 版**（e897737，只改 cube）：256×256 时方块一面只有约 10–15 px → 每台相机改为 512×512。效果：认得出面上的字母，但照样站不住。
- **第 6 → 7 版**（ef883ec）：Sol 在 cube 的 full 里靠"质心在两脚上方"站稳，limited 却只有骨盆 IMU → 24 个 limited 任务的 `spec()` 都补上每个关节的位置、每个连杆的质量和质心、两脚的碰撞框。效果：多数运行只是打印了一下；把它用进代码的 5 个里，Opus 的 walk 估速准了、door 站稳了。另外有个问题：无质量的手（裸 H1 的 `left_hand`、`right_hand`）的 `com_m` 被算远了 0.31 m，误导了 4 个运行。已修正：`server.py` 给无质量连杆取其原点，24 个 limited 任务已重新生成，本轮不重跑。
- **说明以外**：结果工具在每一局结束时记下头比脚高多少，用来分出"结束了但没倒"和"步数到上限但已倒"，多阶段任务记下做到第几步；每块 GPU 最多同时跑 8 个 limited。
