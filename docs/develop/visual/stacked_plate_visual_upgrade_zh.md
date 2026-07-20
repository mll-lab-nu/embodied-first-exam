# Stacked Plate 观感升级

> 日期:2026-07-13
> 背景:untangle/cable 观感改造阶段完成后,对 stacked_plate 做同类升级。任务=旋转上盘(revolute 关节)密封孔列,纯摩擦抓方柱。

## 纪律红线(摸底确认)

该任务有刚体 solver NaN / 初始碰撞体重叠 / 圆柱 pole 打滑的血泪调参史(方柱 20mm、URDF 单链、collision_radius_scale 0.98、noslip 迭代等)。**升级一律为无碰撞视觉件,碰撞体/URDF/关节几何一律不动**——与 cable_routing"装饰与碰撞分离"同配方。落点:`StackedPlateSceneBuilder._add_visual_details`(build 末尾、finalize 前),config `task.visual_details`,各子项独立开关便于按观感裁剪。

## 现状缺口 → 方案(5 项)

| 步 | 缺口 | 方案(纯视觉无碰撞) | 状态 |
|---|---|---|---|
| C1 | 看不见"绕什么转"(轴禁用,防杆穿无孔实心盘) | 每层盘心加**轴承盖 hub**(外盖盘 r0.020 + 深色芯 r0.008) | ✅ 已实施 |
| C2 | 支座=黑圆柱 | 支座脚加**无碰撞底法兰盘**(r0.066×h0.004,工业灰;仅 support 启用时) | ✅ 已实施 |
| C5 | 旋转量不可读 | 各盘缘 0° 位加**刻度小方块**(对齐=初始配准;顺带利好 VLM 读旋转) | ✅ 已实施 |
| C3 | 手柄=裸方柱 | 柱顶旋钮帽 | ⏸ 暂缓:帽扣在**被夹爪抓取的 pole 顶端**会与手指视觉穿插,需你 viewer 定夺形制/位置 |
| C4 | "孔"=0.4mm 平贴片,非通孔 | 双层视觉(外环+深色内盘,微凹观感) | ⏸ 暂缓:孔标记烘焙在**plate URDF 生成器**内(脆弱路径),值得单独一步+独立门 |

## 门

`stacked_plate_physical_rotate_demo` headless build + 步进 30 步无 NaN/崩溃(视觉件加入后物理稳定性不变);其 success/quality 指标(rotation/tab_follow_error/release drift)为后续数值门。观感由用户 viewer 定,C1/C2/C5 各项可 config 关。

## 命令(用户 viewer 观感 + 裁剪)

```
python -m prototypes.stacked_plate_physical_rotate_demo --viewer --backend gpu --verbose
```
看:盘心轴承盖、支座法兰、盘缘刻度;逐项若不合意 `visual_details.<项>.enabled: false` 关。确认方向后再做 C3(旋钮)/C4(通孔)。
