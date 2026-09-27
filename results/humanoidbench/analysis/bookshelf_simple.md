**一句话**：难在贴着书架先站稳，再把第一个物体 trophy 从第二层抬到顶层；五局都没放上一个物体。Luna limited 连站都没站住，其余四局站满 1000 步，但手最多把 trophy 推倒拖到半路。

## GPT-6 Luna
### limited
- **这轮（`-text5`）靠 IMU 反馈站住了**：5.44 min 用 `hip += clip(-.8+.8*(.46-gx)-.08*wy - hip, ...)` 撑出前倾站姿，ep17 起能撑满 1000 步；上一轮（`e95d382`）51 局没有一局超过 80 步，回报从 34.70 涨到 650.10。
- **这次没再把后仰读成前倾**：ep0 1.44 min 手臂后倾时它说 "The IMU now shows the pelvis tilted sharply"（`gravity` x 转负正是后仰），不再是上一轮 "leaning slightly forward" 那种反着读；也没有把站满 1000 步误当成任务完成，`progress` 全程 `{"task_index": 0}` 时它仍在继续摸抓取路径。
- **这次卡着 reset 和时间一起用完**：59.56 min `resets_left` 归零、agent 时间只剩 0.4 min（59.6/60）；上一轮 35.4 min 就把 20 次 reset 耗光，还剩约 24 min 没用——这轮没有提前收手，但最后 28 次 reset 也只是把已有的抓取变体又跑了一遍。
- **抓取和物体识别仍没有进展**：42.55 min 自己写"物体是哪个/顺序仍不确定"，被评分的 ep50 回报 650.10，仍是"站满不挪物体"的量级，没有放上任何红色物体。
### full
- **扫站姿加 IK 伸手**：1.43 min 网格扫出站得住的腿部目标 (0.2, 0.6, −0.4)，再用阻尼最小二乘 IK 让左手推、捏、托 trophy，都没抬起。
- **32 min 起改成手停在旁边**：它说手 "blocked by a shelf board"、绕开后 "reach falls short"，决定 "settle for an improved dense-reward trajectory"。
- **交的轨迹不挪物体**：站姿加左手掌停在 trophy 旁约 8.5 cm；它量了骨盆高度、倾角、根速度和手距，没估回报。
### 两种模式
- **这轮两边都站住了**：full 离线网格扫出 (0.2, 0.6, −0.4) 一次就稳，limited 这次也在线用 IMU 反馈摸出前倾站姿（ep17 起撑满 1000 步），只是多花了 5.44 min、经过 15 次摔倒；两边都还是没有抓起 / 挪动 trophy，回报 806.49（full）对 650.10（limited）。

## GPT-6 Sol
### limited
- **固定踝角蹲住**：ep1 起两踝定在 −0.85 rad 就站住了（IMU 反馈只在 ep2–3 用过），跑满 1000 步的 5 局都没倒。
- **靠看图对准，深度总差一截**：room_camera 里手像已压在烛台上，眼部相机却显示还有间隙（17.30、42.97 min）；换手、双手、转腰、转腕都没抓牢。
- **烛台最多歪一下**：33.01 min 它说 "tilted and shifted slightly ... still on the shelf"，57.78 min 仍是 "the lift still left it on the shelf"。
- **被评分段是 48 min 写的开环脚本**：ep49 照跑其中的抓、抬和 "Release at the translucent top shelf location"，之后试的绕隔板路线没写进去。
### full
- **分段随机搜索加 IK/RRT**：先采样站姿，在静态模型上用 IK 和 RRT 规划绕隔板的手臂路径，再从存下的中途状态分支，逐段搜后 4 组常量动作。
- **舵机跟不上规划**：静态可达的钩取姿态一接触就保持不住（"the arm servos did not hold that orientation under contact"），合拢手指只把 trophy 往里推。
- **把 trophy 推倒拖到半路**：最后停在 [0.788, −0.167, 1.354]，按它自己的进度量约 0.52，仍在下层；它自算站稳、手距、进度各项，没估回报。
### 两种模式
- **都卡在抓取**：两边都站住了、都没把烛台抬起；full 能读状态、从中途分支搜索，才把它推倒拖向目标，limited 只让它歪了一下。

## Claude Opus 5.5
### limited
- **IMU 踝反馈 2 分钟站住**：用 `arctan2(-g[0],-g[2])` 算俯仰、反馈到踝，1.23 min 起的 ep2 已站满 300 步，最终参数撑满 1000 步。
- **手臂顶隔板或带着身体转**：前举时右肩命令 −2.4 rad 只到 −0.88（"blocked by the shelf edge"），侧举抬得起但 "the robot rotated too much"，手指从没合拢。
- **高估用时后自己收尾**：3.92 min 以为 "about 27 minutes used"；6.08 min 从 `elapsed_s` 426 s 得知时间还多，只再试 1 局就在 6.67 min 结束会话。

## 模型对比
- **这回都站住了**：Opus 用 IMU 反馈、Sol limited 固定踝角、Luna limited 这一轮也靠 IMU 反馈，两个 full 在仿真里扫目标，都站满 1000 步。
- **没人抓起 trophy，回报挤在一起**：站满 1000 步、不挪物体约 650–710（Luna limited 650、Sol limited 706、Opus 709）；full 贴近或推动 trophy 只多出 100–150。
- **收尾差别大**：Opus 6.7 min 就放弃，另外四个都干到 57–60 min。

## 改进意见
- **已改：服务计时从 agent 第一次请求开始算**：原来从服务启动算，这三局早 52–96 s；Sol 在 59.91 min 读到 3639 s 就说 "just past the stated one hour window"。
- **已跑：depth 打开没有改变结果**：Luna limited 的 `-depth-text5` 里 `obs["depth"]` 在 23.31、50.35 min 被真正读取（两台头部相机的 min/max/中心值、灰度图存下来看过），但两次之后下一步的判断都还是照 room_camera 的 RGB 裁剪图来的，深度数值没有换算成距离进控制；这局 60.0 min 被墙钟切断（`resets_left` 还剩 31，`AgentTimeoutError`），graded 回报 679.82，和 `-text5` 的 650.10 相近，同样卡在 `{"task_index": 0}`——没有解决 Sol 那条"靠看图对准，深度总差一截"的问题。
- **其余问题在 agent 一侧**：题面、及格线和 `spec()` 没发现问题，Luna limited 这轮已经解决站姿，五组跑法的失败原因现在都在抓取。
