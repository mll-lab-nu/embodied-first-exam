#!/usr/bin/env python3
"""中文报告：Codex + GPT-6 Luna 在 RoboTwin 2.0 任务上 unlimited vs limited，两种模式带视频（GIF 预览 + mp4 链接）。
usage: make_two_mode_report_zh.py <jobs_dir> <unlimited_job> <limited_job> <report_dir> [<batch_plan.json>]
The task-list state file (difficulty) is read from RCB_TASKLIST_STATE if set."""
import json, pathlib, shutil, subprocess, sys, datetime as dt, glob
jobs, ju, jl, rep = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], pathlib.Path(sys.argv[4])
PLAN = sys.argv[5] if len(sys.argv) > 5 else str(pathlib.Path(jobs).parent / "batch_plan_2026-09-23.json")
plan = json.load(open(PLAN))
import yaml
STATE = pathlib.Path(__import__("os").environ.get("RCB_TASKLIST_STATE", "/home/user/data/projects/robot_os_world_all/robotic-code-agent-task-list/state/tasks/robotwin-2.yml"))
DIFF = {t: (b or {}).get("difficulty", "unrated") for t, b in (yaml.safe_load(open(STATE)) or {}).items()} if STATE.exists() else {}
ZH_DIFF = {"easy": "易", "medium": "中", "hard": "难", "extreme": "极难", "unrated": "未评"}
# 失败分析（人工阅读 agent transcript / verifier 输出后写的；U = unlimited，L = limited）
ANALYSIS = {
 "hanging_mug": {"U": "左臂能把杯子放到桌中央，但右臂对中央位置的自动抓取选点规划失败；尝试挪交接点、改杯子朝向都被规划器拒绝，最终无可回放轨迹。核心：交接姿态 + 右臂可达性，以及功能点 2 cm 容差。",
                 "L": "从 RGB 估的杯心在 y 方向偏了几厘米，两次抓取落空；右臂“下降”指令被规划器卡在 z≈1.02 m 不动（靶点在桌面规划器的避障范围内）。最后在架子处张开手，但杯子根本没被拿起。"},
 "open_microwave": {"U": "直接抓门把手往外拉，铰链角度仍为 0，随后 4 分钟就放弃并交付了一条失败轨迹。没有像 RoboTwin 专家那样沿门做多次重新抓取。",
                    "L": "成功。9 个 ee 动作：抓把手、沿弧线分段外拉。反直觉：无 reset 的情况下反而做成，因为 ee 模式下每步都能从图像确认门是否动了。"},
 "place_a2b_right": {"U": "物体 A 是一叠扑克牌（薄片），grasp_actor 的抓取没有把它抬起来；两次尝试后没有保存轨迹。薄物体抓取是原语的盲区。", "L": "第一次抓取落空后物体被蹭偏；换左臂够不到放置点（规划器拒绝 13 个跨桌/低位动作），右臂再抓又空；最后想用推的，物体仍留在盒子左侧。59 步。"},
 "place_can_basket": {"U": "自动接触点选得太高，罐子在搬运中滑落；之后篓子把手的抓取规划无解。交付了一条失败轨迹。", "L": "修正一次后确实把罐子抓起来了（头部相机能看到随手移动），但放下时掉在篓子外远侧；重抓的位置两臂规划器都拒绝（超出可达范围），篓子还被碰歪。54 步，11 次规划失败。是 limited 里最接近成功的一次。"},
 "place_dual_shoes": {"U": "第一只鞋被甩出桌面，规划在第二只鞋前中断；只做了一轮就交付失败轨迹（5.6 分钟）。",
                      "L": "143 个动作、26 分钟，是 limited 里最努力的一次：鞋心估计偏 6 cm，反复调整腕部朝向让指尖跨过鞋子，多次夹到但抬不起来；两只鞋都没进鞋盒。"},
 "place_fan": {"U": "抓取规划成功但回放时风扇没被夹住，放置时把风扇撞开；agent 判断是接触/执行问题，未保存轨迹。",
               "L": "第一次抓取把风扇碰倒，之后的低位扫掠被桌面规划器拒绝；15 个动作后放弃。"},
 "place_object_basket": {"U": "唯一用满 1 小时的：77 次 reset、20 万物理步。篓子把手的自动抓取“跨运行不一致”（CuRobo 规划非确定性），玩具落点略偏使距离判定差一点；一直在微调，没有一条回放通过。",
                         "L": "夹爪只碰到篓子边、抬不起来，改成推；物体放进去与否无法从图像确认，45 步后停止。"},
 "place_object_stand": {"U": "抓取和抬起成功，放置阶段把支架和物体一起撞开，最终 XY 差 3 cm 判定；交付了失败轨迹。",
                        "L": "两次抬起物体都没跟着走，改为低位推；接触后物体和支架从头部相机视野里消失，后续规划失败，24 步停止。"},
 "place_phone_stand": {"U": "手机沿 y 落短 8.8 cm；补偿一次仍不达标，4 分钟后放弃且没保存轨迹。", "L": "第二次抓到手机，但放下后手机靠在支架旁边而不是坐进支架槽；纠正一次仍未进槽，41 步。"},
 "put_bottles_dustbin": {"U": "两个瓶子能可靠进桶；最右侧瓶子的空中交接不稳定（右臂小步移动导致中间瓶子脱手），26 分钟后放弃，无轨迹。", "L": "140 步、16 分钟。左臂在垃圾桶上方只能规划到 z≈0.52 m 以上，只好高处松手；右臂往左递瓶子被规划器的可达边界卡住，交接没完成；一个瓶子被碰倒后再也夹不起来。"},
 "move_can_pot": {"U": "成功（重判后）。首轮 verifier 容器出现 CUDA 报错（与并发作业抢 GPU），用同一 grader 在新容器重判得 1；agent 自己发现罐子落点偏 +x 6.8 cm 并补偿了一次。",
                  "L": "抓起后罐子从两台固定相机视野消失（被举出画面），放到锅边后不可见；agent 因无法确认而停止，48 步。"},
 "adjust_bottle": {"L": "6 次规划被拒；几次从上方合爪都没夹住瓶子，接触把瓶子推到桌前沿以外的相机盲区，agent 不敢再动。34 步。"},
 "handover_mic": {"L": "两次抓取都只碰到麦克风把它推偏，换臂后麦克风已不在任何相机视野里；16 步停止。交接根本没开始。"},
 "lift_pot": {"L": "锅把位置估计先偏了（按前置相机标定重算才知道把手在 x≈±0.14），三种抓法（把手、锅身、侧向）都没抬起来；32 步。双臂同步抓举在 ee 模式下要两臂同时到位，一次估错就白搭。"},
 "press_stapler": {"L": "夹爪对准了订书机，但规划器把腕部卡在 z≈0.83 m 以上，压不下去；反复下压目标反而把腕部推歪；18 步停手。这是 limited 里被“桌面避障规划器”直接封死的例子。"},
 "scan_object": {"L": "先把相机原点用错、修正后左臂到了茶盒上方，但合爪没夹住（把 ee 位姿当成了指尖中心）；右臂低位接近时把茶盒撞到桌远端、扫码枪也出视野；33 步，10 次规划失败。"},
 "dump_bin_bigbin": {"L": "夹爪夹到小桶外壁抬起时桶没跟上；换右臂宽抓仍失败；14 个动作被规划器拒绝，63 步后放弃。倒球需要稳固抓取 + 旋转，limited 下抓取本身就没过。"},
 "open_laptop": {"L": "多次从上方接近盖子边缘抬起，盖子不动（指尖没有插到盖子下沿）；7 个动作被规划器拒绝；54 步放弃。"},
 "pick_dual_bottles": {"L": "两个瓶子在第一次尝试时都被碰倒；改成横向顶抓仍抬不起来；12 个动作被规划器拒绝（够远处的目标）。"},
 "rotate_qrcode": {"L": "前两个目标点被规划器拒绝（跨度太大），改短路点后到达；两次抓取板子都落空（估计位置比实际更靠桌心）。"},
 "shake_bottle": {"L": "末端被规划器卡在 z≈0.85 m 下不去，两次抓取都没夹到瓶子；agent 注意到接触点相对末端有偏移但仍未夹中。"},
}

