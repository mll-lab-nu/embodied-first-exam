## 总体结论
- **过线很少**：23 个计分任务里，Luna limited 按第 5 版说明重跑后过 1 个（sit_hard；上一版过的 push 这次没过，reset 加到 100 的那次又过了），full 过 3 个（push、reach、sit_hard）；Sol 跑的 5 个任务 limited 0 个、full 1 个（cube）；Opus 跑同样 5 个任务的 limited，0 个。
- **full 普遍比 limited 走得远**：Luna 在 22/23 个任务上 full 回报更高，离及格线中位数 0.39 对 0.03。差距主要来自 full 看得到完整状态、能无限重来。
- **limited 最先卡在站稳**：几乎每个 limited 失败的底层都是站不住或一迈步就倒；行走类任务里没有一个 limited 运行做出能前进的步态，有物体的任务里手常常送不到物体旁。
- **limited 卡在控制，不是卡在 reset**：Luna 第 5 版的 23 个里 21 个是 reset 用完才停，停时中位数只用了 20 分钟；reset 加到 100 的 16 个运行里 11 个在 60 分钟内照样用完（中位数 19 分钟），只多过了一个 push，而那次只用了 14 次 reset。Sol、Opus 常在 10 分钟内用完或主动停下。
- **读错方向和状态，每个模型都有**：IMU 前后读反、把画面的左右当成机器人的左右、拿二维画面判断远近、把"本局没结束"当成"没摔倒"。
- **full 输在自己拼的目标上**：agent 看不到 reward，要按说明自己拼目标，常漏掉说明点名的项，也从不把目标换算成回报去和及格线比。
- **防泄漏守住了**：full 的 agent 常去读已删掉 reward 的上游源码，多次 pip、HuggingFace、GitHub 请求都被网络白名单挡下；拦不住的只有模型记忆（Opus 凭记忆复述过 reward 的结构）。

## GPT-6 Luna
24 个任务两种模式都跑了；limited 又按第 5 版说明（未提交，job 名以 `-text5` 结尾）重跑了一轮，下面 limited 的数字取这一轮，cube 取每台相机 512×512 的 `-text6`。数字只算 23 个计分任务；sit_simple 是夹具，两种模式都过。
### limited
- **过了 sit_hard，丢了 push**：sit_hard 第一次在 limited 过线（750.81，向左后方小步退到座面上方再分两段坐下，过线的是最后一批脚本里一个没试过的髋横滚值）；push 这次一次没推动箱子（−215.53）。其余离及格线超过 0.2 的只有 bookshelf_simple 0.32（站满 1000 步，没挪动物体），中位数 0.03，和上一版一样。
- **说明的改动读进去了，控制没变**：IMU 的前后左右这次多数读对（walk、door、truck、kitchen、spoon、basketball 上一版都读反过），但反馈的正负号仍是正反各试一次；关节轴的正负号和相机的 right 轴几乎只打印、不进代码（insert_normal 例外，按轴把 torso 当偏航轴用，上一版到第 44 分钟才改过来）。
- **"没结束不等于没倒"只挡住了一半**：walk、hurdle、reach、truck 都认出了倒地后这一局还在跑；stair 仍把前扑后趴着跑满的最后一局说成 "without falling"，maze 把坐在地上当成直立，push、package 的最后一局躺着跑到步数上限。
- **新时钟没人用来排时间**：服务时钟和 agent 的钟对上了，spoon、insert_normal 不再因为时钟快一分钟而提前收尾；但 21 个运行是 reset 先用完，停时中位数还剩约 40 分钟。
- **最后一次 reset 常押在没试过的脚本上**：stair、package、truck、reach、walk 的被评分段都是临时写的新脚本；door 让一个自动循环 1.6 秒内烧掉最后 6 次 reset（开深度的 window、hurdle 也一样，29 次、16 次）。
### full
- **过了 push、reach、sit_hard**：都是读仿真状态再搜索。push 用 IK 斜推，reach 用 CEM 调 34 个参数，sit_hard 从状态读出朝向，先转髋再坐。
- **离线最近的两个都差在逐步分**：maze 1122.6/1200 走完了所有检查点，但一路趴着（平均直立度 0.04）；basketball 1044.0/1200 进了球，进球前 71 步只挣了约 43。
- **步态仍是瓶颈**：walk、hurdle、stair、balance、truck、room 在 full 里也没做出能走的步态，hurdle、stair 只到及格线的 5–14%，walk 最后交的是原地站立。
- **目标漏项，从不估回报**：常漏掉说明点名的项（maze 的撞墙、window 的速度和头部位移、powerlift 的哑铃高度、cube 的"带正负号、要尖锐"），insert_normal 还把手和插座配反了；12/23 用满 60 分钟，最后 20–30 分钟多在微调一个卡住的控制器。
- **长会话会丢结论**：上下文压缩之后，kitchen 把好的存档覆盖成了更差的一版，insert_normal 丢了已经找到的"要掉头"。
### 两种模式
- **full 的优势来自看得到状态**：站稳（LQR、状态反馈）和对位（IK）在 full 里几分钟就能做到，limited 只有 IMU 和二维画面，做不到；full 不比 limited 高的只有 kitchen（两边都是 0）。
- **同样的错两边都有**：关节下标写错、髋部正负号反了，两种模式都出现；full 靠整段 rollout 能发现并改掉，limited 每试一次就要花一次 reset。

