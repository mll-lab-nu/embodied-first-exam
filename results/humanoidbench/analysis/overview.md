## 总体结论
- **过线**：GPT-6 Luna 在 23 个计分任务上 limited 0 个、full 3 个（push、reach、sit_hard）。GPT-6 Sol 和 Claude Opus 5.5 各跑 5 个任务（walk、door、push、cube、sit_hard）：Opus limited 过 2 个（push、sit_hard）、full 过 4 个（cube 以外都过）；Sol limited 过 1 个（push），full 只跑了 walk 和 sit_hard，过了 sit_hard。
- **limited 卡在站稳，不在信息**：几乎每个 limited 失败的底层都是站不住或一迈步就倒；没有一个运行做出能正常前进的步态，Opus 在 walk 里站满全程也只有约 0.27 m/s。Luna limited 离及格线的中位数只有 0.02，full 是 0.35。加信息也没解开：第 5 版里 reset 加到 100、打开头部深度，只多过了 push 一个任务；第 7 版补上连杆质量和质心后，也只有 Opus 的 door 真用它算了质心。
- **新给的机器人数据多半只打印**：34 个 limited 运行里，只有 5 个把关节位置用进了代码（Opus 的 walk、door、push，Sol 的 door，Luna 的 push），其余的最多只在开头打印过一次。唯一算了质心的 Opus door，此后一局没再倒。
- **Luna limited 的 reset 用得快、押得险**：21/23 个任务用完 50 次 reset，用时中位数 20.9 min，剩下近 40 min 没用上；13 个任务被评分的最后一局是没整段跑过的新脚本；hurdle、powerlift、door、bookshelf、basketball 都有一条命令里的自动循环一口气烧掉 14–45 次 reset（door 的 31 次只用了 3.9 s）。
- **full 输在自拟的目标上**：Luna 在 21/23 个任务上 full 高于 limited（cabinet、kitchen 除外），靠的是完整状态和无限重来；但它们看不到 reward，自拟的代理分常有偏差：walk 的代理分给原地站立也打分，cube 用线性点积代替说明写的 sharp 朝向项，balance 两个任务只按活了多少步来挑。
- **Opus 快、准，但常提前收工**：full 的 4 个过线分别用 3.9–48.8 min；在 walk、sit_hard、door 上它凭记忆重建了上游的 reward，walk 自算的 834.8027 和评分一模一样。另一面，cube 的 limited（5.8 min）、door 的 limited（14.3 min）和 cube 的 full（17.3 min）都在预算还剩一大半时就停了。
- **防泄漏守住了**：full 的 agent 读到的上游源码里 `get_reward` 已经删掉，`pip`、HuggingFace、GitHub 的请求都被网络白名单挡下；拦不住的只有模型记忆。

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