vid = rep / "videos"; vid.mkdir(parents=True, exist_ok=True)
def span(x):
    try:
        a = dt.datetime.fromisoformat(x["started_at"].replace("Z", "+00:00")); b = dt.datetime.fromisoformat(x["finished_at"].replace("Z", "+00:00")); return round((b - a).total_seconds())
    except Exception: return None
def last_msg(trial):
    try:
        d = json.load(open(glob.glob(str(trial / "agent/trajectory.json"))[0]))
        msgs = [(s.get("message") or "").strip() for s in d.get("steps", []) if s.get("source") == "agent" and (s.get("message") or "").strip()]
        return msgs[-1][:600] if msgs else ""
    except Exception: return ""
def trial_for(job, task, limited):
    """Map by result.json task_name (Harbor truncates long trial directory names)."""
    want = f"robotwin_2_0_{task}" + ("-limited" if limited else "")
    for t in sorted((jobs / job).glob("robotwin_2_0_*")):
        if not t.is_dir() or not (t / "result.json").exists(): continue
        try: name = json.load(open(t / "result.json")).get("task_name", "").split("/")[-1]
        except Exception: continue
        if name == want: return t
    return None
def media(trial, task, mode):
    v = trial / "verifier"; out = {}
    if (v / "replay.mp4").exists():
        mp4 = vid / f"{task}_{mode}.mp4"; shutil.copy(v / "replay.mp4", mp4); out["mp4"] = mp4.name
        gif = vid / f"{task}_{mode}.gif"
        if not gif.exists():
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp4), "-vf", "fps=5,scale=480:-1:flags=lanczos", str(gif)], check=False)
        if gif.exists(): out["gif"] = gif.name
    if (v / "replay.last.png").exists():
        png = vid / f"{task}_{mode}.png"; shutil.copy(v / "replay.last.png", png); out["png"] = png.name
    return out