## GPT-6 Sol
跑了 Luna 两种模式都没过的 5 个任务，每类一个：walk、door、cube、package、bookshelf_simple。
### limited
- **0/5，reset 用得最快**：walk、cube、package 在 5–9 分钟用完 50 次 reset，剩约 50 分钟；door 41.9 分钟用完；bookshelf 跑满 60 分钟。一条命令连扫多个参数点，每个点一次 reset。
- **站得比 Luna 稳一些**：bookshelf 站满 1000 步得 706.3（Luna 34.7），cube 91.9（Luna 58.0）；但 walk、package 最长都只站住约 215 步，没做出步态。
- **读方向偶尔出错**：door 把右倾说成左倾，bookshelf 多次被房间相机的远近误导；door 用了相机位姿反投影把手的位置。
### full
- **过了 cube**：照说明"朝向项带正负号、要尖锐"做成判据（max(dot,0)^16），3.8 分钟就靠质心反馈站满 500 步；Luna 在同一任务上用线性点积，没过。
- **walk 最接近**：手写反馈步态加 DE 调参，走满 1000 步、前进 12.3 m，速度 0.61 m/s 还不够；自估 583、回放 603，估得很准。
- **door 唯一开了门**：用快照分段采样，门开到 0.85 rad，但身体没过去；package 刻意不触发终止，回放 −337.5，反而低于 Luna 的 875.1。
### 两种模式
- **full 比 limited 好得多**：离及格线中位数 full 0.50、limited 0.18；full 里状态反馈解决了站稳，limited 在同样的任务上一直没站住。

## Claude Opus 5.5
经 Claude Code 跑了 Sol 那 5 个任务，只跑 limited；这批 sim 日志存的是全精度动作，每一局的回放都是精确的。
### limited
- **0/5，用时最短**：5 个运行只用了 4–17 分钟，共 $8.68；door、package、bookshelf 3 个在还剩 8–18 次 reset、约 47–53 分钟时自己结束，没照说明"不要提前停"。
- **为什么提前停**：Claude Code 没有时钟工具，bookshelf 把已用时间估大了 7–8 倍；package 凭记忆里的 HumanoidBench reward 判断自己过不了；door 觉得"成功希望不大"。
- **`spec()` 用得最好**：IMU 坐标系写进代码且正负号正确；door、package 用相机位姿和 fovy 做反投影，包裹位置估到约 1 cm。
- **控制同样没做出来**：walk 把第 60 步就倒、在地上拖到第 903 步的那一局当成最好的，原样重跑成被评分段；bookshelf 手臂顶在隔板上，手指没合拢过；cube 3.6 分钟用完 reset，手腕一次没动。
- **看图很少**：每个运行只看 2–26 张，Luna、Sol 常看上百张。

## 模型对比
- **limited 三家都卡在站稳**：同样 5 个任务上，没有一家做出前进的步态或完成一次抓取；package 上只有 Opus 高于全零动作，bookshelf 上 Opus（709.3）和 Sol（706.3）都靠站满 1000 步拿分。
- **花 reset 的方式不同**（Luna 取和 Sol、Opus 同一版说明的第 3、4 版运行）：Luna 到第 20 分钟中位数用掉 28 次；Sol 多在 5–9 分钟用完；Opus 要么几分钟用完，要么主动停下。三家结束时都剩下大量时间。
- **读 `spec()` 的差别**：Opus 最会用机器人事实（相机位姿、IMU 坐标系），Sol 次之，Luna 基本只用舵机范围；但用对了事实，也没换来控制上的突破。
- **full 里 Sol 强于 Luna**：5 个任务里 4 个 Sol 更高（walk 603.0 对 158.0，cube 过线）；package 相反，差在对终止奖励的取舍。
- **花费差很多**：同样 5 个任务，Sol 每次约是 Luna 的 17 倍（limited）和 24 倍（full）；Opus limited 平均每次 $1.74，但只用了约 10 分钟。

