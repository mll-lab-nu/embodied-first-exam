**一句话**：dynamo 是流程夹具：把底座中心开进地上的绿色方格就过，三把椅子挡路但推得动；新版 limited 没有 room_camera，要先让绿格进画面。limited 开底座、转向时底座相机只看到地板，抬起腕部相机后在 ep0 第 119 步看到绿格，反投到地面斜着开过去，第 165 步过；full 从环境配置读到绿格坐标，绕椅子走航点，135 步过。

## GPT-6 Luna
### limited
- **底座相机只看得到脚下**：spec 里它 0.335 m 高、朝下 45°；直行 2.70 m、左转 1.49 rad 再转回、左移 0.87 m，7 张底座图全是地板（0.69 min "the base camera still sees only floor tiles, so the furniture and goal are outside its near-field view"）。
- **抬起腕部相机才看到**：第 5、4 关节各转约 0.61 rad，1.63 min（第 119 步）的腕部图里出现蓝格上的椅子和右缘的绿格、红格；2.24 min "I found the furniture and green target with the wrist camera"。
- **FK 加地面求交，没用深度**：用 spec 的 `position_m`、`axis` 和腕部相机位姿自写 FK，绿格像素的射线与 z 0 地面求交得 (5.46, −2.42)，隔 10 步重算 (5.48, −2.41)；腕部深度只在 1.97 min 打印过一次统计。看到绿格后 46 步就 `success`，路上没被椅子挡住。
### full
- **读配置、绕椅子**：从环境的 `task_config` 读到 `ground_goal_region` (3.45–4.2, 3.45–4.2) 和三把椅子的坐标，航点从椅子西侧、北侧绕到绿格东北面开进（NOTES："This avoids chair contact"）。
- **一次失败后放宽容差**：第一版要精确到达 y 4.8 的航点，在北墙 y≈4.7 停住、跑满 1000 步；改成 12 cm 内算到达后 135 步过，两次独立回放一致。
### 两种模式
- **分界在知不知道绿格在哪**：full 一开始就有坐标，只需绕开椅子；limited 165 步里前 119 步在找（开底座、转向、抬腕部相机），看到后 46 步就进了格。

## 对照实验
- **有 room_camera 时开局就看到绿格**：同一新场景、腕部深度，另加 room_camera 的对照运行，0.16 min 第一张 room_camera 图里就有绿格，按 spec 的相机位姿反投到 (5.29, −2.00)，分 7 段边开边看，第 64 步过，3.4 min；第一版（白地面、俯视 room_camera、无深度）走 1 步在图里标定方向后估出 (5.06, −2.52)，脚本直开，第 67 步过，2.0 min。
- **没有 room_camera 多了约 100 步**：标准运行 1.63 min（第 119 步）才在抬起的腕部相机里看到绿格，共 165 步、4.4 min，比对照多 101 步；三次都没用 reset。
