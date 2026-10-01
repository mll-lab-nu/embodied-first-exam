## 总体结论
- **主结果是 GPT-6.1 Sol（每个任务每种模式各跑一次）**：10 个计分任务 limited 10/10、full 10/10，夹具 dynamo 两种模式都过；对照 GPT-6 Luna limited 3/10（sweep-simple、sort-blocks、packing-3d）、full 7/10。
- **这个子集对 GPT-6.1 Sol 已经饱和**：limited 用时中位数 12.4 min（4.6–45.5），reset 用了 0–16 次，obstruction-3d、packing-3d 一次没 reset；20 个运行共 $12.76。要区分更强的模型，得换更难的变体或任务族。
- **limited 的通过经审计是正当的**：只调了文档里的 `spec`、`status`、`observe`、`step`、`reset`，回包里没有世界坐标；位置都来自腕部深度反投影加 `spec()` 的正运动学（obstruction-3d 量到的放置区和起点坐标系下的真值一致），shelf 是转底座回头看才找到被挡住的红块。Luna 拿到的信息一样，输在执行（抓取姿态、放置高度、抛掷落点）。
- **GPT-6 Luna**：limited（50 次 reset）3/10，full 7/10；以下几条是 Luna 的情况。
- **reset 用在探索和标定上**：sweep-simple、sort-blocks 花了十几局找东西、标定抓取和放置，写成 `gen.py` 后整局重放，分别在 ep14、ep13 成功。packing-3d 和 dynamo 在 ep0 现场做完，没用 reset。
- **没过的，reset 也没换来成功**：tossing 重放 43 局，抛出的方块都落在箱前；constrained-cupboard 43 局没有一局把杆放进格子；balance-beam 21 局从没测横梁倾角；shelf 21 局放置高度一直在变，方块多放在柜顶；sweep-into-drawer 手动拉开抽屉后，重放时再也夹不住拉手；scoop-pour 勺里一直是空的；obstruction-3d 只用 1 次 reset，一局现场做到时间耗尽。
- **抓取点和 `blocked` 都用上了**：动过手臂的运行都用了 `spec()` 的 `end_effector`（多数直接写死它的值）；PyBullet 的两个把 `blocked` 当作碰撞信号，停下、抬高或换位置再试。
- **不给 reset 就是 0/10**：探索和执行挤在同一个 1000 步的回合里，9 个 MuJoCo 运行都在 6–46 min 用完了步数。full 模式里知道全部坐标、零试错的通过轨迹也要 574–1000 步。这就是标准配置给 reset 的原因：KinDER 的回合是执行任务的时间，本来不包含探索。
- **full 7/10**：读真值和目标检查、离线规划；没过的是两个多步接触任务（sweep-into-drawer、scoop-pour）和 sweep-simple（底盘碰不到 2 cm 方块，刮板夹不稳）。
- **防泄漏**：limited 只用了底座 RGB、腕部 RGB-D、里程计和 `spec()`，22 个 limited 运行的 leak flag 全空；full 读 kinder 包源码是设计允许的。

## GPT-6.1 Sol
主结果。11 个任务两种模式各跑一次（limited 09-30，full 10-01），标准配置。
### limited
- **10/10**：每个任务都先用腕部 RGB-D 和 `spec()` 的正运动学搭出"看到哪、手就到哪"的管线，再看图调抓取；tossing 看落点调了 5 局出手速度，balance-beam 拟合横梁倾角，shelf 碰到柜顶后改成水平送入。
- **reset 用得少**：0–16 次，最多的是 constrained-cupboard（第 8 局摸出倾斜夹取加底盘推入，被评分的 ep16 第 6 根杆手动补上，第 988 步成功）；用时 4.6–45.5 min，$6.28。
- **有两个贴着规则的成功**：constrained-cupboard、sweep-simple 都是夹爪还夹着最后一件时就判了成功。
### full
- **10/10**：读状态和 KinDER 源码，在 `robot_pinch_site` 或 PyBullet 末端上做 IK；tossing 在 MuJoCo 快照上用差分进化搜出手速度，sweep-into-drawer 拉开抽屉后用刮板扫进 5 块。
- **scoop-pour 换了做法**：舀不起来，就把空的绿箱搬到地上、把黄箱推到台边倒进去（第 935 步成功）；目标检查只看方块在不在绿箱里，验证端回放一致。
- **快**：用时中位数 6.4 min（2.7–46.6），$6.48；Luna full 中位数 39.7 min。
### 两种模式
- **两边都过，差在时间**：limited 中位数 12.4 min，full 6.4 min；limited 多出的时间花在用深度找东西和看图校准上。

