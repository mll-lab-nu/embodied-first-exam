# TopoGym 数据集格式（h5_data_format）

> 日期：2026-07-22
> 性质：**对外数据集合约**——逐帧 obs/action/info 的 HDF5 落盘 schema（对标 RoboMME 的 `doc/h5_data_format.md`）。
> 权威来源：`topogym/data/h5_schema.py`（字段定义）+ `topogym/data/episode_dataset_writer.py`（落盘实现）；下游消费形状经 2026-07-21 的 swap→π0.5 (OpenPI) 冒烟端到端验证。
> 2026-09-16 整理：当前格式以 writer/schema 源码为准；旧环境接口、回放与 π0.5 冒烟记录已移至 `legacy/docs/develop/`。下游验证日期仍是历史范围，不表示新版十项任务已经完成训练验收。

`SCHEMA_VERSION = "0.3.0"`（根属性 `schema_version`）。设计原则（承 `robomme_pipeline_roadmap_zh.md` §2）：**群组骨架对 RoboMME 保真、字段取子集、差异成文**。

---

## 1. 群组结构

一个文件 = 一条 episode（嵌在 `episode_0/` 下，将来多 episode 只需加 `episode_1/`…）：

```text
<root>  attrs: schema_version
└── episode_0/
    ├── setup/            (只有 attrs + 少量 dataset，见 §2)
    └── timestep_<K>/     (K=0..N-1，每 every_n_steps 个物理步一帧)
        ├── obs/          <camera_name>_rgb, eef_state, gripper_state,
        │                 is_gripper_close, joint_state, goal_id
        ├── action/       ee_pose_action
        └── info/         (attrs：task_goal, simple_subgoal, is_subgoal_boundary,
                           is_completed, status)
```

---

## 2. `setup/`（episode 身份与元数据）

**attrs**：`stable_id`、`task_id`、`seed`、`preset_id`、`variant_id`、`difficulty`、`task_goal`（语言指令）、`status`（见 env_format §2 枚举）、`success`(bool)、`every_n_steps`、`camera_names`（S 数组）、与相机同序的 `camera_renderers` / `camera_backgrounds`（S 数组）、`frame_dt_s`。

**datasets**（有 `EpisodePlan` 时才写）：`subgoals`（各子目标 label，S 数组）、`waypoints`（(M,3) float32，planner 的稀疏 waypoint 位置）、`waypoint_labels`（S 数组）。

> `stable_id` = `EpisodeKey.stable_id()`，即 `task__preset__seedN__variant`，是可指名寻址的 episode 身份（对标 RoboMME 的 episode 编号）。

---

## 3. `timestep_<K>/`（逐帧）

### 3.1 `obs/`

| 字段 | dtype / shape | 说明 |
| --- | --- | --- |
| `<camera_name>_rgb` | uint8 HxWx3（gzip 压缩） | 按实际选定相机名写入，如 `oblique_rgb`；不能假定总有 `front_rgb` |
| `wrist_rgb` | uint8 HxWx3（gzip） | 腕部相机（render 前调 `update_dynamic_camera` 跟随手臂）；无 wrist 相机时该键缺省 |
| `eef_state` | float32 (7,) | 末端 **xyz + 四元数**(wxyz) |
| `gripper_state` | float32 (2,) | 两指测得的米制半开口；Robotiq 通过控制器换算，不写驱动关节角 |
| `is_gripper_close` | bool | 是否闭合（按开合中点判定） |
| `joint_state` | float32 (7,) | 7 个臂关节 qpos |
| `goal_id` | int64 标量 | 该实例的目标编号 |

### 3.2 `action/`

| 字段 | dtype / shape | 说明 |
| --- | --- | --- |
| `ee_pose_action` | float32 (7,) | **下一帧的绝对末端位姿**(xyz+quat)，即行为克隆目标；最后一帧重复自身 |

`h5_schema.py` 还声明 `ee_rot6d_action`、`gripper_action`。实际 writer 输出以文件为准：本次共享预览的 H5 仅写入 `ee_pose_action`，不能据 schema 声明假定可选动作字段已生成。

### 3.3 `info/`（attrs）

`task_goal`、`simple_subgoal`（当前 `PlannedSubgoal.label`）、`is_subgoal_boundary`（首帧/末帧/子目标标签变化时 True）、`is_completed`（`success and 末帧`）、`status`。

---

## 4. 下游消费（历史验证）

swap H5 经 `scripts/export_h5_lerobot.py` → LeRobot 数据集 → OpenPI/π0.5 训练管线，**2026-07-21 端到端跑通、零 shape/格式错**。映射与经模型 transform 后的**权威形状**：

| H5 字段 | → LeRobot key | → 模型输入（pi0.5，实测） |
| --- | --- | --- |
| `obs/front_rgb` | `image` | `base_0_rgb` (224,224,3) float32（resize 到 224） |
| `obs/wrist_rgb` | `wrist_image` | `left_wrist_0_rgb` (224,224,3)；`right_wrist_0_rgb` 零填充 |
| `obs/joint_state`(7) ⊕ mean(`gripper_state`) | `state` (8,) | `state` (B,32)（pad 到 32） |
| `action/ee_pose_action`(7) | `actions` (7,) | target actions (B,10,32)（horizon 10、pad 到 32） |
| `setup.task_goal` | `task` → prompt | `tokenized_prompt` (B,200) |

---

## 5. 工具

- **写入**：`EpisodeDatasetWriter` / `dataset_writer_or_null`。当前共享场景预览会实际生成 `runs/environment_bootstrap/default_presentation/camera_check.h5`；各任务是否接入采集以其入口实现为准。
- **检查/查看**：`bash bash_scripts/tests/inspect_dataset.sh <path/to.h5>`、`bash bash_scripts/tests/view_dataset.sh <path/to.h5>`，均要求显式传文件。
- **导 LeRobot**：`scripts/export_h5_lerobot.py`，使用独立的 OpenPI/LeRobot 环境；通用配置注册工具 `scripts/register_openpi_config.py` 保留。
- 旧自动采集、旧任务仿真回放与整套训练冒烟已归档，不再作为当前运行入口。

---

## 6. 差异 vs RoboMME（显式成文）

| 维度 | 我们 | RoboMME | 处置 |
| --- | --- | --- | --- |
| eef 旋转 | 四元数 (7) | rpy (6) | 差异；四元数做归一化无意义，属已知 schema 缺口 |
| 动作表示 | `ee_pose_action`(绝对)；schema 另声明 `ee_rot6d_action` / `gripper_action` | joint / ee_pose / **waypoint** / choice 每帧都存 | `waypoint_action`/`joint_action`/`choice_action` **reserved**，产得出再补 |
| oracle 子目标 | `simple_subgoal`(label) | + `grounded_subgoal`(带空间指代) | `grounded_subgoal` reserved |
| 其它 | — | `is_video_demo` 等 VLA 专属 | reserved，不伪造 |
| depth | 无 | 可选 int16 毫米 | 暂不产 |

> 缺口按 `robomme_pipeline_roadmap_zh.md` 的"reserved 而非 dead field"策略处理：字段名沿用 RoboMME、暂不写、在此成文，等真正产得出时补齐。