## 改进意见
下面这些改动都只动说明文字、`spec()` 里的机器人事实和我们自己的服务与工具，没动上游的 reward、终止条件和及格线。说明的改动（第 5 版）已用 Luna 重跑了一轮 limited，效果写在各条里。
- **已改：说明写明"这一局没结束不等于没摔倒"**（原 T6）：上游判倒只看一个阈值（walk、maze 骨盆低于 0.2 m，stair 躯干直立度低于 0.1），reach、push、package、cabinet、kitchen、truck 根本不判倒；躺着、坐着没过线，这一局就一直跑到第 1000 步。这一轮 34 个 limited 主运行里有 50 局这样跑满（8 个任务），其中 6 局是被评分段；Opus 的 walk、Luna 的 stair 和 maze 因此把倒地的控制器当成了好的。24 个 limited 说明的结束条件后面都补了一句。
- **已改：服务计时从 agent 第一次请求开始算**（原 T5）：`elapsed_s` 和 `time_s` 原来比 agent 的钟早 52–96 s，insert_normal、spoon、cabinet、door 都据此提前或匆忙收尾；现在只差 agent 启动到它第一次请求之间的这一小段（这轮 73 个 limited 运行里，agent 启动后 7–34 s 内就开始驱动机器人），Claude Code 没有时钟工具也能靠它计时。
- **已改：maze 的 limited 说明补了起点**（原 T4）：写明机器人站在第一个检查点上，那颗球第一步就是绿的，每次 reset 都从那里开始。
- **已改：`spec()` 写明读数的正负号**：IMU 加了"前倾时 gravity x 为正、左倾时 y 为正，陀螺仪前俯为 +y"（已在仿真里实测）；每台相机加了画面向右的方向，房间相机的坐标系补了 "y left"。依据：Luna 在 kitchen、truck、bookshelf、spoon 里反复把前后读反，door、cube、spoon 里把画面左右当成机器人的左右。
- **已改：头部相机的近裁剪面调到 1 cm**：原来是 5.5 cm，door 里靠门蹲时眼部相机离门板约 4 cm，画面穿过门板；改后看到的是门板，房间相机和录像不变。
- **已改：结果工具**：回放记下每一局结束时头比脚高多少，据此在图上分出"结束了但没倒"（工具掉了、人还站着，window 旧分析因此写错过 5 处）和"步数到上限但已倒"（躺着、坐着跑满 1000 步）；highbar 吊在杠上，头比脚低不算倒，不做这项判断；多阶段任务（cabinet、kitchen、bookshelf、maze、truck、basketball）记下做到第几步，limited 每一局都有，full 从下一轮起写进验证端的 diagnostics.json；整段录像的右栏显示每条驱动机器人的命令和上一条相比改了什么、命令之间 agent 在画面外做了什么，并加了图例。
- **已跑：可选的头部深度**：`RCB_OBS_DEPTH=1` 打开，默认关，标准配置不变；真 H1 头部有 RGB-D 相机。Luna 在 10 个头部相机看得到目标的任务上开着跑了一轮：door 用深度认出了贴脸的是门板（没开时当成了墙），kitchen 用它看出房间画面里手和把手重叠是错觉；bookshelf、truck、basketball、cabinet 读过一两次就不再用，stair、hurdle、room、window 一次没读。没有一个过线，回报 4 个升、5 个降、kitchen 不变。
- **已改：full 说明里多余的半句**："obs and done are real, except where noted below" 只留在确实写了"本容器里不一样"的 5 个任务上。
- **已跑：reset 加到 100 的对照**（原 E1，原计划 200）：第 5 版里 50 次 reset 用完、还剩 20 分钟以上的 16 个任务各跑一次：11 个在 60 分钟内照样把 100 次用完（中位数 19 分钟），多出的 reset 多半用来扫更多参数点，或被自动循环几秒内烧掉；被评分回报 11 个升、5 个降，只多过了 push，而它只用了 14 次。卡在控制，不是卡在 reset。
- **已跑：push 的 limited 重复**：第 3 版过（最后一局盲跑撞上）、第 5 版没过（一次没推动箱子）、reset 100 那次过（同一局里按房间画面里箱子和红块的位置边推边调右肩，第 185 步过线）：三次过两次，两次的路线不同。
- **已跑：用新说明重跑**：见上面 Luna 的 limited 一节：读数方向多数读对了，倒地和时钟的改动各挡住了一部分误判，控制没变，过线数不变（1 个，换了任务）。
- **已改+已跑：cube 的图像改为 512×512**（`RCB_IMAGE_HW`，只对 cube，说明里的图像尺寸和每步耗时一起更新，即第 6 版）：方块一面从约 10–15 px（放大也糊）变成约 40–60 px，头部相机不用裁图就能认出面上的字母；回报 39.08，256 时 36.34，控制还是卡在站稳。
- **已加：跑配置可以写进文件**：`-c scripts/humanoidbench/configs/limited.yaml`（标准配置）或 `limited-depth.yaml`（再加深度），是合进 sim 的 compose override，命令行不用再列一串环境变量；只作用于 sim，agent 的环境里看不到。
- **发现：并行跑多时取图变慢**：12 个运行同时在跑时，一步带两张头部图要约 75–85 ms，空闲时 6 ms（说明里写的是空闲时测的值）；GPU 占用只有 7%，是很多渲染上下文轮流用 GPU 造成的。结束时的回放和录像也跟着变慢，stair 的 agent 收尾时 `status()` 等了 5 s 超时（不影响评分）。以后可以少开几个并行，或者在说明里写明那是空闲时的数。
- **已改：看图记录**：codex 在循环里看图时（`for (const path of [...]) view_image({path})`），现在也记下看的是哪张图、哪台相机（hurdle 从 113 张里 86 张不明降到 12 张）。
- **注意："结束了但没倒"的含义**：依据是结束时头比脚高 1 m 以上；door、cube、sit_hard 里机器人蹲着向后坐倒、或坐在地上时越过了上游的结束线，头仍高于 1 m，也标成这一类。写分析的指南已写明这一点。
