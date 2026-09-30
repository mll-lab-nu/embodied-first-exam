"""KinDER (TidyBot++; MuJoCo, and two kinematic PyBullet tasks): an episode succeeds or not; no return, no pass mark."""
from __future__ import annotations

try:
    import tomllib
except ModuleNotFoundError:   # Python < 3.11
    import tomli as tomllib

from bench import Bench
from common import esc


class Kinder(Bench):
    name, title, short = "kinder", "KinDER", "kinder"
    standard = {"limited": {"budget_min": "60", "resets": "50", "obs": "cams+proprio+depth", "effort": "medium"},
                "full": {"budget_min": "60", "resets": "", "obs": "state", "effort": "medium"}}
    cameras = {"robot_base": ("底座相机", "left"), "robot_wrist": ("腕部相机", "right"), "room_camera": ("外部相机", "room")}
    camera_files = (("room_camera", r"room|task_view"), ("robot_base", r"robot[_-]?base|base[_-]?cam"),
                    ("robot_wrist", r"robot[_-]?wrist|wrist[_-]?cam"))
    leak_words = r"kindergarden|site-packages/kinder|goal_state|_check_goals"
    video_note = "10 fps（MuJoCo 是实时速度）"
    episode_fields = ("exact", "video", "poster", "video_every")   # PyBullet episodes: a frame every video_every steps
    info_example = "tossing"

    def task_info(self, family: str, row: dict, readme: str) -> dict:
        d = tomllib.load(open(f"{self.scripts}/subset.toml", "rb"))
        t = next((t for t in d["task"] if t["family"] == family), {})
        return {"env": row["upstream env"], "fixture": row["role"] == "fixture",
                "max_steps": t.get("max_steps", d["defaults"]["max_steps"])}

    def task_label(self, t: dict, full: bool = True) -> str:
        return f'<div class="mut">{esc(t["env"])}{" · 夹具" if t["fixture"] else ""}</div>'

    def hero(self, t: dict) -> tuple[list[str], str]:
        chips = [f'<span class="chip">{esc(t["env"])}</span>'] + (['<span class="chip">夹具</span>'] if t["fixture"] else [])
        return chips + super().hero(t)[0], ""

    def intro(self, tasks: list) -> str:
        n_fix = sum(t["fixture"] for t in tasks)
        return (f'<p class="sub">coding agent 在 {len(tasks)} 个选定的 KinDER 任务上的表现（TidyBot++ 移动机械臂，MuJoCo 动力学仿真；'
                "其中两个是 PyBullet 运动学仿真；" f"{len(tasks) - n_fix} 个计分" + (f" + {n_fix} 个夹具" if n_fix else "")
                + "）。两种模式：limited 模拟真机，只给机器人自己的"
                "传感器（见下面的表），reset 最多 50 次；full 里它有仿真器和完整状态，reset 不限，交一条轨迹由验证端回放。判定只看 KinDER 自己的目标检查，"
                "没有回报和部分分。</p>")

    def limited_info(self, cam) -> tuple[list[tuple], str]:
        rows = [
            ("任务说明", "目标和成功条件（写清楚要放到哪、边距多少）；episode 什么时候结束（成功、步数上限、时间到）", "真机任务本来就有的要求",
             "<code>the cube's centre is inside the bin's goal region</code>"),
            ("机载相机", "底座和腕部两台 RGB，480×640，腕部另有逐像素深度（米）；要了才给（<code>images=</code>）",
             "底座是 RGB 网络摄像头，腕部是 Gen3 的 RGB-D 模块", cam("robot_wrist")),
            ("外部相机（标准配置不给）", "可选开关：房间里固定的一台 RGB，不从天花板往下拍；真机 TidyBot++ 没有它，要看远处得自己转底盘、抬腕部相机",
             "实验室里架的相机", cam("room_camera")),
            ("本体", "底盘里程计（起点坐标系下的位姿和速度）、7 个臂关节的角度和角速度、夹爪实际开合（PyBullet 是运动学仿真，没有速度）",
             "编码器和里程计",
             '<code>obs["proprio"]["base_pose"]</code>：起点时是 (0, 0, 0)'),
            ("<code>spec()</code>", "每个动作分量的含义和上下限，臂关节的转轴、位置、限位和力矩上限，夹爪抓取点，每台相机的视场和位姿；"
             "控制频率、步数上限、reset 次数；PyBullet 机器人还写明抓取、松手和碰撞的规则",
             "真机说明书里本来就有", "底盘每步最多 0.1 m、0.1 rad"),
            ("每步的状态", "这一局走了几步；结束没有、为什么（success / failed / timeout / error）；还剩几次 reset；过了几秒；"
             "PyBullet 机器人某步因碰撞没执行时标 <code>blocked</code>", "控制器本来就知道",
             '<code>done=True, reason="failed"</code>（1000 步没成功）'),
            ("不给", "物体和目标区域的位置；世界坐标（里程计从起点算）；结束前的成功判定；质量、摩擦；仿真器本身", "真机上没有", "只能从相机、本体推"),
        ]
        return rows, ("能做的只有 <code>step</code>（一步：底盘、臂关节的增量和夹爪命令，可以批量）和 <code>reset</code>"
                      "（50 次，回到逐位相同的起始状态：找东西、标定放在前面几局，被评分的一局只做执行；对照实验不给 reset）。任一局成功就通过，否则失败；墙钟 60 分钟，请求之间仿真时间不走。")


BENCH = Kinder()
