## 总体结论
- **过线**：GPT-6 Luna 在 10 个计分任务上，limited（只有一局、不能 reset）0/10，full 7/10；夹具 dynamo limited 没过、full 过。
- **一局的步数是 limited 的瓶颈**：找东西、试抓、改错都花在这唯一一局里。9 个 MuJoCo 运行（含夹具）都在 6–46 min 用完了 1000 步，远没到 60 min；两个 PyBullet 运行 60 min 到时只走了 3000 步里的 163 和 764 步。tossing 第 658 步才夹住方块；constrained-cupboard 有 340 步耗在 IK 翻腕和卡在一个航点上；sort-blocks 放下第一块时已用掉 791 步。
- **抓取点用上了，没有决定成败**：动过手臂的运行都用了 `spec()` 的 `end_effector`（多数直接写死它的值），抓取比上一版快（tossing 首次夹住从 27.24 min 提前到 4.33 min，50 次 reset 的对照里），但首次合爪仍常落空，成败卡在后面的放置、配平和找目标上。
- **找不到目标仍是一类失败**：dynamo 只看朝下的底座相机、从不抬腕部相机，1000 步没进格；tossing 沿墙来回一趟没看到箱子；shelf 把墙边一件黑色家具当成柜子。
- **reset 买来的是标定和整局重放**：同样的任务给 50 次逐位相同的 reset（对照），过了 3/10。sweep-simple、sort-blocks 靠前十几局标定、再整局重跑脚本；packing-3d 在 ep0 就过了，没用 reset。
- **full 7/10**：读真值和目标检查、离线规划；没过的是两个多步接触任务（sweep-into-drawer、scoop-pour）和 sweep-simple（底盘碰不到 2 cm 方块，刮板夹不稳）。
- **防泄漏**：limited 只用了底座 RGB、腕部 RGB-D、里程计和 `spec()`，22 个运行的 leak flag 全空；full 读 kinder 包源码是设计允许的。

## GPT-6 Luna
### limited
- **一个也没过，卡在哪**：
  - 找目标：dynamo（只扫地板）、tossing（没看到箱子）、shelf（认错柜子）。
  - 步数耗在反复试：constrained-cupboard、sort-blocks、sweep-into-drawer（434 步才夹起一块方块，拉手处三次合爪都空）。
  - 放下之后：balance-beam 三块都放进了区域，却挤在横梁一端，没配平；scoop-pour 勺里一直是空的，最后夹住的是箱壁；sweep-simple 转底盘时发出张开夹爪的命令，丢了方块。
  - PyBullet 的两个是时间不够：obstruction-3d 每次工具调用只发一步，一小时 163 步，托盘上还压着红块就往下放，被拒 10 次；packing-3d 三件都放进了托盘，但方块花了 30 min 才放下，到时 764 步，没被判成功。两者都用上了 `blocked`：停下、抬高或换位置再试。
- **时间和步数**：MuJoCo 的 9 个都用完了 1000 步（6.1–46.4 min），PyBullet 的 2 个都到 60 min（3000 步里只走了 163 和 764 步）。obstruction-3d、tossing、constrained-cupboard、sweep-simple 都是一次工具调用只发一步、边看边走，没有写成批量脚本。
### full
- **靠真值和源码**：过线的 7 个都读了物体坐标和目标检查，在模型的 `robot_pinch_site` 或 PyBullet 的末端点上做 IK；tossing 在快照上搜抛掷，shelf 用接触列表找到 45° 手腕，constrained-cupboard 59.25 min 才把第 6 根杆插进去，sort-blocks 交的 1000 步轨迹在最后一步才成功。
- **多步接触没做成**：sweep-into-drawer 41.79 min 才拉开抽屉约 7 cm；scoop-pour 夹得起勺子，舀、铲、掀箱都没送进一块；sweep-simple 用指垫扫了 536 步，0 块进箱。
### 两种模式
- **full 的优势是坐标、目标检查和无限次试**：limited 的失败多在找目标和试错上，full 开局就有坐标，离线试多少次都行。
- **一局没有退路**：full 过了的 7 个任务，limited 一个也没过，都是在唯一一局里把步数或时间花在了找东西和改错上。

## 对照实验
- **50 次 reset（同一版代码）**：3/10（sweep-simple ep14、sort-blocks ep13、packing-3d ep0）+ 夹具 dynamo（ep0）。过了的两个靠 reset 换来的标定和整局重放；其余 7 个用了 1–47 次 reset 也没过：tossing 重放 43 局都抛不进箱，constrained-cupboard 43 局没有一局六根都进格，balance-beam 21 局都没配平。这也是标准配置不给 reset 的原因：逐位相同的复位真机做不到，它让 agent 拿仿真的确定性来试错。

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
- **MuJoCo 机器人也可以回 `blocked: false`**：client 文档写明 `blocked` 只有运动学机器人才有，但 shelf、tossing、scoop-pour、sweep-into-drawer 的 agent 都直接读了 `o["blocked"]`、撞上一次 `KeyError` 才改成 `.get`。每个机器人都回这个键，文档更简单，也少一次出错。

## 各版的改动
- **第 1 版 → 第 2 版（09-29）**：场景换成 MimicLabs 实验室（只影响画面）；limited 去掉外部相机，给机器人自己的两台相机，腕部带深度；修了服务端的串帧 bug。
- **筛选（09-29）**：给 KinDER 其余任务族也生成了任务，3D 的都有 limited（Franka 和 PyBullet 机器人也只给机器人自己的传感器）；修了 Pymunk 回放不确定。结果见上一节。
- **第 3 版，当前（09-29 夜）**：
  - 子集定为 11 个：原来 6 个，加筛选里 limited 没过的 5 个；其余任务目录删掉。
  - `spec()` 给出夹爪抓取点（`end_effector`）：TidyBot++ 是指垫合拢处，实测在腕末 link 下 0.2054 m，上游 `pinch_site` 短 2.4 cm。
  - PyBullet 机器人被拒的一步回 `blocked: true`，批量在这一步停。第一版判断"没动"用的是逐位相等，底座转过之后 KinDER 撤回时偏航角会留下 1e-17 级舍入，漏报了少数几步（obstruction-3d、packing-3d 的标准运行各 2 步）；改成 1e-9 的容差后，这两个运行重跑了。
  - limited 标准配置改为只有一局、不能 reset；50 次 reset 作为对照。
  - 按 main 的规范：full 在独立的评分容器里评分，两种模式都只放行模型 API。

## 和旧版比
- **第 2 版（50 次 reset，没有抓取点和 `blocked`）**：计分 2/10（sweep-into-drawer、balance-beam）+ 夹具。同样 50 次 reset 的对照是 3/10，但过的换成了 sweep-simple、sort-blocks、packing-3d，上一版过的两个这次没过：单次运行，看不出抓取点让整体变好。
- **`blocked` 修好之前的两个 PyBullet 标准运行**：obstruction-3d 过了（第 408 步），packing-3d 超时；重跑后两个都没过。说明文字和 `spec()` 相同，差在各漏报了 2 步和单次运行本身的波动。
- **第 1 版（白地面、外部相机、没有深度）**：前 6 个 0/5，夹具过了。