## GPT-6 Luna
### limited
- **过线的三个**：sweep-simple 在 ep12 标出夹取高度、空夹阈值和松手点，ep14 前 319 步回放脚本、后面现场补夹，第 905 步成功；sort-blocks 11 局调好扫描位、分割阈值和取放顺序，ep13 回放放进两块、现场补夹另两块，第 813 步成功；packing-3d 在 ep0 现场逐件装盘，35 步 `blocked` 都在原局里改了做法，第 1657 步成功。
- **没过的卡在哪**：放置和配平（constrained-cupboard、shelf、balance-beam）、动态动作（tossing 的抛掷落点、scoop-pour 的舀取）、多步接触（sweep-into-drawer 的拉手），以及 obstruction-3d 的节奏：一局里慢慢松手、试错，60 min 到时被评分的 ep1 只走到第 1004 步。
- **时间和 reset**：没过的 7 个都用满了 60 min，reset 用了 1–47 次，没有一个用完 50 次。
### full
- **靠真值和源码**：过线的 7 个都读了物体坐标和目标检查，在模型的 `robot_pinch_site` 或 PyBullet 的末端点上做 IK；tossing 在快照上搜抛掷，shelf 用接触列表找到 45° 手腕，constrained-cupboard 59.25 min 才把第 6 根杆插进去，sort-blocks 交的 1000 步轨迹在最后一步才成功。
- **多步接触没做成**：sweep-into-drawer 41.79 min 才拉开抽屉约 7 cm；scoop-pour 夹得起勺子，舀、铲、掀箱都没送进一块；sweep-simple 用指垫扫了 536 步，0 块进箱。
### 两种模式
- **full 的优势是坐标、目标检查和离线试错**：tossing、balance-beam、shelf、constrained-cupboard、obstruction-3d 只有 full 过了，limited 卡在放置精度、配平和落点上。
- **sweep-simple 反过来**：full 夹不稳刮板、0 块进箱；limited 改用底盘载着逐块搬过去，靠 reset 标定成功。

## 对照实验
- **不给 reset（同一版代码）**：0/10，夹具也没过。9 个 MuJoCo 运行在 6–46 min 用完了唯一一局的 1000 步：tossing 第 658 步才夹住方块，constrained-cupboard 有 340 步耗在 IK 翻腕和卡住的航点上，dynamo 从头到尾没抬腕部相机、1000 步盲扫。两个 PyBullet 运行是时间不够（3000 步里走了 163 和 764 步）。

## 筛选：KinDER 其余的任务族（09-29）
每族一个偏难变体，GPT-6 Luna 每种模式各跑一次；limited 没过的 5 个留进了子集（上表 7–11 行），其余 19 个不再保留。

| 任务族 | full | limited | 去留 |
|---|---|---|---|
| ConstrainedCupboard3D-o6 | ✅（59.5 min） | ❌ | 保留 |
| SweepSimple3D-o10 | ❌ | ❌ | 保留 |
| SortClutteredBlocks3D-o4 | ✅（第 1000 步） | ❌ | 保留 |
| Obstruction3D-o4（PyBullet） | ✅ | ❌ | 保留 |
| Packing3D-p3（PyBullet） | ✅ | ❌ | 保留 |
| Rearrange3D-o2、PickPlace3D、FrankaPickPlace3D | ✅ | ✅ | 不保留 |
| 其余 6 个 PyBullet 族 | 6/6 ✅ | 6/6 ✅ | 不保留：几分钟就过，有的靠半空松手 |
| 4 个 Dynamic2D、6 个 Kinematic2D 族 | 10/10 ✅ | —（2D 没有 limited） | 不保留 |

## 改进意见
- **三个任务的起点几乎就是世界原点**：obstruction-3d (−0.12, 0, 0)、balance-beam (0.036, 0.004)、tossing (0.036, −0.047)，"用起点坐标系挡住记忆里的上游坐标"在这三个任务上基本不起作用；这次 GPT-6.1 Sol 的坐标都能追溯到深度测量，但要稳妥，可以给起点加偏移或随机化。
- **MuJoCo 机器人也可以回 `blocked: false`**：client 文档写明 `blocked` 只有运动学机器人才有，但 shelf、tossing、scoop-pour、sweep-into-drawer 的 agent 都直接读了 `o["blocked"]`，撞上一次 `KeyError` 才改成 `.get`。每个机器人都回这个键，文档更简单，也少一次出错。

## 各版的改动
- **第 1 版 → 第 2 版（09-29）**：场景换成 MimicLabs 实验室（只影响画面）；limited 去掉外部相机，给机器人自己的两台相机，腕部带深度；修了服务端的串帧 bug。
- **筛选（09-29）**：给 KinDER 其余任务族也生成了任务，3D 的都有 limited；修了 Pymunk 回放不确定。结果见上一节。
- **第 3 版，当前（09-29 夜至 09-30）**：
  - 子集定为 11 个：原来 6 个，加筛选里 limited 没过的 5 个；其余任务目录删掉。
  - `spec()` 给出夹爪抓取点（`end_effector`）：TidyBot++ 是指垫合拢处，实测在腕末 link 下 0.2054 m，上游 `pinch_site` 短 2.4 cm。
  - PyBullet 机器人被拒的一步回 `blocked: true`，批量在这一步停。起初判断"没动"用的是逐位相等，底座转过之后 KinDER 撤回时偏航角会留下 1e-17 级舍入，漏报了少数几步；改成 1e-9 的容差，受影响的两个无 reset 运行重跑了。
  - limited 标准配置曾短暂改成不给 reset，结果见对照实验；因为 KinDER 的回合只算执行时间，改回 50 次，和 HB 一致。
  - 按 main 的规范：full 在独立的评分容器里评分，两种模式都只放行模型 API；API key 留在模型网关里，agent 的容器里只有占位符。

## 和旧版比
- **第 2 版（50 次 reset，没有抓取点和 `blocked`）**：计分 2/10（sweep-into-drawer、balance-beam）+ 夹具；这一版 3/10，过的换成了 sweep-simple、sort-blocks、packing-3d，上一版过的两个这次没过。单次运行，看不出抓取点让整体变好，但抓取普遍变快（tossing 首次夹住从 27.24 min 提前到 4.33 min）。
- **第 1 版（白地面、外部相机、没有深度）**：前 6 个 0/5，夹具过了。