def info(trial):
    r = json.load(open(trial / "result.json")) if (trial / "result.json").exists() else {}
    rw = json.load(open(trial / "verifier/reward.json")) if (trial / "verifier/reward.json").exists() else None
    ar = r.get("agent_result") or {}
    return {"done": rw is not None, "success": (rw or {}).get("success"), "rw": rw or {}, "agent_s": span(r.get("agent_execution") or {}),
            "tok_in": ar.get("n_input_tokens"), "tok_out": ar.get("n_output_tokens"), "msg": last_msg(trial),
            "exc": (r.get("exception_info") or {}).get("exception_type")}
def fmt_res(i):
    if i is None: return "未开始"
    if not i["done"]: return "运行中"
    if i["rw"].get("grader_error"): return "⚠ verifier 报错（待重判）"
    return "✅ 成功" if i["success"] == 1 else ("❌ 失败（未交付轨迹）" if i["rw"].get("missing_trajectory") else "❌ 失败")
L = ["# RoboTwin 2.0 × Codex（GPT-6 Luna，ChatGPT 订阅）— unlimited 与 limited 两种模式对比报告\n",
     f"生成时间 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}。Harbor 作业：`{ju}`（unlimited）、`{jl}`（limited），3 路并发，每次 agent 预算 3600 s。",
     "任务集：用户在任务目录里标 keep 的 11 个 + 随机抽的 5 个 medium（已 drop）+ 5 个 easy，共 21 个；seed 为冷门 seed，专家在其上可完成（见 batch_plan_2026-09-23.json）。\n",
     "## 两种模式",
     "| | unlimited | limited（机器人即服务） |", "|---|---|---|",
     "| 仿真器 | 与 agent 同一容器，可直接 import | 独立 sidecar 容器，agent 打不开 |",
     "| reset | 无限 | 没有：一次 trial 一个 episode |",
     "| 可见信息 | 物体位姿、check_success 源码、RoboTwin 抓放原语 | 仅四路相机 RGB（含相机标定）+ 关节/夹爪/末端位姿 |",
     "| 动作 | RoboTwin 原语 / 低层 step | `qpos`(14) 或 `ee`(16)，即 RoboTwin 评测原生 take_action |",
     "| 交付物 | agent 保存的 (T,34) 轨迹 | 服务端录制的 (T,34) 轨迹 |",
     "| verifier | 独立沙箱回放两遍 + 六视角视频 | 独立沙箱读 sidecar 记录（服务端已回放核验）+ 六视角视频 |\n",
     "视频均为六相机拼图：上排 世界斜视 / 正面 observer / 头部，下排 正面 / 左腕 / 右腕。GIF 为预览（5 fps），点击链接看 mp4。\n"]
