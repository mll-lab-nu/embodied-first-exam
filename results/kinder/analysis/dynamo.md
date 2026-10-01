**一句话**：dynamo 是流程夹具：把底座中心开进地上的绿色方格就过，三把椅子挡路但推得动；limited 没有 room_camera，底座相机朝下只照到脚前地板，要先让绿格进画面。limited 只看底座相机、按里程计把房间一条条扫过去，第 719 步在底座图右上角看到绿格，斜行 5 步，ep0 第 724 步过，50 次 reset 一次没用；full 从环境配置读到绿格坐标，绕椅子走航点，135 步过。GPT-6.1 Sol 两种模式都过：limited 抬起腕部相机找格，第 183 步；full 直线开过去推开椅子，第 50 步。

## GPT-6 Luna
### limited
- **只用低头的底座相机，靠走遍房间找格**：开头原地转一圈拼成 12 格，只有脚前地板（0.53 min "The sweep found no chair or colored marker within the base camera’s close view"）；之后按里程计直行到墙、再沿几条直线横扫，每隔几步看一张底座图，4.19 min 起用像素颜色计数筛图。腕部相机只在开头看过一张，手臂和夹爪动作全程为 0，`end_effector` 只出现在 `spec()` 的打印里。
- **第 719 步才看到绿格**：5.32 min 认出椅子那一排（"The chair row is now visible around x≈4.2 m"），在 x 4.40 沿 −y 分 8 段扫回，最后一张 `neg_lane_7`（y −1.95）右上角是绿格，绿色掩码 18707 像素；这时离 1000 步上限只剩 281 步。
- **按像素估方向进格**：5.93 min "it is roughly 0.7 m forward and 0.3 m toward negative y"，没做 FK 或地面求交，发 (0.09, −0.04) 斜行，第 724 步 `success`，里程计 (4.79, −2.13)。
- **reset 没派上用场**：`resets_left` 始终 50，找格和进格都在 ep0 里做完；`gen.py` 是成功后把这一局的批次原样写下来（6.21 min "a runnable replay of the successful episode"），不是先探路再回放。
### full
- **读配置、绕椅子**：从环境的 `task_config` 读到 `ground_goal_region` (3.45–4.2, 3.45–4.2) 和三把椅子的坐标，航点从椅子西侧、北侧绕到绿格东北面开进（NOTES："This avoids chair contact"）。
- **一次失败后放宽容差**：第一版要精确到达 y 4.8 的航点，在北墙 y≈4.7 停住、跑满 1000 步；改成 12 cm 内算到达后 135 步过，两次独立回放一致。
### 两种模式
- **分界在知不知道绿格在哪**：full 一开始就有坐标，只需绕开椅子；limited 724 步里约 719 步在找格，靠扫线经过绿格附近、又看了那张底座图才过。

## GPT-6.1 Sol
### limited
- **先抬腕部相机**：开头只给关节 4 加 47 步把手臂抬起，第 47 步的腕部图里就同时看到椅子和绿格（1.05 min "the green square partly visible to the right"）；按 `spec()` 的关节位置和相机位姿写 FK，把腕部深度反投影到地面，绿格中位点 (4.745, −2.810)，走近后 3691 像素时是 (4.787, −2.775)。
- **按坐标绕到椅子右侧**：2.00 min "there’s room to approach from the right side of the chairs"，沿 y −3.455 越过椅子，再向 +y 平移，ep0 第 183 步 `success`，里程计 (4.728, −2.772)。
- **reset 没用**：一局就过，3.8 min、$0.2067；`gen.py` 是成功后把 183 个动作合成 11 段写下来。
### full
- **读配置直开**：从 `task_config` 读到 `ground_goal_region` (3.45–4.2, 3.45–4.2)，每步把底座朝 (3.8, 3.8) 开、x/y 各限 0.1 m，不绕椅子，NOTES："The base pushes chairs 1 and 3 aside"。
- **第一版即成功**：50 步 `success`，两次新进程回放一致，1.5 min、$0.0988。
- **几乎不看图**：只看了 `topdown`、`task_view` 两张图；目标和底座位置都从状态读，椅子在观测前 48 维里，它没去用。
### 两种模式
- **两边都很快**：full 知道绿格坐标、直接推开椅子，50 步；limited 抬腕后一张图就看到绿格、用深度量出坐标再绕椅子，183 步。和 GPT-6 Luna 的 limited（只用底座相机扫房间，第 724 步）比，差在先抬不抬腕部相机。

## 对照实验
- **无 reset 的对照没过**（ep0 第 1000 步 `failed`）：同样只看底座相机扫线，但第 188 步之后改成 30 步一批、`images=False`，后 812 步只看了 3 张图，靠底座碰巧压进方格；这次进格的 (4.79, −2.13) 所在那一块只被三条线围着开过，y 约 1.0–1.65 一线却开了三趟，1000 步在 5.62 min 用完时还在扫。

## 和旧版比
- **旧版（50 次 reset，没有抓取点）抬起了腕部相机**：第 119 步在腕部图里看到绿格，FK 加地面求交定位，第 165 步过；这次只看底座相机，第 724 步才过。这题不动夹爪，`end_effector` 两次都没用上，差别在找格的办法。第一版有 room_camera，第 67 步就过。
