**一句话**：难在贴着书架先站稳，再把第一个物体 trophy 从隔板上拿起、放到它的目标位；GPT-6 Luna 两种模式都站住了、都没抬起 trophy：limited 641.18，full 793.15（线 2000）；GPT-6.1 Sol limited 75.82（被评分一局只站了 100 步，最好一局 767.48）、full 882.78（放上了 trophy，`progress` 到 1）。

## GPT-6 Luna
### limited
- **IMU 反馈站住**：髋俯仰 IMU 反馈加更负的踝目标，ep11（3.9 min）起能站满 1000 步，51 局里站满的有 34 局。
- **看图伸手没抓起**：放大 room_camera 手动调手臂和手指，够到了几层隔板，13.86 min 仍说 "the first peg has not visibly left its shelf"；51 局 `progress` 都是 `{"task_index": 0}`。
- **reset 交给脚本空转**：`gen.py` 在 5 条接近-抓-抬-放路线间轮换，ep21–49 的 29 次 reset 在 2.3 min 内跑完，回报 659.74–668.23，没据失败改参数。
- **被评分的是半自动一局**：ep50 前 522 步是脚本、之后用 Ctrl-C 停掉改手动，站满 1000 步，641.18，低于脚本整局最高的 679.48（ep12）。
- **新 spec 事实只打印**：打出了关节位置、连杆质量质心、脚的碰撞盒，代码只用 `qpos.range`，站姿全靠 IMU 反馈调。
### full
- **从状态里读出目标**：读上游 `bookshelf.py` 和实例状态，得出顺序 trophy、book_c、chalk、book_e、book_b 和 trophy 目标 `[0.75, -0.25, 1.55]`；踝加躯干俯仰反馈站满 1000 步。
- **碰到了 trophy 但抬不起**：IK 发现隔板挡手（"a solid slab at z≈1.225"），姿态搜索后右手贴上 trophy；张手会推远，合手 "lost contact before the trophy lifted"，左手够不到杯口。
- **交的是手贴着不动**：55.96 min 存下"前倾站姿、右手贴在 trophy 上"，回放 793.15；57.94 min 一个把 trophy 推近目标（0.45 → 0.368）的变体，60 min 超时前没存上。
### 两种模式
- **都卡在第一个物体**：两边都站满 1000 步、都没放上任何物体；full 的手确实碰到 trophy，回报高 151.97。
- **判断依据不同**：limited 看了 150 张图，只能从放大图里猜物体动没动；full 只看 1 张图，用 trophy 到目标的距离当进度。

## GPT-6.1 Sol
### limited
- **spec 用进了视觉和重心**：双目加 spec 运动学估杆位置，用 `links` 质量算重心做站姿反馈；0.67 min 认定第一件是 "the pink stand on the second shelf"，51 局 `progress` 都是 `{"task_index": 0}`。
- **一局用了 23 min**：ep18（34.5–58.0 min）站到第 978 步，35.95 min "both hands are now aligned around the stem"，41.03 min "The stem hasn’t moved with the hands"，改从上方插、按指尖投影微调，杆仍没动；这局 767.48，高于 GPT-6 Luna 两种模式。
- **重试脚本烧光 reset**：58 min 起 `attempts.py` 每局 reset、站 100 步、找杆，ep19–45 都报 "no stereo stem"，27 次 reset 约 0.9 min 用完。
- **被评分的是 100 步**：ep50 停在脚本的第 100 步、站着，60 min 到点，75.82；用了 50 次 reset，看了 132 张图，$3.2634。
### full
- **放上了第一件**：读上游源码和实例状态得出物体顺序与目标位，自写约束逆动力学站满 1000 步；17.89 min 修掉一个丢手指指令的 bug 后，竖直手掌握住 trophy 的杆、抽出、抬高，并行搜插入位姿，33.36 min trophy 落在顶层目标约 8 cm 处，`progress` `{"task_index": 1}`。
- **book C 握不住**：33.36 min "the adjacent books obstruct the grip"，拨开邻书、竖握、上方钩、两角夹都试了，54.27 min "can lift book C briefly, but it slips during withdrawal"。
- **装包被挡**：1.25 min 和 11.91 min 两次 `pip install osqp`（第二次改用 http 源加 `--trusted-host`）都连不上，改为自写求解。
- **用时**：60.1 min（超时）、$3.1603、136 次工具调用，看了 4 张图；回放 882.78。
### 两种模式
- **full 过了第一段**：full 读得到杆的位姿和接触，离线反复试握法，把 trophy 放上顶层，882.78；limited 一局 23 min 两手对准杆但杆没动，被评分的 ep50 只站 100 步，75.82，`progress` 停在 0。两边都用满 60 min，花费相近（$3.1603 对 $3.2634）。

## 改进意见
- **说明和设置没发现问题**：说明写明第一件放不上回报就封在第一段，GPT-6 Luna 两种模式和 GPT-6.1 Sol limited 的 `progress` 都停在 `{"task_index": 0}`，与此一致（GPT-6.1 Sol full 放上第一件，到了 1）；失败都在抓取。

## 和旧版比
- **第 5 → 7 版 limited**：回报 650.10 → 641.18（最长一局 1000 → 1000 步）；新 spec 事实只打印未用，照样站住、没挪物体。
- **full 重跑**：回报 806.49 → 793.15；同是站姿加手停在 trophy 旁，没抬起。