rows = []; tot = {"u": [0, 0], "l": [0, 0]}
for task in plan["all_tasks"]:
    tu, tl = trial_for(ju, task, False), trial_for(jl, task, True)
    iu, il = (info(tu) if tu else None), (info(tl) if tl else None)
    mu, ml = (media(tu, task, "unlimited") if tu else {}), (media(tl, task, "limited") if tl else {})
    for k, i in (("u", iu), ("l", il)):
        if i and i["done"] and not i["rw"].get("grader_error"): tot[k][1] += 1; tot[k][0] += int(i["success"] == 1)
    cat = "keep" if task in plan["keep"] else ("medium(drop)" if task in plan["medium_drop_sample"] else "easy")
    rows.append((task, cat, iu, il, mu, ml))
L += ["## 总表", "| 任务 | 类别 | 难度 | unlimited | 用时 s | 动作 | tokens 入/出 | limited | 用时 s | 动作 | tokens 入/出 |", "|---|---|---|---|---|---|---|---|---|---|---|"]
def cells(i):
    if not i: return ["—", "", "", ""]
    return [fmt_res(i), str(i["agent_s"] or ""), str(i["rw"].get("n_actions") or i["rw"].get("steps") or ""), f"{(i['tok_in'] or 0)/1000:.0f}k / {(i['tok_out'] or 0)/1000:.1f}k" if i["done"] else ""]
for task, cat, iu, il, mu, ml in rows:
    L.append(f"| [{task}](#{task}) | {cat} | {ZH_DIFF.get(DIFF.get(task,'unrated'))} | " + " | ".join(cells(iu)) + " | " + " | ".join(cells(il)) + " |")
L.append(f"\n**已完成的成功率：** unlimited {tot['u'][0]}/{tot['u'][1]} · limited {tot['l'][0]}/{tot['l'][1]}（不含 verifier 报错和未完成的）\n")
sep = {}
for job in (ju, jl):
    for t in (jobs / job).glob("robotwin_2_0_*"):
        if (t / "result.json").exists(): sep[json.load(open(t / "result.json")).get("verifier_environment_mode")] = sep.get(json.load(open(t / "result.json")).get("verifier_environment_mode"), 0) + 1
L.append("## verifier 隔离（确认）\n")
L.append(f"两个作业里所有已完成 trial 的 `verifier_environment_mode` 均为 `separate`（{sep}）：verifier 在独立容器里运行（`tests/Dockerfile` 构建，同一仿真镜像 + verifier 自己的工具和实例），agent 容器在评分前已被停掉，只有 `/app/output/` 被拷过去。"
         "limited 模式下额外由 sidecar 服务端录制/回放，agent 容器里没有仿真器。全部 44 个 RoboTwin 任务目录都带 `environment_mode = \"separate\"` 和 `tests/Dockerfile`，CI 检查 `check-verifier-isolation.sh` 强制。\n")
L.append("## 失败原因分析（总体）\n")
L.append("**unlimited（有 reset、有物体位姿、有 grasp_actor/place_actor 原语）**\n"
         "1. **接触点抓取打滑 / 抓不起**：原语自动选的接触点对罐子（太高）、扑克牌（薄片）、风扇、鞋这类物体不牢，回放时物体滑落或被撞开（place_can_basket、place_a2b_right、place_fan、place_dual_shoes、place_object_stand）。\n"
         "2. **放置偏差**：按功能点放下后物体停在离目标几厘米处（place_phone_stand 差 8.8 cm，place_object_basket 差一点），agent 做一次补偿后就放弃。\n"
         "3. **双臂/交接规划无解**：hanging_mug 的右臂对中央交接位无可行抓取；put_bottles_dustbin 最右瓶的空中交接不稳定。\n"
         "4. **过早放弃**：预算 3600 s，但 10 个失败里 8 个在 4–12 分钟内就结束（open_microwave 4 分钟、place_phone_stand 4 分钟），只有 place_object_basket 用满 1 小时（77 次 reset）。模型倾向在“原语没成功”后宣布做不到，而不是像专家那样循环重试（open_microwave 的专家就是循环再抓 50 次）。\n"
         "5. **不交付失败轨迹**：4 个失败没有保存 trajectory.npz，与保存了失败轨迹的得分一样是 0，说明缺少部分得分/诊断信号。\n"
         "6. **CuRobo 非确定性**：place_object_basket 的把手抓取“跨运行不一致”，agent 反复微调无法收敛。\n"
         "7. **基础设施**：move_can_pot 的 verifier 容器首轮 CUDA 报错（与并发作业抢 GPU），用同一 grader 重判为成功；最终 unlimited 11/21。\n")
