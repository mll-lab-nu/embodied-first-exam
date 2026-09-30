"""HumanoidBench (Unitree H1, MuJoCo): a return against a pass mark, and a robot that can fall."""
from __future__ import annotations

import glob
import json
import re

try:
    import tomllib
except ModuleNotFoundError:   # Python < 3.11
    import tomli as tomllib

from bench import Bench
from common import REPO, esc, num, tip

UP_M = 1.0   # an episode's end: the head this far above the lower foot (m, the replay's final_head_h) or more
             # means the robot was still up (~1.6 standing, ~1.3 crouched; under 1 sitting on the floor or lying)
PROGRESS = {"current_subtask": lambda v: f"柜子做完 {v - 1}/4 格", "task_index": lambda v: f"放好 {v}/5 个物体",
            "maze_stage": lambda v: f"到过 {v}/4 个检查点（含起点）", "stage": lambda v: f"阶段 {v}",
            "tasks_to_complete": lambda v: f"厨房四项还剩 {len(v)} 项", "packages_on_table": lambda v: f"{v} 个包裹上了桌"}


class HumanoidBench(Bench):
    name, title, short, scored = "humanoidbench", "HumanoidBench", "hb", True
    standard = {"limited": {"budget_min": "60", "resets": "50", "obs": "head+joints+imu+room", "effort": "medium"},
                "full": {"budget_min": "60", "resets": "", "obs": "state", "effort": "medium"}}
    cameras = {"left_eye_camera": ("左眼", "left"), "right_eye_camera": ("右眼", "right"), "room_camera": ("外部相机", "room")}
    camera_files = (("room_camera", r"room"), ("left_eye_camera", r"left[_-]?(?:eye|cam)"), ("right_eye_camera", r"right[_-]?(?:eye|cam)"))
    leak_words = (r"humanoid[-_]?bench|\bmujoco\b|dm_control|get_reward|rewards\.tolerance|_STAND_HEIGHT|_WALK_SPEED|"
                  r"_RUN_SPEED|stand_reward|small_control|dont_move")
    video_every, video_note = 2, "25 fps，实时速度"
    episode_fields = ("return", "max_dx", "final_dx", "final_z", "final_upright", "final_head_h", "progress", "video",
                      "poster", "exact")
    texts = {   # the task text a run had, by what its job name ends with. text5 and text6 were a working tree, committed
                # afterwards in e897737 (cube there at text 6); text7 is ef883ec. What each version changed and why:
                # results/humanoidbench/analysis/overview.md, "各版的改动".
        "070fdcf": ("第 1 版", "09-24", "070fdcf"), "06b0ab3": ("第 2 版", "09-24", "06b0ab3"),
        "e95d382": ("第 3 版", "09-25", "e95d382"), "8e09011": ("第 4 版", "09-25", "8e09011"),
        "text5": ("第 5 版", "09-26", "e897737"), "text6": ("第 6 版", "09-27", "e897737"), "text7": ("第 7 版", "09-28", "ef883ec"),
    }
    retired = {"070fdcf", "06b0ab3", "e95d382", "8e09011", "text5", "text6"}   # runs.csv rows: texts 1-2's are in git
                                                                              # at 884d59e, texts 3-6's at c9449ce
    why = {"success": "达到及格线，服务结束了这一段", "below_bar": "交了轨迹，回放没到及格线"}
    diag_what, info_example = "回报、及格线、回放用时", "bookshelf_simple"

    def task_dir(self, family: str, limited: bool) -> str | None:
        found = sorted(glob.glob(f"{REPO}/tasks/humanoidbench-*-{family.replace('_', '-')}-i00{'-limited' if limited else ''}"))
        return found[0] if found else None

    def task_info(self, family: str, row: dict, readme: str) -> dict:
        legend = dict(re.findall(r"(C\d+) ([^·.\n]+?)(?= ·|\.)", readme.split("Classes", 1)[1].split("\n\n", 1)[0]))
        t = {x["family"]: x for x in tomllib.load(open(f"{self.scripts}/subset.toml", "rb"))["task"]}.get(family, {})
        f = json.load(open(f"{self.scripts}/facts.json")).get(family, {})
        d = self.task_dir(family, True)
        compose = open(f"{d}/environment/docker-compose.yaml").read() if d else ""
        pose = re.search(r'RCB_ROOM_CAMERA_POSE:\s*"([^"]*)"', compose)
        cls = row["class"]
        return {"robot": row["robot"], "cls": cls, "fixture": cls == "fixture",
                "cls_name": legend.get(cls, "fixture" if cls == "fixture" else ""),
                "cls_long": (t.get("capability_class") or "").split("·", 1)[-1].strip(), "one_liner": t.get("one_liner", ""),
                "bar": f.get("success_bar"), "nop": f.get("nop_return"), "nop_steps": f.get("nop_steps"),
                "max_steps": f.get("max_steps"), "pose": pose.group(1) if pose else "",
                "camera_note": (t.get("limited") or {}).get("camera_note", "")}

    def task_label(self, t: dict, full: bool = True) -> str:
        if not full:
            return f'<div class="mut">{esc(t["robot"])} · {esc(t["cls"])}</div>'
        return (f'<div class="mut" data-tip="{tip(t["cls"] + " · " + t["cls_long"], t["one_liner"])}">{esc(t["robot"])} · '
                f'{esc(t["cls"])}{"" if t["cls_name"] in ("", t["cls"]) else " " + esc(t["cls_name"])}</div>')

    def hero(self, t: dict) -> tuple[list[str], str]:
        cls = t["cls"] if t["cls_name"] in ("", t["cls"]) else f'{t["cls"]} · {t["cls_name"]}'
        chips = [f'<span class="chip">{esc(t["robot"])}</span>',
                 f'<span class="chip" data-tip="{tip(t["cls_long"] or cls, t["one_liner"])}">{esc(cls)}</span>',
                 f'<span class="chip">及格线 {num(t["bar"], 0)}</span>', f'<span class="chip">全零动作 {num(t["nop"])}</span>',
                 f'<span class="chip">{t["max_steps"]} 步 / episode</span>']
        pose = (f"外部相机位姿 <code>{esc(t['pose'])}</code>（lookat x,y,z · 距离 · 方位角 · 俯仰角）" if t["pose"]
                else "外部相机：录像相机在 t=0 的位姿")
        return chips, (f'<p class="mut" style="font-size:12.5px;margin:6px 0 0">limited 模式的相机（t=0 的三张图在右边）：{pose}</p>'
                       f'<p class="mut" style="font-size:12.5px;margin:2px 0 0;max-width:760px">{esc(t["camera_note"])}</p>')

    def intro(self, tasks: list) -> str:
        return (f'<p class="sub">coding agent 在 {len(tasks)} 个选出来的 HumanoidBench 任务上的表现（{len(tasks) - 1} 个计分 + sit_simple 夹具）。'
                "两种模式：limited 模拟真机，只给真机本来就有的信息（见下面的表），reset 有上限；full 里它有完整的物理状态，reset 不限，"
                "交一条轨迹由验证端回放打分。两种都没有 reward。</p>")

    def limited_info(self, cam) -> tuple[list[tuple], str]:
        rows = [
            ("任务说明", "任务目标；episode 什么时候结束（过线、摔倒、步数到顶、时间到）；及格线，以及回报由哪几项组成（文字描述，没有公式和代码）",
             "真机任务本来就有的要求", "<code>passes iff the summed per-step reward reaches 2000</code>"),
            ("头部相机", "左右眼两张 RGB，256×256（cube 512×512），视场 45°；要了才给（<code>images=</code>）", "H1 头上的相机", cam("left_eye_camera")),
            ("外部相机", "房间里固定的一台 RGB，尺寸同上，位置按任务定", "实验室里架的相机", cam("room_camera")),
            ("关节角和角速度", "每个关节的角度（rad）和角速度（rad/s）：19 个，带灵巧手的任务 69 个", "关节编码器",
             '<code>obs["proprio"]["joint_pos"]</code>：69 个数'),
            ("骨盆 IMU", "角速度和重力方向，骨盆坐标系", "机身 IMU", "站直时 <code>gravity</code> ≈ (0, 0, −1)，前倾时 x &gt; 0"),
            ("<code>spec()</code>", "每个驱动器 ±1 对应的角度，每个关节的转轴和位置，每个连杆的质量和质心，两脚的碰撞框，"
             "IMU 坐标系和各读数的正负号，每台相机的视场和位姿；控制频率 50 Hz、每局步数上限、reset 次数", "真机说明书和 URDF 里本来就有",
             "<code>left_knee</code> −0.26 … 2.05 rad；躯干 17.79 kg；外部相机在起点坐标系的 (−1.61, −1.83, 1.99) m"),
            ("每步的状态", "这一局走了几步；结束没有、为什么（success / failed / timeout / error）；还剩几次 reset；从第一次请求起过了几秒",
             "控制器本来就知道", '第 50 局第 1000 步：<code>done=True, reason="failed", resets_left=0</code>（站满 1000 步，没放上物体）'),
            ("深度（只在对照实验）", "两台头部相机逐像素的深度，米", "H1 头上的 RGB-D 相机", "—"),
            ("不给", "reward 和回报；机器人在房间里的位置和朝向；物体的位姿；接触力；仿真器本身", "真机上没有", "只能从相机、关节和 IMU 推"),
        ]
        return rows, ("能做的只有 <code>step</code>（每个驱动器一个 [−1, 1] 的位置目标，一次是 50 Hz 的一步，"
                      "可以批量）和 <code>reset</code>（50 次，回到同一起始状态）。任一局过线就通过，否则记最后一局；墙钟 60 分钟，请求之间仿真时间不走。"
                      "每个任务 t=0 的三张相机画面在任务页顶部。")

    def obs(self, spec: dict) -> str:
        return ("head+joints" + ("+imu" if spec["imu"] else "") + ("+depth" if spec.get("depth") else "")
                + ("+room" if "room_camera" in spec["cameras"] else ""))

    def down(self, e: dict) -> bool | None:
        h = e.get("final_head_h")
        return None if h is None else h < UP_M

    def progress_text(self, p: dict | None) -> str:
        return "；".join(PROGRESS[k](v) for k, v in (p or {}).items() if k in PROGRESS)

    def ep_lines(self, e: dict) -> tuple[str, str]:
        h, prog = e.get("final_head_h"), self.progress_text(e.get("progress"))
        return (f"{e['steps']} 步 · 回报 {num(e.get('return'))}" + (f" · 骨盆最远前进 {num(e.get('max_dx'))} m" if e.get("max_dx") is not None else ""),
                (f"结束时头比脚高 {h:.2f} m（{'没倒' if h >= UP_M else '已倒或坐在地上'}）" if h is not None else "") + (f" · {prog}" if prog else ""))

    def episode_columns(self) -> list[tuple]:
        n = lambda k: lambda e: f'<td class="n">{num(e.get(k))}</td>'   # noqa: E731
        return [('<th class="n">回报</th>', n("return")), ('<th class="n">最远前进 (m)</th>', n("max_dx")),
                ('<th class="n">最终 x (m)</th>', n("final_dx")), ('<th class="n">结束时头比脚高 (m)</th>', n("final_head_h")),
                ("<th>进度</th>", lambda e: f'<td class="mut" style="white-space:nowrap">{esc(self.progress_text(e.get("progress")))}</td>')]

    def episode_note(self) -> str:
        return ("回报、位移和姿态来自验证端事后回放，agent 看不到。"
                f"x 是骨盆沿世界 x 轴的位移，只在行走类任务里是前进方向；头比脚高 {UP_M:g} m 以上算没倒（站着约 1.6 m，坐在地上或躺下不到 1 m）。")

    def episode_rows(self, task: dict, eps: list) -> list[tuple]:
        # world +x is forward only for the gait tasks (C1, C2); elsewhere (sit_hard's chair is behind) the row would mislead
        if task.get("cls") not in ("C1", "C2") or not any(abs(e.get("max_dx") or 0) >= 0.25 for e in eps):
            return []
        dxs = [e.get("max_dx") or 0 for e in eps]
        return [("骨盆最远前进 (m)", 86, min(0, min(dxs)) * 1.1, max(0.3, max(dxs)) * 1.12, lambda e: e.get("max_dx"))]

    def digest_episodes(self, s: dict, at) -> list[str]:
        v = lambda x: f"{x:.2f}" if isinstance(x, float) else x   # noqa: E731
        L = ["## Episodes (return and displacement from the verifier-side replay, which the agent never saw)", "",
             "Each replay is checked against the live run; ≈ marks one that does not end where the live episode did "
             "(a log from before the service recorded end states rounds actions to 5 decimals: only its graded episode is exact).", "",
             "head_h is the head's height above the lower foot when the episode ended (about 1.6 standing, under 1 sitting "
             f"on the floor or lying): a `failed` episode with head_h {UP_M:g} or more ended without a fall (a tool or an object "
             "dropped). progress: how far a multi-stage task got.", "",
             "| ep | start min | steps | ended | return | max_dx m | final_dx m | final_z m | head_h m | progress | images viewed |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
        up = lambda e: e["end"] == "failed" and (e.get("final_head_h") or 0) >= UP_M   # noqa: E731
        return L + [(f"| {e['ep']} | {at(e['t0'] or s['a0'])} | {e['steps']} | {e['end'] or 'reset by the agent, or running'}"
                     f"{' (robot still up)' if up(e) else ''} | {'' if e.get('exact') or e.get('return') is None else '≈'}{v(e.get('return'))} | "
                     f"{e.get('max_dx')} | {e.get('final_dx')} | {e.get('final_z')} | {e.get('final_head_h')} | "
                     f"{json.dumps(e['progress']) if e.get('progress') else ''} | {e.get('views')} |") for e in s["episodes"]]

    def family(self, task_name: str) -> str:
        return re.sub(r"^humanoidbench-(loco|manip)-|-i\d+(-limited)?$", "", task_name).replace("-", "_")


BENCH = HumanoidBench()