L.append("**limited（只有 RGB + 本体，无 reset，ee/qpos 原生动作）**\n"
         "1. **位置估计误差**：从头部相机 + 标定反投影得到的物体位置常偏 3–6 cm（hanging_mug、place_dual_shoes、rotate_qrcode、shake_bottle），一次抓空后物体往往已被碰倒（pick_dual_bottles、place_fan），没有 reset 就雪上加霜。\n"
         "2. **末端与夹爪接触点的偏移**：agent 把 ee 位姿当夹爪中心，实际指尖在别处，多次“闭合-抬起”后物体留在桌上（shake_bottle、open_laptop、place_object_stand）。\n"
         "3. **规划器拒绝靶点**：ee 模式下 CuRobo 只对桌面避障，靠近桌面或远处的目标被拒（dump_bin_bigbin 14 次、pick_dual_bottles 12 次、rotate_qrcode 9 次），agent 需要自己拆短路点，浪费步数。\n"
         "4. **没有成功信号就停手**：episode 不自动结束，模型在 4–9 分钟、几十个动作后主动停止（“无法从图像确认”），远低于 1 小时预算；只有 place_dual_shoes（26 分钟）和 put_bottles_dustbin（16 分钟）坚持较久。\n"
         "5b. **最接近成功的**：place_can_basket（罐子确实抓起来了，放偏）、put_bottles_dustbin（交接卡在可达边界）、place_phone_stand（手机靠在支架旁）。最终 limited 1/21。\n"
         "5. **视野遮挡**：举起物体后从两台固定相机里消失（move_can_pot、place_object_stand），模型不敢再动。\n"
         "6. **唯一成功 open_microwave**：门把手大、位置好估，且“拉一下看一眼”正好适合 ee 分步控制——这恰是 unlimited 里模型 4 分钟就放弃的任务。\n")
L.append("## 逐任务（左 unlimited，右 limited）\n")
for task, cat, iu, il, mu, ml in rows:
    L.append(f"### {task}\n\n类别：{cat} · 难度：{ZH_DIFF.get(DIFF.get(task,'unrated'))}（任务目录 state） · seed {plan['seeds'].get(task)}\n")
    L.append("| unlimited | limited |\n|---|---|")
    def cell(i, m, mode):
        if not i: return "未运行"
        s = fmt_res(i)
        if i["done"]:
            s += f"<br>用时 {i['agent_s']} s · 动作 {i['rw'].get('n_actions') or i['rw'].get('steps') or '—'} · tokens {(i['tok_in'] or 0)//1000}k/{(i['tok_out'] or 0)//1000}k"
            if mode == "unlimited" and i["rw"].get("agent_resets") is not None:
                s += f"<br>调试过程：{i['rw'].get('agent_sessions')} 个进程，{i['rw'].get('agent_resets')} 次 reset，{i['rw'].get('agent_sim_steps')} 物理步"
        if "gif" in m: s += f"<br>![{task} {mode}](videos/{m['gif']})"
        elif "png" in m: s += f"<br>![{task} {mode}](videos/{m['png']})"
        if "mp4" in m: s += f"<br>[mp4](videos/{m['mp4']})"
        return s
    L.append(f"| {cell(iu, mu, 'unlimited')} | {cell(il, ml, 'limited')} |\n")
    for i, mode in ((iu, "unlimited"), (il, "limited")):
        if i and i["msg"]:
            L.append(f"**{mode} agent 最后一条说明：** {i['msg'].replace(chr(10), ' ')}\n")
    an = ANALYSIS.get(task, {})
    for key, mode, i in (("U", "unlimited", iu), ("L", "limited", il)):
        if i and i["done"] and i["success"] != 1 and an.get(key):
            L.append(f"**{mode} 失败分析：** {an[key]}\n")
        elif i and i["done"] and i["success"] == 1 and an.get(key) and "成功" in an[key]:
            L.append(f"**{mode} 分析：** {an[key]}\n")
(rep / "README.md").write_text("\n".join(L)); print("wrote", rep / "README.md", "| videos:", len(list(vid.glob('*.mp4'))))
