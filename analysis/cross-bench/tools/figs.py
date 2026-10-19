"""Chart figures ({{fig:name|k=v}}) over trials, features, reviews and approach labels. Each takes `by` (agent / mode /
agent_mode / bench / outcome; the EFE Task Atlas groupings tasktype / body / cap; category = the bench-level navigation
groups, kept for old text) for the rows and any trial filter (agent=…, mode=…, bench=…, tasktype=…; comma = or).
tasktype and cap are multi-label: a trial counts in the row of each of its values (with_multi says so in 怎么读)."""
from __future__ import annotations
import itertools
import statistics as S
from collections import Counter, defaultdict
import charts as C
import common
import palette as PL
import queries as Q

MODE_NAME = {"privileged": "privileged", "standard": "standard", "standard-realtime": "realtime"}
CAT_NAME = {"tabletop": "桌面", "household": "家居", "dexterous": "灵巧", "dynamic": "动态", "reasoning": "推理", "safety": "安全"}
import json as _json, os as _os, re
from common import HERE as _HERE
CB = _json.load(open(_os.path.join(_HERE, "meta/codebook.json")))
_ld = {k: re.sub(r"^[^：]{1,30}：", "", v) for k, v in CB["approach"]["loop"].items()}   # the legend prints the name already
# Colours (meta/DESIGN.md → Colours): a chart's categories take the palette slots in fixed order (PL.slots: --cat1,
# --cat2, …; 其他 / none / 外部 grey); valence charts keep their meaning with the slot aliases (PL.ALIAS: success --ok
# green, failure --n1 red). Every legend's colours are clearly apart (tools/check.py fails a page where they are not).
# Solving approaches (user 10-18, meta/OUTLINE.md v17; queries.way): three families — Code to Control (开环 / 闭环 /
# 搜索参数), Direct Control (the agent issues commands step by step), Train Model to Control (a trained policy: technique
# rl) — plus 混合 and 无; English names from embodied-first-exam.ai (user 10-18). Names: the loop labels' own "名称："
# (codebook approach.loop) and approach_zh.way (Train Model to Control); families: approach_zh.way_family. Colours, a
# grouped set: the Code to Control members are one blue family (--way-open, --cat1,
# --way-search; the two way tokens come from figs_way.css(), which build.py adds), the other families rust / magenta /
# gold, 无 grey. validate_palette.js in this order (grey aside): ALL PASS light and dark (adjacent normal ΔE ≥ 16.1 /
# 15.6, every pair ≥ 16.1 / 15.6; adjacent CVD ≥ 15.1 / 11.1) — the same tokens as figs_way's wayrate / waypair.
_WZ = CB["approach_zh"]
_lname = lambda code: CB["approach"]["loop"][code].split("：", 1)[0]
WAY_COLOR = {"code-open": "--way-open", "code-closed": PL.BLUE, "search": "--way-search", "agent-segment": PL.RUST,
             "train": PL.MAGENTA, "mixed": PL.GOLD, "none": PL.GREY[0]}
LOOP = [(k, _WZ["way"][k][0] if k in _WZ["way"] else _lname(k), WAY_COLOR[k], _WZ["way"][k][1] if k in _WZ["way"] else _ld[k])
        for f in _WZ["way_family"].values() for k in f[2]]
WAY_FAMILY = [(name, [x for x in LOOP if x[0] in members]) for name, _, members in _WZ["way_family"].values()]
way = Q.way
CAUSE = {k: v for k, v in CB["cause_zh"].items()}
CLAIM = {"correct-success": ("声称成功且成功", "最终说做成了，评分也通过"), "false-success": ("声称成功但失败", "说或暗示做成了，评分没过"),
         "knows-failed": ("如实说失败", "最终明说没做成"), "no-claim": ("没有表态", "最终消息没说成败"),
         "matches-live": ("和现场一致、评分不同", "agent 看到的现场结果和最终评分不一致")}
# write, read, shell take the slots of the case pages' activity strip (tools/site/app.js ACT: --l1, --l2, --l3, --c7)
TOOLS = PL.slots([("write", "写文件"), ("read", "读文件"), ("shell", "命令与脚本"), ("image", "看图"), ("plan", "写计划"), ("other", "其他")])
# How a trial ended (valence): success green, 超时 blue (--n1; red is GPT-6 Astra's colour), the other failure kinds
# rust / violet / magenta / gold, grey other (PL.ALIAS; the same tokens as app.js ENDS).
ENDS = [("success", "成功", "--ok"), ("timeout", "超时", "--n1"), ("self-stopped", "自己停下", "--n2"), ("fell", "摔倒", "--n5"),
        ("episode-over", "局被判负", "--n3"), ("token-budget", "token 上限", "--n4"), ("other-fail", "其他失败", "--c0")]
# Stages: one slot each (the phases are declared groups, drawn as each row's dividers and as the legend's group names).
STAGES = PL.slots([("understanding", "理解任务", "读懂目标、及格线和约束"), ("exploration", "摸清环境", "弄清接口、机器人和场景"),
                   ("perception", "感知", "看清物体在哪、是什么"), ("design", "设计方法", "选定并搭好做法"),
                   ("execution", "控制执行", "真正动手时的控制和物理"), ("verification", "验证", "结束前的检查"),
                   ("deliverable", "交付", "存下被评分的东西"), ("time-budget", "时间与预算", "时间、reset、token 的安排"),
                   ("external", "外部原因", "评分、任务或基础设施侧，不是 agent 的问题")])
PHASES = [("动手之前", ("understanding", "exploration", "perception", "design")), ("动手时", ("execution",)),
          ("收尾", ("verification", "deliverable")), ("时间与预算", ("time-budget",))]
TECH = [("ik", "IK"), ("fk", "FK"), ("pd", "PD/反馈"), ("keyframe", "关键帧/路点"), ("motion_plan", "运动规划"),
        ("traj_opt", "轨迹优化/MPC"), ("search", "参数搜索"), ("rl", "RL"), ("perception", "图像处理"), ("state_edit", "改仿真状态")]
TECH_ANN = [("ik", "IK"), ("fk", "FK"), ("pd", "PD/反馈"), ("keyframe", "关键帧/路点"), ("motion-plan", "运动规划"),
            ("traj-opt", "轨迹优化/MPC"), ("param-search", "参数搜索"), ("rl", "RL"), ("replay", "重放"), ("state-edit", "改仿真状态"),
            ("library", "现成控制器"), ("visual-servo", "看图对准"), ("grasp-geometry", "先读几何再抓")]
PERCEPTION = [("sim-state", "读仿真状态"), ("geometry", "读碰撞体/网格"), ("depth-3d", "深度转 3D"), ("pixels-2d", "2D 像素"), ("agent-looks", "agent 看图")]
INTEGRITY = [("pip_upstream", "下载上游包"), ("success_src", "读成功判定源码"), ("decompile", "反编译 pyc"),
             ("grep_answers", "搜答案文件"), ("web", "上网"), ("log", "关或删日志")]


ROW = {"agent": "一个 agent", "agent_mode": "一个 agent 在一种模式下", "mode": "一种模式", "category": "一类任务",
       "bench": "一个 benchmark", "outcome": "成功或失败", "crit": "一种关键点", "tasktype": "一种任务类型",
       "body": "一种机器人形态", "cap": "一种能力要求"}
# EFE Task Atlas groupings (queries.atlas; meta/codebook.json trial_zh): code -> [name, definition], in drawing order
ATLAS_ZH = {f: CB["trial_zh"][f] for f in ("tasktype", "body", "cap")}
MULTI_WHAT = {"tasktype": "任务类型", "cap": "能力要求"}


DEFAULT_BY = {"unsolved": "tasktype", "trio": "tasktype", "dots": "tasktype"}                      # figures whose default grouping is multi-label


def with_multi(figs: dict) -> dict:
    """The figure registry with one note added under every chart grouped by tasktype or cap (the 怎么读 line stays one
    sentence): a task counts in each of its task types (capabilities), so the groups add up to more than the whole."""
    def wrap(name, fn):
        def draw(**kv):
            out = fn(**kv)
            what = MULTI_WHAT.get(kv.get("by", DEFAULT_BY.get(name)))
            if not what or 'class="howto"' not in out:
                return out
            note, i = f'<p class="note">一个任务可属于几种{what}，各算一次，所以各组相加多于全部。</p>', out.rfind('<details class="more">')
            return out[:i] + note + out[i:] if i >= 0 else out + note
        return draw
    return {k: wrap(k, f) for k, f in figs.items()}
NOT_RERUN = "这是分析的判断，不是重跑验证的结果。"
_LUNA_OPEN = "非 Luna 的 agent 只算 Luna 没过的评测项。"          # all set only: the core set has no GPT-6 Luna at all


def _row(by) -> str:
    """'每行是…' subject for the 怎么读 line (a space after a trailing Latin word, so Chinese text can follow)."""
    r = ROW.get(by, by)
    return r + " " if r[-1:].isascii() else r


def _label(by, v):
    if by == "agent_mode":
        return f"{v[0]} · {MODE_NAME.get(v[1], v[1])}"
    if by == "crit":                                       # critical-point kind -> its Chinese name (codebook progress_zh)
        return PROG["critical"].get(v, [v])[0]
    if by in ATLAS_ZH:
        return ATLAS_ZH[by].get(v, [v])[0]
    return MODE_NAME.get(v, v) if by == "mode" else CAT_NAME.get(v, v) if by == "category" else {"1": "成功", "0": "失败"}.get(v, v) if by == "outcome" else v


def _key(by, t):
    if by == "agent_mode":
        return (t["agent"], t["mode"])
    return Q.CATEGORY.get(t["bench"]) if by == "category" else t["success"] if by == "outcome" else t[by]


def _groups(rows, by, min_n=5):
    """[(row label, rows)] in the grouping's order; a list key (tasktype, cap) puts the row in each of its groups."""
    g = defaultdict(list)
    for r in rows:
        k = _key(by, r)
        for x in (k if isinstance(k, list) else [k]):
            g[x].append(r)
    order = [(a, m) for a in Q.ORDER for m in MODE_NAME] if by == "agent_mode" else Q.ORDER if by == "agent" else list(MODE_NAME) if by == "mode" else list(CAT_NAME) if by == "category" else [c[0] for c in CRIT] if by == "crit" else list(ATLAS_ZH[by]) if by in ATLAS_ZH else sorted(g)
    return [(_label(by, k), g[k]) for k in order if len(g.get(k, [])) >= min_n]


def _filter(rows, kv):
    return [r for r in rows if Q._match(r, {k: v for k, v in kv.items() if k not in ("by", "min", "src", "note", "say", "lead", "detail", "scope")})]


def _lead(data, keys, what: str, skip=("_other",)) -> str:
    """One computed sentence over a stacked chart: for each row, the largest part (rows with n >= 3). data: [(label,
    counts)] or [(label, counts, n)]. The fraction's denominator is the row's whole n, the number the chart prints at the
    row's right end ("其他" included); keys in `skip` are never named as the largest part."""
    names = {k[0]: k[1] for k in keys}
    out = []
    for lab, c, *given in data:
        n = round(given[0] if given else sum(c.values()))
        top = [(k, v) for k, v in c.most_common() if k not in skip and v]
        if n >= 3 and top:
            k, v = top[0]
            out.append(f"{lab}：{what}最多是「{names.get(k, k)}」（{round(v)}/{n}）")
    return f'<p class="figsay">{"；".join(out)}。</p>' if out else ""


def _frac(a, b):
    a, b = Q._f(a), Q._f(b)
    return min(a / b, 1.0) if a is not None and b else None


_PLEGS = re.compile(r'<div class="plegs">.*?</div>(?=<div class="crow axis chead">)', re.S)


def fig_loop(ctx, by="mode", **kv):
    """How the robot was driven (approach labels, v17 families): one bar per row with each family's share above its span
    and the row's own dividers between families (charts.phased); the legend groups the three Code to Control members and puts the
    other families under 其他做法 (as figs_way does)."""
    rows = _filter(Q.ann_rows(ctx), kv)
    known = {k[0] for k in LOOP}
    data = []
    for lab, rs in _groups(rows, by, int(kv.get("min", 5))):
        c = Q.tally(rs, lambda r: [r["way"]] if r["way"] in known else [])
        data.append((lab, round(sum(c.values())), c))
    read = "每段 = 一种做法的抽样 trial 数/这一行的抽样 trial 数；分析认定。"
    chart = C.phased(data, WAY_FAMILY, unit="抽样 trial", sample=True, read=read,
                     note=f"竖线是这一行各类做法的分界。{_WZ['way']['train'][0]} 按做法标注的技术里有没有 rl 认定。")
    if chart:
        code, rest = WAY_FAMILY[0], [x for _, ks in WAY_FAMILY[1:] for x in ks]
        lg = "".join(f'<div class="pleg"><b>{C.esc(g)}</b>{C.legend([(k[1], k[2], k[3]) for k in ks])}</div>' for g, ks in (code, ("其他做法", rest)))
        chart = _PLEGS.sub(lambda m: f'<div class="plegs">{lg}</div>', chart, count=1)
    return (_lead([(lab, c, n) for lab, n, c in data], LOOP, "") if kv.get("lead") and chart else "") + chart


def fig_tech(ctx, by="agent", src="code", **kv):
    """Technique use: share of trials whose code shows it (src=code, all valid trials) or labelled from the review (src=ann)."""
    if src == "ann":
        rows = _filter(Q.ann_rows(ctx), kv)
        data = [(lab, len(rs), Q.tally(rs, lambda r: set(r["tech"]))) for lab, rs in _groups(rows, by)]
        return C.heat(data, TECH_ANN, unit="抽样 trial", sample=True, note="",
                      read="每格 = 用到这项技术的抽样 trial 数/这一行的抽样 trial 数；分析认定。")
    rows = [t for t in _filter(ctx.trials, kv) if t.get("has_traj") == "1"]
    data = [(lab, len(rs), Counter(k for t in rs for k, _ in TECH if t.get(f"tech_{k}") == "1")) for lab, rs in _groups(rows, by, 20)]
    return C.heat(data, TECH, unit="trial 数", note="只表示用过，不表示起主要作用。",
                  read="每格 = 代码里出现这项技术的 trial 数/这一行的 trial 数；按代码匹配。")


def fig_perception(ctx, by="mode", **kv):
    rows = _filter(Q.ann_rows(ctx), kv)
    data = [(lab, len(rs), Q.tally(rs, lambda r: set(r["perception"]))) for lab, rs in _groups(rows, by)]
    return C.heat(data, PERCEPTION, unit="抽样 trial", sample=True, note="",
                  read="每格 = 位置来自这一来源的抽样 trial 数/这一行的抽样 trial 数；分析认定。")


def fig_tools(ctx, by="agent", **kv):
    """Mix of tool calls (share of all calls)."""
    rows = [t for t in _filter(ctx.trials, kv) if t.get("has_traj") == "1"]
    data = []
    for lab, rs in _groups(rows, by, 20):
        c = Counter()
        for t in rs:
            n = {k: int(Q._f(t.get(f"n_{k}")) or 0) for k in ("shell", "write", "read", "image", "plan")}
            c.update(n)
            c["other"] += max(0, int(Q._f(t.get("calls")) or 0) - sum(n.values()))
        data.append((lab, c))
    return C.stack(data, TOOLS, unit="调用数",
                   read="每段 = 一类工具调用数/这一行的调用总数；按运行日志统计。")


def fig_calls(ctx, by="agent", **kv):
    """How much each agent does per trial: median and interquartile range of process counts (log axis)."""
    rows = [t for t in _filter(ctx.trials, kv) if t.get("has_traj") == "1"]
    metrics = [("calls", "工具调用"), ("py_runs", "运行脚本"), ("images_seen", "看图")]
    groups = _groups(rows, by, 20)
    blocks = []
    for k, label in metrics:
        out = []
        for lab, rs in groups:
            v = sorted(x for t in rs if (x := Q._f(t.get(k))) is not None)
            if len(v) >= 5:
                out.append((lab, len(v), (v[len(v) // 4], S.median(v), v[3 * len(v) // 4])))
        blocks.append((label, out))
    return C.ranges(blocks, note="各 agent 跑的评测项不同" + ("（非 Luna 只跑 Luna 没过的评测项）" if ctx.set != "core" else "") + "。",
                    read="点 = 每个 trial 计数的中位数，条 = 中间一半的 trial；按日志统计。")


def cause_desc(code: str) -> str:
    """Codebook description of a cause code (other:… codes describe themselves)."""
    import json, os
    from common import HERE
    cb = json.load(open(os.path.join(HERE, "meta/codebook.json")))["cause"]
    return next((g[code] for g in cb.values() if code in g), code.replace("other:", ""))


def fig_profile(ctx, **kv):
    """One row per agent: the signature on every dimension, each cell computed from labels, reviews or features."""
    ann, rev = _filter(Q.ann_rows(ctx), kv), _filter(Q.review_rows(ctx), kv)
    loop_name = {k[0]: (k[1], k[2]) for k in LOOP}            # v17 approaches (queries.way)
    tech_name = dict(TECH_ANN)
    head = ["Agent", "privileged 方式", "standard 方式", "常用技术", "调用 / trial", "看图 / trial（std）",
            "失败时用时", "比别家更常见的失败", "失败却称成功"]
    fails_all = [r for r in rev if r["outcome"] == "failure"]
    causes = lambda r: {c for c in [r["primary"]] + r["secondary"] if c}
    base = Q.tally(fails_all, causes)
    out = []
    for a in Q.ORDER:
        mine_a = [r for r in ann if r["agent"] == a]
        if len(mine_a) < 5:
            continue
        def top_loop(mode):
            rs = [r for r in mine_a if r["mode"] == mode]
            if len(rs) < 3:
                return '<span class="meta">–</span>'
            k, n = Q.tally(rs, lambda r: [r["way"]]).most_common(1)[0]
            l, c = loop_name.get(k, (k, "--c0"))
            return f'<span class="dot" style="background:var({c})"></span>{C.esc(l)} <span class="meta">{round(n)}/{len(rs)}</span>'
        tech = Q.tally(mine_a, lambda r: {x for x in r["tech"] if x in tech_name}).most_common(2)
        tr = [t for t in ctx.trials if t["agent"] == a and t.get("has_traj") == "1"]
        calls = Q.med(t.get("calls") for t in tr)
        imgs = Q.med(t.get("images_seen") for t in tr if t["mode"] == "standard")
        fails = [t for t in ctx.open if t["agent"] == a and t["success"] == "0"]
        used = [x for t in fails if (x := _frac(t["agent_min"], t["cutoff_min"])) is not None]
        fr = [r for r in rev if r["agent"] == a and r["outcome"] == "failure"]
        mine_c, seen = Q.tally(fr, causes), Counter(c for r in fr for c in causes(r))      # at least 3 plain cases
        lift = sorted(((k / len(fr)) / (base[c] / len(fails_all)), c, k) for c, k in mine_c.items() if seen[c] >= 3 and base[c]) if fr else []
        false = Q.count(fr, lambda r: r["claim"] == "false-success")
        out.append([f'<a href="#agent-{a.lower().replace(" ", "-")}">{C.esc(a)}</a>', top_loop("privileged"), top_loop("standard"),
                    "、".join(f'{C.esc(tech_name[k])} <span class="meta">{round(n)}/{len(mine_a)}</span>' for k, n in tech),
                    f"{calls:.0f}" if calls is not None else "–", f"{imgs:.0f}" if imgs is not None else "–",
                    f"{round(100 * S.median(used))}%" if used else "–",
                    f'<span class="deflab" data-tip="{C.esc(CAUSE.get(lift[-1][1], [lift[-1][1], cause_desc(lift[-1][1])])[1])}">{C.esc(CAUSE.get(lift[-1][1], [lift[-1][1].replace("other:", "")])[0])}</span> <span class="meta">{round(lift[-1][2])}/{len(fr)}，别家的 {lift[-1][0]:.1f} 倍</span>' if lift else "–",
                    f'{round(false)}/{len(fr)}' if fr else "–"])
    note = ("方式、技术：分析过的 trial 的方式标注（随机抽样）；调用、看图：全部有效 trial 的中位数；"
            f"失败时用时：{'Luna 没过的评测项上' if ctx.set != 'core' else ''}失败 trial 用掉的时间占时限的中位数；比别家更常见的失败：失败分析里（主因或次因）"
            "占比除以全部 agent 的占比最高的原因，至少 3 例；失败却称成功：失败分析里最终声明为成功的。")
    return (C.howto("每行是一个 agent；每列的来源和分母见表下说明。") + '<div class="profile">' + Q.table(head, out, num_from=4)
            + f'</div><p class="note">{C.esc(note)}</p>')


def fig_timeuse(ctx, by="agent", scope="open", **kv):
    """Where in the time limit trials end, by how they end (scope=all: every cell, used for Luna's own page)."""
    rows = _filter(ctx.trials if scope == "all" else ctx.open, kv)
    data = []
    for lab, rs in _groups(rows, by, 20):
        pts = [(x, Q.ending(t)) for t in rs if (x := _frac(t["agent_min"], t["cutoff_min"])) is not None]
        data.append((lab, pts))
    return C.hist(data, ENDS, note=_LUNA_OPEN if ctx.set != "core" else "",
                  read="横轴 = 用时占时限的比例，柱高 = trial 数，颜色 = 结束方式。")


def fig_lanes(ctx, by="agent", **kv):
    """When things happen, as a share of the time limit (medians)."""
    rows = [t for t in _filter(ctx.open, kv) if t.get("has_traj") == "1"]
    marks = PL.slots([("first_clock_min", "第一次看时钟"), ("first_output_min", "第一次写交付目录"), ("last_output_min", "最后一次写交付目录")])
    data = []
    for lab, rs in _groups(rows, by, 20):
        med = {}
        for k, _, _ in marks:
            v = [x for t in rs if (x := _frac(t.get(k), t["cutoff_min"])) is not None]
            med[k] = S.median(v) if len(v) >= 5 else None
        ends = sorted(x for t in rs if (x := _frac(t["agent_min"], t["cutoff_min"])) is not None)
        band = (ends[len(ends) // 4], ends[3 * len(ends) // 4]) if len(ends) >= 8 else None
        data.append((lab, len(rs), med, band))
    return C.lanes(data, marks, note="只算有过该事件的 trial；看时钟、写交付目录（/app/output）按命令文本识别，是近似值。",
                   read="色块 = 各事件时刻的中位数（占时限），浅带 = 结束时刻的中间一半。")


def fig_endings(ctx, by="agent", **kv):
    rows = _filter(ctx.open, kv)
    data = [(lab, Counter(Q.ending(t) for t in rs)) for lab, rs in _groups(rows, by, 20)]
    return C.stack(data, ENDS, unit="trial 数", note=_LUNA_OPEN if ctx.set != "core" else "",
                   read="每段 = 一种结束方式的 trial 数/这一行的 trial 数；评分程序判定成败。")


# Failure causes have no fixed colour: a cause chart is one chart's categories like any other, so its causes take the
# palette slots in the order drawn (PL.slots), with each family's members side by side (cause_order).
# grasp-contact is split by its grasp-1 subtype into three display codes.
GRASP_SPLIT = {"miss": "grasp-in", "push-away": "grasp-in", "slip-lift": "grasp-held", "slip-carry": "grasp-held",
               "release": "grasp-held"}
CAUSE_ZH_EXTRA = {"grasp-in": ["抓取·没拿进手里", "抓空或合手时把物体推开"], "grasp-held": ["抓取·拿住又丢", "抬起时滑脱、搬运中掉落或放下时出错"],
                  "grasp-other": ["抓取·夹不住等", "根本夹不住、工具没碰对，或抓取失败没细分"]}
# cause families (for the stack order only): grasp, collision, IK, precision, fall; perception and interface; understanding,
# planning and method; time; verification, metacognition and deliverable; external
CAUSE_FAMILY = {"grasp-contact": "grasp", "collision": "collision", "no-safety-guard": "collision", "ik-limits": "ik",
                "precision": "precision", "instability": "precision", "balance-fall": "fall", "dynamic-timing": "fall"}
GROUP_FAMILY = {"perception": "sense", "interface": "sense", "understanding": "method", "planning": "method", "method": "method",
                "time": "time", "verification": "check", "metacognition": "check", "deliverable": "check", "external": "external"}


def cause_family(code: str) -> str:
    if code in CAUSE_ZH_EXTRA:
        return "grasp"
    return CAUSE_FAMILY.get(code) or next((GROUP_FAMILY[g] for g, cs in CB["cause"].items() if code in cs), "external")


def cause_order(codes: list[str]) -> list[str]:
    """Stack order of a chart's causes (given most common first): each family's members side by side, families in the
    order of their most common member. Colours then follow this order (PL.slots), so touching causes take adjacent slots."""
    blocks = {}
    for c in codes:
        blocks.setdefault(cause_family(c), []).append(c)
    return [c for cs in blocks.values() for c in cs]


def display_cause(ctx, r) -> str:
    """A review's primary cause as drawn: grasp-contact split by its grasp-1 subtype; free other:* codes -> other."""
    p = r["primary"]
    if p == "grasp-contact":
        return GRASP_SPLIT.get((ctx.grasp.get(r["key"]) or {}).get("subtype"), "grasp-other")
    return p if p and not p.startswith("other:") else "_other"


def _code_label(field, v):
    if field in ("primary", "secondary", "any_cause"):
        return CAUSE_ZH_EXTRA.get(v) or CAUSE.get(v, [v.replace("other:", ""), ""])
    if field in CODE_ZH:
        return CODE_ZH[field].get(v, (v, ""))
    if field in ("fix", "any_fix"):
        return CB["fix_zh"].get(v, (v, ""))
    if field == "claim":
        return CLAIM.get(v, (v, ""))
    return (v, "")


CODE_ZH = {**CB["style_zh"], **CB["time_zh"]}            # review style / time fields -> {code: [Chinese name, definition]}
# Claims (valence, drawn in this order): told the truth about a success green, claimed a false success --n1 blue, the
# other three rust / gold / violet. Style and time codes take the slots in codebook order, one fixed colour per code.
CLAIM_COLORS = {"correct-success": "--ok", "false-success": "--n1", "knows-failed": PL.RUST, "no-claim": PL.GOLD, "matches-live": PL.VIOLET}
DIST_WHAT = {"primary": "主因", "secondary": "次因", "claim": "最终声明", "on_failure": "受挫后的做法", "plan_vs_act": "开局方式",
             "verification": "验证程度"}


def fig_dist(ctx, by="agent", field="primary", top="7", outcome="failure", **kv):
    """Review distribution of one field per group: stacked when single-valued, shaded table when multi-valued.
    Codes show their Chinese name; hover gives the one-line definition."""
    rows = [r for r in _filter(Q.review_rows(ctx), kv) if r["outcome"] == outcome]
    if field == "primary":
        rows = [{**r, "primary": display_cause(ctx, r)} for r in rows]
    if field == "any_cause":
        rows = [{**r, "any_cause": [c for c in [r["primary"]] + r["secondary"] if c]} for r in rows]
    groups = _groups(rows, by, int(kv.get("min", 5)))
    if field == "stage":
        return fig_stage_rows(groups, lead=bool(kv.get("lead")), by=by)
    vals = [v for v, _ in Q.tally(rows, lambda r: [v for v in (r[field] if isinstance(r[field], list) else [r[field]]) if v and v != "_other"]).most_common(int(top))]
    kind = "失败" if outcome == "failure" else "成功"
    if isinstance(rows[0][field] if rows else "", list) or field == "any_cause":
        what = "主因或次因含该项" if field == "any_cause" else "带有该项"
        return C.heat([(lab, len(rs), Q.tally(rs, lambda r: {v for v in r[field] if v in vals})) for lab, rs in groups],
                      [(v, *_code_label(field, v)) for v in vals], unit="抽样 trial", sample=True, tone="neg" if field in ("primary", "secondary", "any_cause") else "", note="",
                      read=f"每格 = 带这一项的抽样{kind}数/这一行的抽样{kind}数；分析认定。")
    if field == "claim":                                 # valence colours, in CLAIM's order
        vals = [v for v in CLAIM if v in vals]
        keys = [(v, *_code_label(field, v)[:1], CLAIM_COLORS[v], _code_label(field, v)[1]) for v in vals]
    elif field in CODE_ZH:                               # style / time codes: one slot per code, in codebook order
        keys = [k for k in PL.slots([(v, *_code_label(field, v)) for v in CODE_ZH[field]], grey=()) if k[0] in vals]
        vals = [k[0] for k in keys]
    else:                                                # causes: families side by side; past eight, the rest is 其他
        vals = (cause_order(vals) if field in ("primary", "secondary") else vals)[:len(PL.CAT)]
        keys = PL.slots([(v, *_code_label(field, v)) for v in vals], grey=())
    keys += [("_other", "其他", PL.GREY[0], "其余原因合计")]
    data = [(lab, Q.tally(rs, lambda r: [r[field] if r[field] in vals else "_other"])) for lab, rs in groups]
    what = DIST_WHAT.get(field, "类")
    read = f"每段 = 一种{what}的抽样{kind}数/这一行的抽样{kind}数；分析认定。"
    chart = C.stack(data, keys, unit="抽样 trial", sample=True, read=read)
    return (_lead(data, keys, "主因" if field == "primary" else "") if kv.get("lead") and chart else "") + chart


def fig_stage_rows(groups, lead=False, by="agent") -> str:
    """Decisive-error stages as one bar per row, ordered by phase (动手之前 | 动手时 | 收尾 | 时间与预算 | 外部), with
    each row's own dividers between phases."""
    st = {k[0]: k for k in STAGES}
    rows = [(lab, len(rs), Q.tally(rs, lambda r: [r["stage"]])) for lab, rs in groups]
    phases = PHASES + [("外部", ("external",))]
    phase = [(lab, Counter({g: sum(c.get(k, 0) for k in ks) for g, ks in PHASES}), n) for lab, n, c in rows]
    return (_lead(phase, [(g, g) for g, _ in PHASES], "决定性错误") if lead and rows else "") + C.phased(
        rows, [(g, [st[k] for k in ks]) for g, ks in phases], note="竖线是这一行各大段的分界。",
        read="每段 = 决定性错误在这一阶段的抽样失败数/这一行的抽样失败数。")


def fig_integrity(ctx, by="agent", **kv):
    """Trials with each boundary-crossing signal (all finished trials with a trajectory, rule-flagged ones included)."""
    rows = [t for t in _filter(ctx.all, kv) if t.get("has_traj") == "1"]
    flag = lambda t, k: t.get(f"int_{k}") not in (None, "", "0") or (k == "web" and t.get("web_calls") not in (None, "", "0"))
    data = [(lab, len(rs), Counter(k for t in rs for k, _ in INTEGRITY if flag(t, k))) for lab, rs in _groups(rows, by, 20)]
    return C.heat(data, INTEGRITY, unit="trial 数", tone="neg", note="含被拦下和没找到的尝试；是否违规见分析。",
                  read="每格 = 命令里出现这一信号的 trial 数/这一行的 trial 数；按文本匹配。")

EXCLUDED = PL.slots([("suspect", "评分侧存疑", "现场运行、回放或这一局本身已成功，最终却判失败"),
                     ("filter", "内容过滤器掐断", "模型服务的内容过滤器中途掐断了会话"),
                     ("infra", "其他基础设施问题", "API、网关、网络或评分程序出错")], grey=("infra",))


def fig_excluded(ctx, by="agent", **kv):
    """Trials the sampled analyses leave out because their zero was not the agent's doing (grader side or
    infrastructure), as counts per row; the monitor's success counts (queries.load_perf) count them as failures. Rule
    violations are the agent's own and are left out of the chart."""
    kind = lambda t: "suspect" if t["validity"] == "suspect" else "filter" if t["validity_reason"] == "provider_filter" else "infra"
    rows = [t for t in _filter(ctx.all, kv) if t["validity"] in ("suspect", "infra")]
    data = [(lab, Counter(kind(t) for t in rs), "") for lab, rs in _groups(rows, by, 1)]
    return C.counts(data, EXCLUDED, note="看板的结果把这些记作失败；抽样分析不计入。违规的 trial 抽样分析也不计入，不在图里。",
                    read="条长和数字 = 抽样分析不计入的 trial 数，颜色 = 原因。")


# Fix groups are kinds of change, not outcomes: one slot each; 需要更强的控制能力 (no change to the approach) is grey.
FAMILIES = PL.slots([("grasp", "抓取与接触"), ("loop", "闭环与安全"), ("percept", "感知核实"), ("verify", "自检与调试"),
                     ("budget", "时间与 reset"), ("strategy", "换法与重估"), ("harness", "harness"), ("task", "任务侧"),
                     ("skill", "需要更强的控制能力")], grey=("skill",))


FAMILIES = [(k, l, c, "、".join(CB["fix_zh"][f][0] for f, g in Q.REMEDY_FAMILY.items() if g == k and f in CB["fix_zh"])) for k, l, c in FAMILIES]


def fig_remedy(ctx, by="agent", **kv):
    """Which change would most likely have turned each failure into a pass (remedy labels, grouped into families)."""
    rows = _filter(Q.rem_rows(ctx), kv)
    data = [(lab, Q.tally(rs, lambda r: [r["family"]])) for lab, rs in _groups(rows, by)]
    return C.stack(data, FAMILIES, unit="抽样 trial", sample=True, note=NOT_RERUN,
                   read="每段 = 最该补的一步属这一组的抽样失败数/这一行的抽样失败数。")


def fig_fixes(ctx, by="agent", **kv):
    """Shares of failures per remedy code (main or extra), shaded."""
    rows = _filter(Q.rem_rows(ctx), kv)
    codes = [c for c, _ in Q.tally(rows, lambda r: [c for c in r["any_fix"] if c]).most_common(10)]
    data = [(lab, len(rs), Q.tally(rs, lambda r: {c for c in r["any_fix"] if c in codes})) for lab, rs in _groups(rows, by)]
    return C.heat(data, [(c, *CB["fix_zh"].get(c, (c, ""))) for c in codes], unit="抽样 trial", sample=True, tone="pos", note=NOT_RERUN,
                  read="每格 = 可补步骤含这一项的抽样失败数/这一行的抽样失败数。")


TIMEJ = PL.slots([("noclock", "以时间为由收工，没看时钟", "误判了剩余时间或时间还多就收工，而且全程没看时钟"),
                  ("clock", "以时间为由收工，看过时钟", "误判了剩余时间或时间还多就收工，虽然看过时钟"),
                  ("timeout-nodeliv", "到点时没有交付物", "时限到时还没存下任何能被评分的文件"),
                  ("other-time", "其他时间问题", "没有时间计划、很晚才存交付物、reset 或 token 用完、长时间空等"),
                  ("none", "与时间无关", "主因和次因里都没有时间类原因")])
TIME_CAUSES = {c for c in CB["cause"]["time"]}


def fig_time_chart(ctx, by="agent_mode", **kv):
    """Reviewed failures by how time figured in them: stopped on a time pretext (with / without looking at the clock),
    another time problem, or no time cause at all."""
    def kind(r):
        cs = {r["primary"], *r["secondary"]}
        if cs & {"misjudged-time", "early-stop"}:
            return "clock" if r["clock_aware"] == "True" else "noclock"
        if "timeout-no-deliverable" in cs:
            return "timeout-nodeliv"
        return "other-time" if cs & TIME_CAUSES else "none"
    rows = [r for r in _filter(Q.review_rows(ctx), kv) if r["outcome"] == "failure"]
    data = [(lab, Q.tally(rs, lambda r: [kind(r)])) for lab, rs in _groups(rows, by, int(kv.get("min", 8)))]
    return C.stack(data, TIMEJ, unit="抽样 trial", sample=True, note="「以时间为由收工」= 分析认定它误判了剩余时间或时间还多就收工。",
                   read="每段 = 时间起这类作用的抽样失败数/这一行的抽样失败数；分析认定。")


# would-pass (valence): likely the success green, maybe aqua, unlikely grey
FIXRANK_KEYS = [("likely", "很可能翻盘", "--ok", "只做这一处改动，这次很可能成功"), ("maybe", "可能翻盘", PL.AQUA, "只做这一处改动，这次可能成功"),
                ("unlikely", "不太可能", "--c0", "只做这一处改动也不太可能成功")]


def fig_fixrank(ctx, top="14", **kv):
    """Which single change the failures most often lacked: one bar per change, length = failures with it as the main
    change, split by whether that change alone would likely flip the result."""
    rows = _filter(Q.rem_rows(ctx), kv)
    by_fix = defaultdict(Counter)
    for (fix, would), k in Q.tally(rows, lambda r: [(r["fix"], r["would_pass"])]).items():
        by_fix[fix][would] += k
    order = sorted(by_fix, key=lambda f: -sum(by_fix[f].values()))[:int(top)]
    data = [(CB["fix_zh"].get(f, (f, ""))[0], by_fix[f], CB["fix_zh"].get(f, ("", f))[1]) for f in order]
    return C.counts(data, FIXRANK_KEYS, total=len(rows), note=NOT_RERUN,
                    read="数字 = 最该补的是这一步的失败数/全部抽样失败数；颜色 = 把握。")


_RL = CB["reason_zh"]["level"]
REASON_LEVEL = PL.slots([(k, *_RL[k][:2]) for k in ("high", "both", "low", "external")])
# Effective levels (queries.level2): both split into before / after; a both without a when label is drawn after low
# as 未细分.
REASON_LEVEL2 = PL.slots([(k, *_RL[k][:2]) for k in ("high", "before", "after", "low")]
                         + [("both", _RL["both"][0] + "（未细分）", "还没判定先后：" + _RL["both"][1]), ("external", *_RL["external"][:2])])


def fig_reason(ctx, by="agent", **kv):
    """Is there a thinking error behind each failure? reasoning-1 levels; once any when-1 labels exist, the effective
    levels (both split into before / after, an unsplit both shown as 未细分 while labelling runs)."""
    rows = _filter(Q.reason_rows(ctx), kv)
    split = bool(ctx.reasoning_when)
    field = "level2" if split else "level"
    data = [(lab, Q.tally(rs, lambda r: [r[field]])) for lab, rs in _groups(rows, by, int(kv.get("min", 5)))]
    keys = [k for k in REASON_LEVEL2 if k[0] != "both" or any(c.get("both") for _, c in data)] if split else REASON_LEVEL
    what = "（每个失败只记一个层级；高低层都有的再分事前想错、事后没挽回）" if split else "（每个失败只记一个层级）"
    return C.stack(data, keys, unit="抽样 trial", sample=True,
                   read="每段 = 这一层级的抽样失败数/这一行的抽样失败数；分析认定。")


def fig_reasonkinds(ctx, by="agent", detail="", **kv):
    """Which thinking errors, as shares of the failures: the five groups in the agent's working order (理解 → 方法 → 计划 →
    查证 → 调整), or the eight kinds with detail=1."""
    rows = _filter(Q.reason_rows(ctx), kv)
    field, names = ("kinds", CB["reason_zh"]["kind"]) if detail else ("groups", CB["reason_zh"]["group"])
    order = [k for k, _ in Q.tally(rows, lambda r: r[field]).most_common()] if detail else list(names)
    data = [(lab, len(rs), Q.tally(rs, lambda r: set(r[field]))) for lab, rs in _groups(rows, by, int(kv.get("min", 5)))]
    return C.heat(data, [(k, *names.get(k, (k, ""))[:2]) for k in order], unit="抽样 trial", sample=True, tone="neg",
                  note="纯低层失误和外部原因不带任何一类。",
                  read="每格 = 带这类高层错误的抽样失败数/这一行的抽样失败数。")


def fig_modes_chart(ctx, scope="open", fmt="", **kv):
    """Same agent, same task in both modes: which mode passed (scope=all: every cell, used for Luna's own page). Reads
    the monitor's graded rows (queries.load_perf; filter=drop leaves out the content-filter stops)."""
    keys = [("both", "两种都成功", "--ok", ""), ("priv", "只有 privileged 成功", PL.BLUE, ""), ("std", "只有 standard 成功", PL.GOLD, ""), ("none", "都失败", PL.SOFT[0], "")]
    data = []
    only = set(kv["agent"].split(",")) if kv.get("agent") else None
    pool = Q.perf_pool(ctx, {**kv, "scope": scope})
    if not kv.get("agent"):                                # headline: the six MAIN_AGENTS on the tasks graded for all six
        pool = [t for t in Q.common_subset(pool, Q.MAIN_AGENTS) if t["agent"] in Q.MAIN_AGENTS]
    for a, c in sorted(Q.mode_pairs(pool).items(), key=lambda kv2: Q.ORDER.index(kv2[0])):
        if (scope == "all" or a != "GPT-6 Luna") and sum(c.values()) >= 15 and (only is None or a in only):   # Luna failed every open cell by construction
            data.append((a, Counter({"both": c[(1, 1)], "priv": c[(1, 0)], "std": c[(0, 1)], "none": c[(0, 0)]})))
    ns = {sum(c.values()) for _, c in data}
    one = len(ns) == 1                                     # every row the same n: say it once (user 10-19), no count column
    batch = f"同一批 {ns.pop()} 个任务" if one else "两种模式都跑过的任务"
    return C.stack(data, keys, unit="任务数", note=("" if ctx.set == "core" else "全部评测项都算。" if scope == "all" else "只算 Luna 没过的评测项，所以不列 Luna。")
                   + ("" if kv.get("agent") else Q.CORE_ALL + "。" if ctx.set == "core" else "只算六家主要 agent 都评过分的任务。"), fmt=fmt,
                   read=f"每行 = 一家在{batch}上的成败；每段 = 这种成败组合的比例，评分程序判定。" if fmt == "pct"
                   else f"每行 = 一家在{batch}上的成败；每段 = 成败组合的任务数/任务数，评分程序判定。", label=False,
                   cls=" compact", count=not one)


GROUPINGS = ("tasktype", "body", "cap", "category")       # task groupings of the block charts (category: navigation groups)


def _members(by: str, t: dict) -> list:
    """The groups one trial falls in under a task grouping: its Atlas values (tasktype / cap: each one), or its bench's
    navigation group (category)."""
    if by == "category":
        return [Q.CATEGORY.get(t["bench"])]
    v = t[by]
    return v if isinstance(v, list) else [v]


def _group_names(by: str) -> list[tuple]:
    return list(CAT_NAME.items()) if by == "category" else [(k, v[0]) for k, v in ATLAS_ZH[by].items()]


def fig_common_chart(ctx, by="", top="3", fmt="", **kv):
    """Head-to-head on the same tasks: success rate per agent, one block per mode (by=tasktype / body / cap / category:
    one block per group, the `top` strongest agents as rows; mode= and other trial filters pick the tasks). Reads the
    monitor's graded rows on the task dirs Luna did not pass (queries.load_perf; filter=drop as in q:rate). scope=all
    without by= adds a realtime block (standard-realtime, the tasks graded for all six in that mode). Bars wear the
    agents' colours (agent_color) and print no value (k/n in tip and table, user 10-19)."""
    pool = Q.perf_pool(ctx, kv)
    agents = [a for a in Q.MAIN_AGENTS if any(t["agent"] == a for t in pool)]   # the headline six (user 10-18)
    if by in GROUPINGS:
        return _common_by(_filter(Q.common_subset(pool, agents), kv), by, agents[:int(top)], len(agents), "mode" in kv, ctx.set, fmt)
    modes = Q.MAIN_MODES + (("standard-realtime",) if kv.get("scope") == "all" else ())
    cs = Q.common_subset(pool, agents, modes)
    blocks = []
    for m in modes:
        rows = []
        for a in agents:
            s, n = Q.rate([t for t in cs if t["agent"] == a and t["mode"] == m])
            if n:
                rows.append((a, s / n, f"{s}/{n}", f"{a} · {m}：成功 {s}/{n}"))
        blocks.append((f"{MODE_NAME[m]}：同一批任务上的成功率", rows))
    return C.bars(blocks, note=(Q.CORE_ALL if ctx.set == "core" else "只算这些 agent 都跑过的任务（且都是 Luna 没过的评测项）") + "。",
                  read=_COMMON_READ[fmt == "pct"], colors={a: agent_color(a) for a in agents}, keys=agent_keys(agents), fmt="" if kv.get("labels") == "kn" else fmt,
                  label=kv.get("labels") == "kn", cls=" compact")      # labels=kn: print k/n after each bar (user 10-19, §1.1)


_COMMON_READ = ("每条是做成数/评测项数；同一批评测项，评分程序判定成败。", "每条是一家做成的评测项比例；同一批评测项，评分程序判定成败。")


def _unmapped(benches) -> str:
    """The note for benchmarks that site.json `categories` does not list (their trials fall in no category block)."""
    names = sorted({b for b in benches if b not in Q.CATEGORY})
    return f"{'、'.join(names)} 不属于任何类别，只计入合计。" if names else ""


def _common_by(cs, by, show, n_agents, one_mode, which="core", fmt="") -> str:
    """Success rate on the common task set, per task group (see GROUPINGS): a block per group, a row per shown agent."""
    blocks, small = [], []
    for cat, name in _group_names(by):
        rows, n = [], 0
        for a in show:
            s, n = Q.rate([t for t in cs if t["agent"] == a and cat in _members(by, t)])
            if n:
                rows.append((a, s / n, f"{s}/{n}", f"{a} · {name}：成功 {s}/{n}"))
        if rows and n < C.SMALL:
            small.append(name)
        blocks.append((f"{name} · {n} 个任务" + ("（样本少）" if rows and n < C.SMALL else ""), rows))
    note = ((Q.CORE_ALL if which == "core" else "只算这些 agent 都跑过的任务（且都是 Luna 没过的评测项）") + "。" + ("" if one_mode else "privileged 和 standard 的同一任务各算一个。")
            + (f"标「样本少」的块少于 {C.SMALL} 个任务，仅供参考。" if small else "")
            + (_unmapped(t["bench"] for t in cs) if by == "category" else ""))
    return C.bars(blocks, note=note, read=_COMMON_READ[fmt == "pct"], colors={a: agent_color(a) for a in show},
                  keys=agent_keys(show), fmt=fmt, label=False)


# Three-agent overlap (fig:overlap): an exclusive combination's colour says how many of the three solved it (declared
# groups 3 / 2 / 1 / 0, one hue each); the dots say who.
OVERLAP_GROUP = [("3", "三家都做成", "--ok"), ("2", "两家做成", PL.BLUE), ("1", "一家做成", PL.GOLD), ("0", "三家都没做成", "--c0")]
OVERLAP_NAME = {"all3": "三家都做成", "astra+argon": "Astra 和 Argon", "astra+opus": "Astra 和 Opus", "argon+opus": "Argon 和 Opus",
                "astra": "只有 Astra", "argon": "只有 Argon", "opus": "只有 Opus", "none": "三家都没做成"}


def _ngroup(combo: str) -> str:
    return "3" if combo == "all3" else "0" if combo == "none" else str(combo.count("+") + 1)


def fig_overlap(ctx, by="", fmt="", **kv):
    """Which of GPT-6 Astra, Gemini 4 Argon and Opus 5.5 solved each evaluation item of the headline subset (graded for
    all six main agents; queries.overlap_cells). Default: an UpSet-style matrix, one row per exclusive combination
    (queries.COMBOS), three dots (filled = solved), one column per mode with a bar (k/n of that mode; only the 三家都没做成 row prints its value); the tip
    lists up to 8 task names. by=tasktype / body / cap: per group, a three-part bar (三家都做成 / 一两家做成 / 都没做成),
    one panel per mode (mode=, default privileged,standard), rows by the 都没做成 share, 其他 last (_overlap_by).
    by=bench: the hardest benchmarks, one grey 都没做成 bar each (_overlap_bench; min= / top=)."""
    top = kv.pop("top", "")                                        # drawing options, not row filters
    minshare = float(kv.pop("minshare", 0) or 0)
    modes = kv["mode"].split(",") if kv.get("mode") else list(Q.MAIN_MODES if by in GROUPINGS + ("bench",) else MODE_NAME)
    cells = {m: Q.overlap_cells(ctx, **{**kv, "mode": m}) for m in modes}
    modes = [m for m in modes if cells[m]]
    if not modes:
        return ""
    if by == "bench":
        return _overlap_bench(cells, modes, int(kv.get("min", 1)), int(top) if top else 0, fmt, minshare)
    if by in GROUPINGS:
        return _overlap_by(cells, modes, by, int(kv.get("min", 1)), kv.get("show", ""), fmt)
    names = [a for a in Q.TRIO.values()]
    head = "".join(f'<th class="uh">{C.esc(a)}</th>' for a in names) + "".join(
        f'<th class="um{C.MODE_CLS.get(MODE_NAME[m], "")}">{MODE_NAME[m]}<small>（共 {len(cells[m])} 项）</small></th>' for m in modes)
    body, table = [], []
    for combo in Q.COMBOS:
        g = next(x for x in OVERLAP_GROUP if x[0] == _ngroup(combo))
        dots = "".join(f'<td class="ud"><i class="udot{" on" if key in combo.split("+") or combo == "all3" else ""}"></i></td>' for key in Q.TRIO)
        tds, trow = [], [C.esc(OVERLAP_NAME[combo])]
        for m in modes:
            hit = Q.overlap_hit(cells[m], combo)
            k, n = len(hit), len(cells[m])
            tasks = sorted(dict.fromkeys(Q.task_label(cells[m][c]["row"]) for c in hit))
            tip = f"{OVERLAP_NAME[combo]} · {MODE_NAME[m]}：{k}/{n}" + ("；如 " + "、".join(tasks[:8]) + ("等" if len(tasks) > 8 else "") if tasks else "")
            tds.append(f'<td class="ub" data-tip="{C.esc(tip)}"><span class="ubt"><span class="ubf" style="width:{100 * k / n:.1f}%;background:var({g[2]})"></span></span><b>{(C.value(k, n, fmt) if fmt else k) if combo == "none" else ""}</b></td>')
            trow.append(C.kn(k, n))
        body.append(f'<tr class="ug{g[0]}"><th scope="row" class="ul">{C.esc(OVERLAP_NAME[combo])}</th>{dots}{"".join(tds)}</tr>')
        table.append(trow)
    read = "每行一种做成组合，条长 = 占这一列评测项的比例；只有三家都没做成那一行标" + ("比例" if fmt == "pct" else "项数") + "，评分程序判定。"
    lg = C.legend([(lab, col) for _, lab, col in OVERLAP_GROUP])
    return (C.howto(read) + f'<div class="chart upset">{lg}<div class="scroll"><table class="t upset"><tr><th></th>{head}</tr>{"".join(body)}</table></div>'
            '<p class="note">鼠标停在格子上可看这一格的任务（最多 8 个）。</p></div>'
            + C.numbers(["组合"] + [MODE_NAME[m] for m in modes], table))


# fig:overlap|by=…: three parts per task group, declared by how many of the three solved it (三家都做成 green, 一两家做成
# gold, 都没做成 grey; validate_palette.js on green and gold passes light and dark, the grey is the palette's neutral).
OVERLAP_3 = [("3", "三家都做成", "--ok"), ("12", "一两家做成", PL.GOLD), ("0", "都没做成", "--c0")]


def _overlap_by(cells: dict, modes: list, by: str, min_n: int, show: str = "", fmt: str = "") -> str:
    """fig:overlap|by=…: a three-part stack per task group (OVERLAP_3; a task counts in each of its groups), one panel per
    mode side by side; rows by the 都没做成 share in the first mode (most unsolved first), 其他 (not in the Atlas) last.
    show=none: one grey bar per group instead, the 都没做成 share (k/n)."""
    count = {m: defaultdict(Counter) for m in modes}
    for m in modes:
        for v in cells[m].values():
            part = "3" if len(v["solved"]) == 3 else "0" if not v["solved"] else "12"
            for g in _members(by, v["row"]):
                count[m][g][part] += 1
    first = count[modes[0]]
    keep = {g for m in modes for g, c in count[m].items() if sum(c.values()) >= min_n}
    rows = _rank_groups(keep, by, lambda g: first[g]["0"] / sum(first[g].values()) if sum(first[g].values()) else 0)
    note = (f"按 {MODE_NAME[modes[0]]} 下都没做成的比例排序" + (f"，少于 {min_n} 项的类不画" if min_n > 1 else "")
            + ("；不在 Task Atlas 里的任务归入「其他」" if Q.UNCLASSIFIED in rows else "") + "。三家 = " + "、".join(Q.TRIO.values()) + "。")
    parts = []
    for m in modes:
        title = f"{MODE_NAME[m]}<small>（共 {len(cells[m])} 项）</small>"
        if show == "none":
            bars = []
            for g in rows:
                c, lab = count[m][g], _group_label(by, g)
                n = sum(c.values())
                if n:
                    bars.append((lab, c["0"] / n, f'{c["0"]}/{n}', f"{lab} · {MODE_NAME[m]}：三家都没做成 {c['0']}/{n}"))
            parts.append((title, C.bars([("", bars)], color="--c0", fmt=fmt)))
        else:
            data = [(_group_label(by, g), count[m][g]) for g in rows if sum(count[m][g].values())]
            parts.append((title, C.stack(data, OVERLAP_3, unit="评测项", fmt=fmt, label=False)))
    what = "比例" if fmt == "pct" else "评测项数/这类评测项数"
    read = f"每条 = 三家都没做成的{what}；评分程序判定。" if show == "none" else f"每段 = 做成情况相同的{what}；评分程序判定。"
    return C.panels(parts, read=read, note=note)


def _overlap_bench(cells: dict, modes: list, min_n: int, top: int, fmt: str = "", minshare: float = 0) -> str:
    """fig:overlap|by=bench: the hardest benchmarks, one panel per mode in the fig:trio look (compact: thin bars, tight
    rows, the mode title alone): a row per benchmark with one grey bar, the share of its evaluation items none of the
    three solved (label k/n). Per panel: benchmarks with at least min_n items in that mode and (minshare=, e.g. 0.3)
    that share at least minshare, by that share (descending; ties: more items first), the `top` hardest (0: all)."""
    panels, table, labels = [], [], []
    for m in modes:
        count = defaultdict(Counter)
        for v in cells[m].values():
            count[v["row"]["bench"]]["n"] += 1
            count[v["row"]["bench"]]["none"] += not v["solved"]
        rows = sorted((b for b, c in count.items() if c["n"] >= min_n and c["none"] / c["n"] >= minshare),
                      key=lambda b: (-count[b]["none"] / count[b]["n"], -count[b]["n"], Q.BENCH_NAME.get(b, b)))[:top or None]
        body = []
        for b in rows:
            c, lab = count[b], Q.BENCH_NAME.get(b, b)
            tip = f"{lab} · {MODE_NAME[m]}：三家都没做成 {C.kn(c['none'], c['n'])}"
            body.append((lab, [_tbar(c["none"], c["n"], "--c0", tip, fmt, none=True)]))
            table.append([C.esc(lab), MODE_NAME[m], str(c["n"]), C.kn(c["none"], c["n"])])
        labels += [lab for lab, _ in body]
        panels.append((m, len(cells[m]), body))
    note = (f"每个模式只画评测项不少于 {min_n} 个" + (f"、三家都没做成的比例不低于 {100 * minshare:.0f}%" if minshare else "")
            + "的 benchmark" + (f"，最多取最难的 {top} 个" if top and minshare else f"，取最难的 {top} 个" if top else "")
            + "，按三家都没做成的比例从高到低排序。三家 = " + "、".join(Q.TRIO.values()) + "。")
    return (C.howto("灰条 = 三家都没做成的评测项占这个 benchmark 的比例。")
            + f'<div class="chart trio tcompact"><div class="mpanels">{"".join(_tpanel(m, n, b, labels, count=False) for m, n, b in panels)}</div>'
            + f'<p class="note">{note}</p></div>' + C.numbers(["Benchmark", "模式", "评测项", NONE_LABEL], table))


# fig:venn: an area-proportional three-set Venn per mode (venn.layout), in the agents' colours (slots in agent order:
# palette.AGENT, as TRIO_COLOR). Each mode is scaled to fit its panel; the panels share one viewBox size, so
# text has one size in all three.
VENN_NAME = {"all3": "三家都做成", "astra+argon": "只有 Astra 和 Argon 做成", "astra+opus": "只有 Astra 和 Opus 做成",
             "argon+opus": "只有 Argon 和 Opus 做成", "astra": "只有 Astra 做成", "argon": "只有 Argon 做成", "opus": "只有 Opus 做成",
             "none": "三家都没做成"}
VENN_SHORT = {"astra": "Astra", "argon": "Argon", "opus": "Opus"}
VENN_PAINT = ("astra", "argon", "opus", "astra+argon", "astra+opus", "argon+opus", "all3")   # hit order: the most specific on top
_VENN_IDS = itertools.count()


def _members_of(combo: str) -> frozenset:
    return frozenset(Q.TRIO) if combo == "all3" else frozenset(combo.split("+"))


def _venn_svg(lay: dict, view: tuple, regions: dict, color: dict, label: str) -> str:
    """One panel's SVG: soft circle fills, a clickable shape per region (clip by its circles, mask out the others; the
    most specific regions are painted last, so a click lands on the right one), outlines, set labels, region numbers
    (outside ones with a thin leader line). regions: combo -> (k, tip, title, data)."""
    W, H, ox, oy = view
    pid = f"vn{next(_VENN_IDS)}"
    f = lambda v: f"{v:.1f}"
    circ = {k: (x + ox, y + oy, r) for k, (x, y, r) in lay["circles"].items()}
    circle = lambda k, extra="": f'<circle cx="{f(circ[k][0])}" cy="{f(circ[k][1])}" r="{f(circ[k][2])}"{extra}/>'
    defs = "".join(f'<clipPath id="{pid}{k}">{circle(k)}</clipPath>' for k in Q.TRIO)
    rect = f'x="0" y="0" width="{f(W)}" height="{f(H)}"'
    for combo in VENN_PAINT:
        out = [k for k in Q.TRIO if k not in _members_of(combo)]
        if out:
            defs += (f'<mask id="{pid}x{"".join(out)}" maskUnits="userSpaceOnUse" {rect}><rect {rect} fill="#fff"/>'
                     + "".join(circle(k, ' fill="#000"') for k in out) + "</mask>")
    fills = "".join(circle(k, f' class="vc" style="fill:var({color[k]})"') for k in Q.TRIO)
    lines = "".join(circle(k, f' class="vo" style="stroke:var({color[k]})"') for k in Q.TRIO)
    regs = []
    for combo in VENN_PAINT:
        k, tip, title, data = regions[combo]
        spot = lay["spots"].get(_members_of(combo))
        if not k and not spot:
            continue
        out = [x for x in Q.TRIO if x not in _members_of(combo)]
        shape = f'<rect class="vshape" {rect}' + (f' mask="url(#{pid}x{"".join(out)})"' if out else "") + "/>"
        for m in _members_of(combo):
            shape = f'<g clip-path="url(#{pid}{m})">{shape}</g>'
        num = ""
        if spot:
            x, y = spot["x"] + ox, spot["y"] + oy
            if not spot["inside"]:
                num += (f'<line class="vlead" x1="{f(spot["ax"] + ox)}" y1="{f(spot["ay"] + oy)}" x2="{f(spot["lx"] + ox)}" '
                        f'y2="{f(spot["ly"] + oy)}"/><circle class="vdot" cx="{f(spot["ax"] + ox)}" cy="{f(spot["ay"] + oy)}" r="1.6"/>')
            num += f'<text class="vnum{"" if spot["inside"] else " vout"}" x="{f(x)}" y="{f(y)}">{k}</text>'
        focus = ' tabindex="0" role="button"' if num else ""
        regs.append(f'<g class="vreg"{focus} aria-label="{C.esc(title)}：{k} 项" data-tip="{C.esc(tip)}" data-title="{C.esc(title)}" '
                    f'data-tasks="{data}">{shape}{num}</g>')
    names = "".join(f'<text class="vlab" x="{f(x + ox)}" y="{f(y + oy)}" text-anchor="{anchor}">'
                    f'<tspan class="vname">{C.esc(VENN_SHORT[k])}</tspan> {C.esc(lay["names"][k])}</text>'
                    for k, (x, y, anchor) in lay["labels"].items())
    return (f'<svg viewBox="0 0 {f(W)} {f(H)}" role="group" aria-label="{C.esc(label)}"><defs>{defs}</defs>'
            f'<g class="vfills" aria-hidden="true">{fills}</g>{"".join(regs)}<g class="vlines" aria-hidden="true">{lines}</g>'
            f'<g aria-hidden="true">{names}</g></svg>')


def fig_venn(ctx, **kv):
    """Area-proportional three-agent Venn diagrams (GPT-6 Astra, Gemini 4 Argon, Opus 5.5), one per mode (mode=, default
    all three), on the headline subset (graded for all six main agents; queries.overlap_cells): a circle's area is that
    agent's solved count, each pairwise overlap the pair's (venn.layout); every region prints its count (a small one
    outside, with a leader line), each circle its agent's k/n, 都没做成 is a pill under the diagram. A region (an SVG group
    with tabindex, data-tasks = [[benchmark, task, mode], …]) lists its tasks under the diagrams on click / Enter (app.js
    vennShow); its tip gives the count and the first names."""
    import json as J
    import venn as V
    modes = kv["mode"].split(",") if kv.get("mode") else list(MODE_NAME)
    cells = {m: Q.overlap_cells(ctx, **{**kv, "mode": m}) for m in modes}
    modes = [m for m in modes if cells[m]]
    if not modes:
        return ""
    keys = list(Q.TRIO)
    color = {k: TRIO_COLOR[a] for k, a in Q.TRIO.items()}
    lays, regions, table = {}, {}, []
    for m in modes:
        cs, n = cells[m], len(cells[m])
        size = {k: sum(k in v["solved"] for v in cs.values()) for k in keys}
        pair = {frozenset((a, b)): sum(a in v["solved"] and b in v["solved"] for v in cs.values())
                for i, a in enumerate(keys) for b in keys[i + 1:]}
        regions[m] = {}
        for combo in Q.COMBOS:
            hit = Q.overlap_hit(cs, combo)
            items = sorted(list(Q.task_parts(cs[c]["row"])) + [m] for c in hit)
            first = "、".join(f"{b} · {t}" for b, t, _ in items[:4]) + ("等" if len(items) > 4 else "")
            title = f"{VENN_NAME[combo]} · {MODE_NAME[m]}"
            tip = f"{title}：{len(hit)}/{n}" + (f"；如 {first}" if items else "") + ("。点开看全部任务。" if items else "。")
            regions[m][combo] = (len(hit), tip, title, C.esc(J.dumps(items, ensure_ascii=False)))
        names = {k: f"{size[k]}/{n}" for k in keys}
        lay = V.layout(keys, size, pair, {_members_of(c): regions[m][c][0] for c in VENN_PAINT},
                       {k: f"{VENN_SHORT[k]} {names[k]}" for k in keys})
        lays[m] = {**lay, "names": names}
        table.append([MODE_NAME[m], str(n)] + [str(size[k]) for k in keys] + [str(regions[m][c][0]) for c in Q.COMBOS])
    pad = 6
    W = max(l["bbox"][2] - l["bbox"][0] for l in lays.values()) + 2 * pad
    H = max(l["bbox"][3] - l["bbox"][1] for l in lays.values()) + 2 * pad
    panels = []
    for m in modes:
        x0, y0, x1, y1 = lays[m]["bbox"]
        view = (W, H, (W - (x1 - x0)) / 2 - x0, (H - (y1 - y0)) / 2 - y0)
        k, tip, title, data = regions[m]["none"]
        n = len(cells[m])
        svg = _venn_svg(lays[m], view, regions[m], color, f"{MODE_NAME[m]}：三家做成情况的韦恩图，共 {n} 项")
        panels.append(f'<div class="vpanel"><p class="rtitle">{MODE_NAME[m]}<small>（共 {n} 项）</small></p>{svg}'
                      f'<button type="button" class="vnone" data-tip="{C.esc(tip)}" data-title="{C.esc(title)}" data-tasks="{data}">'
                      f'都没做成 <b>{k}</b></button></div>')
    lg = C.legend([(a, color[k]) for k, a in Q.TRIO.items()])
    return (C.howto("圈面积 = 做成数，块内 = 恰好这几家做成的项数，分母见图题。") + f'<div class="chart venn">{lg}<div class="vpanels">{"".join(panels)}</div>'
            '<div class="vlist" aria-live="polite"><p class="note">点图里任一块，这里列出它的任务。</p></div></div>'
            + C.numbers(["模式", "评测项", *[f"{VENN_SHORT[k]} 做成" for k in keys], *[VENN_NAME[c] for c in Q.COMBOS]], table))


TRIO_COLOR = {a: PL.AGENT[a][0] for a in Q.TRIO.values()}       # the agents' own colours (palette.AGENT)


def agent_color(a: str) -> str:
    """An agent's bar colour, the same in every chart: GPT-6 Astra red-orange, Gemini 4 Argon purple, Opus 5.5 teal (TRIO_COLOR,
    as fig:trio and fig:venn); the other agents have no colour of their own and share the neutral grey."""
    return TRIO_COLOR.get(a, PL.GREY[0])


def agent_keys(agents) -> list[tuple]:
    """The legend of agent_color: each coloured agent by name, then one grey item naming the rest."""
    rest = [a for a in agents if a not in TRIO_COLOR]
    return [(a, TRIO_COLOR[a]) for a in agents if a in TRIO_COLOR] + ([("、".join(rest), PL.GREY[0])] if rest else [])


def _rank_groups(groups: dict, by: str, share) -> list:
    """Group keys in drawing order: by share (descending; ties by the grouping's own order), 其他 (not in the Atlas) last."""
    order = {g: i for i, (g, _) in enumerate(_group_names(by))}
    known = sorted((g for g in groups if g != Q.UNCLASSIFIED), key=lambda g: (-share(g), order.get(g, 99)))
    return known + ([Q.UNCLASSIFIED] if Q.UNCLASSIFIED in groups else [])


def _group_label(by: str, g: str) -> str:
    return "其他" if g == Q.UNCLASSIFIED else dict(_group_names(by)).get(g, g)


NONE_LABEL = "三家都没做成"


def _tbar(k, n, col: str, tip: str, fmt: str = "", none: bool = False, label: bool = True) -> str:
    """One thin bar of the fig:trio look (width = k/n; none: the hatched grey 三家都没做成 bar); label=False leaves the
    value column empty (the number stays in the tip and the 看数字 table)."""
    w = 100 * k / n if n else 0
    return (f'<span class="tb{" tbnone" if none else ""}" data-tip="{C.esc(tip)}"><span class="tbt"><span class="tbf" style="width:{w:.1f}%;'
            f'background:var({col})"></span></span><span class="tv">{C.value(k, n, fmt) if label else ""}</span></span>')


def _label_em(labels, cap: float = 11) -> float:
    """The row-label column width (em) that fits the longest label: wide (CJK) characters 1em, others about .6em;
    at least the stylesheet's 7em, at most cap (default 11em)."""
    return min(cap, max([7] + [sum(1 if ord(ch) > 0x2e7f else .6 for ch in lab) + .5 for lab in labels]))


def _tpanel(m: str, n: int, rows: list, labels: list, count: bool = True) -> str:
    """One mode panel of the fig:trio look: the mode title (共 n 个评测项; count=False: the title alone), then rows =
    [(label, [_tbar html])]; the label column fits the longest of `labels` (all panels of one chart, so they line up)."""
    col = f' style="grid-template-columns:minmax(64px,{_label_em(labels):.1f}em) minmax(0,1fr)"'
    body = "".join(f'<div class="trow"{col}><span class="cl" title="{C.esc(lab)}">{C.esc(lab)}</span><span class="tbars">{"".join(bars)}</span></div>'
                   for lab, bars in rows)
    return (f'<div class="mpanel"><p class="rtitle ttitle{C.MODE_CLS.get(MODE_NAME[m], "")}">{MODE_NAME[m]}'
            + (f'<small>共 {n} 个评测项</small>' if count else "") + f'</p>{body}</div>')


def fig_trio(ctx, by="tasktype", fmt="", **kv):
    """GPT-6 Astra, Gemini 4 Argon and Opus 5.5 per task group (by=tasktype, default; body / cap): a row per group with
    three bars in the agents' colours and a hatched grey 三家都没做成 bar, one panel per mode (mode=, default
    privileged,standard), on the headline subset (graded for all six main agents; queries.overlap_cells). Rows by the
    三家都没做成 share in the first mode, ascending (easiest first, hardest last); tasks not in the Atlas are the row 其他,
    always last. A row label carries the group's item count in that mode; only the grey bar prints its value (fmt=pct:
    the integer percent); the agents' k/n are in the tip and the table."""
    modes = kv["mode"].split(",") if kv.get("mode") else list(Q.MAIN_MODES)
    cells = {m: Q.overlap_cells(ctx, **{**kv, "mode": m}) for m in modes}
    modes = [m for m in modes if cells[m]]
    if not modes:
        return ""
    count = {m: defaultdict(Counter) for m in modes}             # mode -> group -> Counter(agent key; "n")
    for m in modes:
        for v in cells[m].values():
            for g in _members(by, v["row"]):
                count[m][g]["n"] += 1
                count[m][g].update(v["solved"])
                count[m][g]["none"] += not v["solved"]
    first = count[modes[0]]
    rows = _rank_groups({g for m in modes for g in count[m]}, by, lambda g: -first[g]["none"] / first[g]["n"] if first[g]["n"] else -1)
    panels, table = [], []
    for m in modes:
        body = []
        for g in rows:
            c, lab = count[m][g], _group_label(by, g)
            bars = [_tbar(c[k], c["n"], col, f"{a} · {lab} · {MODE_NAME[m]}：{what} {C.kn(c[k], c['n'])}", fmt, none=k == "none", label=k == "none")
                    for k, a, col, what in [(k, a, TRIO_COLOR[a], "做成") for k, a in Q.TRIO.items()] + [("none", NONE_LABEL, "--c0", "评测项")]]
            body.append((f"{lab}（{c['n']}）", bars))           # the row label carries this mode's item count
            if c["n"]:
                table.append([C.esc(lab), MODE_NAME[m], str(c["n"])] + [C.kn(c[k], c["n"]) for k in Q.TRIO] + [C.kn(c["none"], c["n"])])
        panels.append((m, len(cells[m]), body))
    labels = [lab for _, _, body in panels for lab, _ in body]
    panels = [_tpanel(m, n, body, labels) for m, n, body in panels]
    lg = C.legend([(a, TRIO_COLOR[a]) for a in Q.TRIO.values()] + [(NONE_LABEL, "--c0")]).replace(
        '<i style="background:var(--c0)">', '<i class="hatch" style="background:var(--c0)">')
    read = ("每条 = 一家做成的评测项占这类评测项（括号里是项数）的比例；灰色斜纹条 = 三家都没做成的比例。" if fmt == "pct"
            else "每条 = 一家的做成数/这类评测项数（括号里是项数）；灰色斜纹条 = 三家都没做成的。")
    return (C.howto(read) + f'<div class="chart trio">{lg}<div class="mpanels">{"".join(panels)}</div>'
            + f'<p class="note">按 {MODE_NAME[modes[0]]} 下三家都没做成的比例从低到高排序，最难的在最下'
            + ("；不在 Task Atlas 里的任务归入「其他」，放在最后" if Q.UNCLASSIFIED in rows else "") + "。</p>"
            + "</div>" + C.numbers([FIG_BY_ROW.get(by, ""), "模式", "评测项", *Q.TRIO.values(), NONE_LABEL], table))


# fig:dots (user 10-19, replaces fig:trio on the page): per task group one row, the three agents' success shares as dots on
# one line (agent colours), a thin line from the lowest to the highest dot; the 三家都没做成 share sits apart in a narrow
# column at the right (a small grey bar and its value), so nothing grey lies on the agents' line.
DOT_TICKS = (0, 25, 50, 75, 100)


def _dots_panel(m: str, n: int, rows: list, lab_em: float, right: str = NONE_LABEL) -> str:
    """One mode panel of fig:dots. rows: [(label, sub, {agent: (share, tip)}, (share, value text, tip) of 三家都没做成)];
    sub: a muted second line under the label (reasons=1; "": no text for this row; None: not asked); dots drawn by share, highest first, so a lower
    dot sits on top where two overlap."""
    col = f' style="grid-template-columns:minmax(64px,{lab_em:.1f}em) minmax(0,1fr) var(--dn-w)"'
    grid = "".join(f'<b class="dg" style="left:{x}%"></b>' for x in DOT_TICKS)
    body = [f'<div class="drow dhead"{col}><span class="cl"></span><span></span><span class="dnh">{right}</span></div>']
    for i, (lab, sub, dots, (xn, xv, xtip)) in enumerate(rows):
        vs = [v for v, _ in dots.values()]
        line = f'<span class="drange" style="left:{100 * min(vs):.1f}%;width:{100 * (max(vs) - min(vs)):.1f}%"></span>' if vs else ""
        pts = "".join(f'<i class="dd" style="left:{100 * v:.1f}%;background:var({TRIO_COLOR[a]})" data-tip="{C.esc(tip)}"></i>'
                      for a, (v, tip) in sorted(dots.items(), key=lambda kv2: -kv2[1][0]))
        none = (f'<span class="dn" data-tip="{C.esc(xtip)}"><span class="dnt"><span class="dnf" style="width:{100 * xn:.1f}%"></span></span>'
                f'<span class="dnv">{C.esc(xv)}</span></span>')
        cl = (f'<span class="cl" title="{C.esc(lab + ("：" + sub if sub else ""))}"><span class="dl1">{C.esc(lab)}</span>'
              + (f'<span class="dsub">{C.esc(sub)}</span>' if sub else "") + "</span>"
              if sub is not None else f'<span class="cl" title="{C.esc(lab)}">{C.esc(lab)}</span>')
        body.append(f'<div class="drow{" alt" if i % 2 else ""}"{col}>{cl}'
                    f'<span class="dtrack">{grid}{line}{pts}</span>{none}</div>')
    axis = "".join(f'<span style="left:{x}%">{x}%</span>' for x in DOT_TICKS)
    body.append(f'<div class="drow daxis"{col}><span class="cl"></span><span class="dtrack">{axis}</span><span></span></div>')
    return (f'<div class="mpanel"><p class="rtitle ttitle{C.MODE_CLS.get(MODE_NAME[m], "")}">{MODE_NAME[m]}'
            f'</p><div class="drows">{"".join(body)}</div></div>')


def _bench_reasons() -> dict:
    """meta/bench_reasons.json: {bench id: {"hard": text, "easy": text}} for fig:dots|by=bench|reasons=1; {} when the
    file is missing or unreadable."""
    try:
        return _json.load(open(_os.path.join(_HERE, "meta/bench_reasons.json")))
    except (OSError, ValueError):
        return {}


def fig_dots(ctx, by="tasktype", **kv):
    """GPT-6 Astra, Gemini 4 Argon and Opus 5.5 per task group (by=tasktype, default; body / cap / bench) as a dot plot,
    one panel per mode (mode=, default privileged,standard; scope=all by default), on the headline subset
    (queries.overlap_cells, as fig:trio). A row per group: the three agents' success shares on one line, a thin line
    joining the lowest and highest; at the right, in its own column, a small grey bar with the 三家都没做成 share (value
    k/n; fmt=pct: the integer percent). Groups with fewer than min= items (default 5) in a panel are left out. Each
    panel's rows by its 三家都没做成 share: side=easy (default) ascending, easiest on top; side=hard descending, hardest
    on top; 其他 (not in the Atlas) last; top=N keeps the first N per panel (by=bench: default 10; else all). by=bench:
    a row per benchmark (ties: more items first); reasons=1 adds a muted second line under each name, that side's text
    from meta/bench_reasons.json (none when missing). The row label carries the group's item count in that panel. The
    dots print no value: k/n are in the tips and the 看数字 table."""
    fmt = kv.pop("fmt", "")
    side = kv.pop("side", "easy")
    tops = [int(x) for x in str(kv.pop("top", "") or (10 if by == "bench" else 0)).split(",")]   # top=4,8: per mode panel, in mode order
    why = _bench_reasons() if by == "bench" and kv.pop("reasons", "") not in ("", "0") else None
    min_n = int(kv.get("min", 5))
    modes = kv["mode"].split(",") if kv.get("mode") else list(Q.MAIN_MODES)
    cells = {m: Q.overlap_cells(ctx, **{"scope": "all", **kv, "mode": m}) for m in modes}
    modes = [m for m in modes if cells[m]]
    if not modes:
        return ""
    metric = "avg" if by == "bench" and side == "easy" else "none"    # easy benchmarks: ranked by the three agents' mean success (user 10-19)
    right = "三家平均成功率" if metric == "avg" else NONE_LABEL
    kn_of = lambda c: (c["astra"] + c["argon"] + c["opus"], 3 * c["n"]) if metric == "avg" else (c[metric], c["n"])
    sign = -1 if side == "hard" or metric == "avg" else 1           # hard: the largest 三家都没做成 share first; all3: the largest 三家都做成 first
    members = (lambda r: [r["bench"]]) if by == "bench" else (lambda r: _members(by, r))
    panels, table, labels = [], [], []
    for mi, m in enumerate(modes):
        top = tops[min(mi, len(tops) - 1)]
        count = defaultdict(Counter)                                 # group -> Counter(agent key; "n"; "none")
        for v in cells[m].values():
            for g in members(v["row"]):
                count[g]["n"] += 1
                count[g].update(v["solved"])
                count[g]["none"] += not v["solved"]
                count[g]["all3"] += len(v["solved"]) == 3
        keep = {g for g in count if count[g]["n"] >= min_n}
        share = lambda g: kn_of(count[g])[0] / kn_of(count[g])[1]
        if by == "bench":
            order = sorted(keep, key=lambda g: (sign * share(g), -count[g]["n"], Q.BENCH_NAME.get(g, g)))
        else:
            order = _rank_groups(keep, by, lambda g: -sign * share(g))
        rows = []
        for g in order[:top or None]:
            c, lab = count[g], Q.BENCH_NAME.get(g, g) if by == "bench" else _group_label(by, g)
            where = f"{lab} · {MODE_NAME[m]}"
            dots = {a: (c[k] / c["n"], f"{a} · {where} · 做成 {C.kn(c[k], c['n'])}") for k, a in Q.TRIO.items()}
            sub = ((why.get(g) or {}).get("tag") or (why.get(g) or {}).get(side, "")) if why is not None else None   # a short tag: what the benchmark is
            rows.append((lab if by == "bench" else f"{lab}（{c['n']}）", sub, dots, (kn_of(c)[0] / kn_of(c)[1], f"{100 * kn_of(c)[0] / kn_of(c)[1]:.0f}%" if metric == "avg" else C.value(c[metric], c["n"], fmt),
                                                           f"{right} · {where} · {C.kn(*kn_of(c))}")))
            table.append([C.esc(lab), MODE_NAME[m], str(c["n"])] + [C.kn(c[k], c["n"]) for k in Q.TRIO] + [C.kn(*kn_of(c))])
        labels += [r[0] + ("　　" + r[1] if r[1] else "") for r in rows]     # name and tag share one line (by=bench)
        panels.append((m, len(cells[m]), rows))
    lab_em = _label_em(labels, cap=13 if why is not None else 11)
    lg = ('<div class="legend dlegend">' + "".join(f'<span><i class="dd" style="background:var({TRIO_COLOR[a]})"></i>{C.esc(a)}</span>'
                                                  for a in Q.TRIO.values())
          + f'<span><span class="dnt dnkey"><span class="dnf" style="width:60%"></span></span>{right}（右栏）</span></div>')
    note = (f"每栏按{right}" + ("" if metric == "avg" else "的比例") + ("从高到低排序，最难的在最上" if side == "hard" else "从高到低排序，最容易的在最上" if metric == "avg" else "从低到高排序，最容易的在最上")
            + ((f"；少于 {min_n} 个评测项的 benchmark 不画" if min_n > 1 else "") + (("；每栏最多取前 " + "、".join(str(x) for x in tops) + " 个" if len(set(tops)) > 1 else f"；每栏最多取前 {top} 个") if top else "")
               if by == "bench" else "")
            + ("；不在 Task Atlas 里的任务归入「其他」，放在最后" if by != "bench" and any(
                Q.UNCLASSIFIED in _members(by, v["row"]) for m in modes for v in cells[m].values()) else "")
            + (("。名字旁是它的类型；最右列是三家平均成功率（三家做成数之和 ÷ 3 × 评测项数）。" if metric == "avg" else f"。名字旁是它的类型；最右列是{right}的数/这个 benchmark 的评测项数。") if by == "bench" else "。括号里是这一栏的评测项数。"))
    head = "Benchmark" if by == "bench" else FIG_BY_ROW.get(by, "")
    return (C.howto(f"每个点 = 一家做成的比例；右栏灰条 = {right}" + ("。" if metric == "avg" else "的比例。"))
            + f'<div class="chart trio dots{" dreason" if why is not None else ""}">{lg}<div class="mpanels">'
            + "".join(_dots_panel(m, n, r, lab_em, right) for m, n, r in panels)
            + f'</div><p class="note">{note}</p></div>'
            + C.numbers([head, "模式", "评测项", *Q.TRIO.values(), right], table))


FIG_BY_ROW = {"tasktype": "任务类型", "body": "机器人形态", "cap": "能力要求", "category": "类别"}


def fig_unsolved(ctx, by="tasktype", **kv):
    """Cells (task x mode) of the headline subset (graded for all six queries.MAIN_AGENTS; min= / with= / agent= as in
    q_unsolved) that none of them solved, per task group (by=tasktype, default; body / cap / category) and mode. One
    block per group (first: all), one row per mode."""
    cells = Q.run_cells(ctx, **kv)
    blocks = []
    for cat, name in [("", "全部任务")] + _group_names(by):
        rows, K, N = [], 0, 0
        for m, lab in MODE_NAME.items():
            ts = [x for (_, mm), x in cells.items() if mm == m and (not cat or cat in _members(by, x[0]))]
            k, n = sum(Q.unsolved(x) for x in ts), len(ts)
            K, N = K + k, N + n
            if n:
                rows.append((lab, k / n, f"{k}/{n}", f"{name} · {lab}：{n} 个评测项里 {k} 个无人做成"))
        if rows:
            blocks.append((f"{name} · 合计 {K}/{N}", rows))
    if len(blocks) == 2:                                   # one category left: the total block would repeat it
        blocks = blocks[1:]
    names = Q.agent_list(kv.get("with") or kv.get("agent") or "main")
    short = (f"至少 {kv['min']} 家" if kv.get("min") and not kv.get("with") else "六家" if names == list(Q.MAIN_AGENTS) else "、".join(names))
    return C.bars(blocks, color="--n1", note=_unmapped(x[0]["bench"] for x in cells.values()) if by == "category" else "",
                  read=Q.batch_words(f"每条 = 无人做成数/{short}都评过分的评测项数；评分程序判定。"))


# Deliverable kinds (approach labels): one slot each, none = grey.
DELIV = PL.slots([("fresh-process", "新进程一次生成"), ("in-session", "会话中录制"), ("stitched", "拼接多段"),
                  ("live-only", "只有现场运行"), ("none", "没有交付物")])
_dd = {k: re.sub(r"^[^：]{1,12}：", "", v) for k, v in CB["approach"]["deliverable"].items()}      # the legend prints the name already


def fig_deliv(ctx, by="agent", **kv):
    """How the graded deliverable was made, from approach labels; the tip of each segment adds the share that succeeded."""
    rows = _filter(Q.ann_rows(ctx), kv)
    groups = _groups(rows, by, int(kv.get("min", 5)))
    data = [(lab, Q.tally(rs, lambda r: [r["deliverable"]])) for lab, rs in groups]
    win = {lab: Q.tally(rs, lambda r: [r["deliverable"]] if r["success"] == "1" else []) for lab, rs in groups}
    extra = {(lab, k): f"其中评分通过 {round(win[lab][k])}/{round(c)}" for lab, cnt in data for k, c in cnt.items() if c}
    keys = [(k, lab, c, _dd[k]) for k, lab, c in DELIV if any(cnt.get(k) for _, cnt in data)]
    read = "每段 = 一种生成方式的抽样 trial 数/这一行的抽样 trial 数；分析认定。"
    mixed = any(cnt.get("live-only") for _, cnt in data) and any(cnt.get(k) for _, cnt in data for k in ("fresh-process", "stitched"))
    return C.stack(data, keys, unit="抽样 trial", sample=True, extra=extra, read=read,
                   note="「只有现场运行」只出现在 standard，那里评分的是现场这一局；比较生成方式只看 privileged 的行。" if mixed else "")


# Grasp ways: one slot each, other = grey.
GRASP = PL.slots([("miss", "抓空", "手指合上时物体不在指间（位置或手的几何没弄清）"),
                  ("push-away", "合手时推走", "接近或合手时把物体推开、碰倒"),
                  ("slip-lift", "抬起时滑脱", "抓住了，抬起或转腕时滑出"),
                  ("slip-carry", "搬运中掉落", "搬运或移动底盘时掉落"),
                  ("release", "放下时出错", "放得太高、没支撑就松手或粘在手上"),
                  ("cannot-hold", "根本夹不住", "太宽、太重、太薄或摩擦、力不够"),
                  ("tool-use", "工具没接触好", "拿着工具推、铲、擦、插时没碰对"),
                  ("other", "其他", "")])


def fig_grasp(ctx, by="agent", **kv):
    """How grasp / contact failures happen (grasp-1 labels on failures whose review lists grasp-contact)."""
    rows = _filter(Q.grasp_rows(ctx), kv)
    data = [(lab, Q.tally(rs, lambda r: [r["subtype"]])) for lab, rs in _groups(rows, by, 5)]
    return C.stack(data, GRASP, unit="抽样 trial", sample=True,
                   read="每段 = 一种抓取失败方式的数/这一行抓取失败的抽样数。")


# Progress and critical points (progress-1 labels). Levels 0–5 take --lv0…--lv5 (PL.ALIAS: grey → violet → blue →
# aqua → gold → the success green for 做成, the same tokens as the case pages' staircase); critical kinds and
# after-actions one slot each, grey = none / n/a.
PROG = CB["progress_zh"]
LEVELS = [(str(lv), f"第 {lv} 级", f"--lv{lv}", "{}。{}".format(*PROG["level"][str(lv)])) for lv in range(6)]   # child titles start 第 N 级
_pk = lambda part, codes: PL.slots([(k, *PROG[part][k][:2]) for k in codes])
CRIT = _pk("critical", ("time-out", "bad-deliverable", "out-of-reach", "terminated", "fall", "reset-out", "none"))
AFTER = _pk("after", ("stopped", "same-retry", "changed-method", "unrelated", "n/a"))
GRASP3 = PL.slots([(c, *CAUSE_ZH_EXTRA[c]) for c in ("grasp-in", "grasp-held", "grasp-other")])
BASIS = "进展等级 privileged 按 agent 自己的测试运行算，standard 按现场这一局算。"
BEST_TITLE = "全部抽样 trial 最高到了第几级（成功、失败各一行）"     # figs_time.fig_best, the all-trials view of fig_stuck


def _prog(ctx, kv, outcome="failure"):
    """Sampled progress rows matching the figure's filters (failures unless outcome is given)."""
    return [r for r in _filter(Q.progress_rows(ctx), kv) if not outcome or r["outcome"] == outcome]


def _side(groups, field, fmt, tip):
    """Per row, the median of a share field as short text under the row's count (rows with ≥ 3 values)."""
    out = {}
    for lab, rs in groups:
        v = [r[field] for r in rs if r.get(field) is not None]
        if len(v) >= 3:
            m = S.median(v)
            out[lab] = (fmt.format(round(100 * m)), tip.format(lab=lab, p=round(100 * m), n=len(v), rs=rs, m=m))
    return out


# progress-2 (10-18): two kinds of critical point — key steps (the milestones) and no-return events — and the way the
# trial ended. One slot each, grey = none (an end type outside the list is drawn as the grey 其他).
NORETURN = _pk("no_return", ("fall", "terminated", "out-of-reach", "none"))
NRAFTER = _pk("nr_after", ("stopped", "kept-trying"))
END = _pk("end", ("time-out", "resets-used", "deliverable", "agent-stopped", "goal-done", "crash"))
NR_DEF = "不可挽回点 = 第一个让它再也不可能通过、reset 也补不回的事件：摔倒、够不到或被任务终止"


def fig_noreturn(ctx, by="mode", **kv):
    """Failures by their no-return event (progress-2): fall, terminated, out of reach, or none."""
    groups = _groups(_prog(ctx, {**kv, "v2": "True"}), by, int(kv.get("min", 5)))
    data = [(lab, Q.tally(rs, lambda r: [r["no_return"]])) for lab, rs in groups]
    chart = C.stack(data, NORETURN, unit="抽样 trial", sample=True, note=NR_DEF + "。超时、reset 用完、交付物不合格不是不可挽回点，算作结束方式。",
                    read="每段 = 一类不可挽回点的抽样失败数/这一行的抽样失败数。")
    return (_lead(data, NORETURN, "不可挽回点", skip=("none",)) if kv.get("lead") and chart else "") + chart


def fig_nrafter(ctx, by="agent", **kv):
    """What the agent did after a no-return event with time left (progress-2: stopped / kept trying), with the median
    share of the limit still left at the event under each row's count."""
    rows = [{**r, "nr_left_frac": 1 - r["nr_t"] if r["nr_t"] is not None else None}
            for r in _prog(ctx, {"no_return": "!none", **kv, "v2": "True"}) if r["nr_after"] in ("stopped", "kept-trying")]
    groups = _groups(rows, by, int(kv.get("min", 5)))
    data = [(lab, Q.tally(rs, lambda r: [r["nr_after"]])) for lab, rs in groups]
    side = _side(groups, "nr_left_frac", "剩 {}%", "{lab}：不可挽回点时还剩的时间占时限的中位数 {p}%（{n} 个）")
    chart = C.stack(data, NRAFTER, unit="抽样 trial", sample=True, side=("剩余时限（中位数）", side),
                    note=NR_DEF + "。右侧「剩 x%」= 不可挽回点时还剩的时间占时限的中位数。",
                    read="每段 = 一种之后做法的抽样失败数/这一行的数量；分析认定。")
    return (_lead(data, NRAFTER, "不可挽回点之后") if kv.get("lead") and chart else "") + chart


def fig_end(ctx, by="mode", **kv):
    """How each failure ended (progress-2 end types); an unknown code is drawn as 其他."""
    groups = _groups(_prog(ctx, {**kv, "v2": "True"}), by, int(kv.get("min", 5)))
    known = {k[0] for k in END}
    data = [(lab, Q.tally(rs, lambda r: [r["end"] if r["end"] in known else "_other"])) for lab, rs in groups]
    keys = END + ([("_other", "其他", "--c0", "没有归入以上几类")] if any(c.get("_other") for _, c in data) else [])
    chart = C.stack(data, keys, unit="抽样 trial", sample=True,
                    read="每段 = 一种结束方式的抽样失败数/这一行的抽样失败数；分析认定。")
    return (_lead(data, keys, "结束方式") if kv.get("lead") and chart else "") + chart


def fig_crit(ctx, by="agent", **kv):
    """RETIRED (progress-1 critical point; kept so the current text builds — use fig_noreturn / fig_end).
    Failures by the kind of their critical point (the first event after which the trial could no longer pass)."""
    groups = _groups(_prog(ctx, {**kv, "v1": "True"}), by, int(kv.get("min", 5)))
    data = [(lab, Q.tally(rs, lambda r: [r["crit"]])) for lab, rs in groups]
    chart = C.stack(data, CRIT, unit="抽样 trial", sample=True,
                    read="每段 = 一类关键点的抽样失败数/这一行的抽样失败数；分析认定。")
    return (_lead(data, CRIT, "关键点", skip=("none",)) if kv.get("lead") and chart else "") + chart


def fig_crit_time(ctx, by="mode", **kv):
    """RETIRED (progress-1, kept so the current text builds).
    When the critical point falls, as a share of the time limit: a histogram per row, coloured by kind; by=crit
    gives one row per kind."""
    rows = [r for r in _prog(ctx, kv) if r["crit_t"] is not None]
    groups = _groups(rows, by, int(kv.get("min", 5)))                 # by=crit: one row per kind (see _groups)
    med = "，".join(f"{lab} {round(100 * S.median(r['crit_t'] for r in rs))}%" for lab, rs in groups)
    return C.hist([(lab, [(r["crit_t"], r["crit"]) for r in rs]) for lab, rs in groups], CRIT[:-1],
                  note=f"关键点时刻的中位数（占时限）：{med}。" if groups else "",
                  read="横轴 = 关键点占时限的位置，柱高 = 失败数，颜色 = 关键点类型。")


def fig_after(ctx, by="agent", **kv):
    """RETIRED (progress-1, kept so the current text builds — use fig_nrafter).
    What the agent did after the critical point (failures with one; time-outs left out unless crit= is given), with
    the median share of the limit still left at that point under each row's count."""
    kv = {"crit": "!none,time-out", **kv}
    groups = _groups(_prog(ctx, {**kv, "v1": "True"}), by, int(kv.get("min", 5)))
    data = [(lab, Q.tally(rs, lambda r: [r["after"] or "n/a"])) for lab, rs in groups]
    which = "（不含超时）" if kv["crit"] == "!none,time-out" else f"（关键点是{'或'.join(PROG['critical'].get(k, [k])[0] for k in kv['crit'].lstrip('!').split(','))}{'以外' if kv['crit'].startswith('!') else ''}）"
    side = _side(groups, "left", "剩 {}%", "{lab}：关键点时还剩的时间占时限的中位数 {p}%（{n} 个）")
    chart = C.stack(data, AFTER, unit="抽样 trial", sample=True, side=("剩余时限（中位数）", side),
                    note="右侧「剩 x%」= 关键点时还剩的时间占时限的中位数。",
                    read=f"每段 = 关键点之后一种做法的抽样失败数/这一行的数量{which}。")
    return (_lead(data, AFTER, "关键点之后", skip=("n/a",)) if kv.get("lead") and chart else "") + chart


def fig_stuck(ctx, by="agent", **kv):
    """The last progress level each failure reached (failures only; figs_time.fig_best shows every trial), with the
    median share of its session spent at that level."""
    groups = _groups(_prog(ctx, kv), by, int(kv.get("min", 5)))
    data = [(lab, Q.tally(rs, lambda r: [str(r["stuck"])])) for lab, rs in groups]
    side = _side(groups, "stuck_share", "停 {}%", "{lab}：停在最后一级的时间占这次会话用时的中位数 {p}%（{n} 个）")
    chart = C.stack(data, LEVELS, unit="抽样 trial", sample=True, side=("停在最后一级的时间（中位数）", side),
                    note=BASIS + "右侧「停 x%」= 停在这一级的时间占会话用时的中位数。",
                    read="每段 = 停在这一级的抽样失败数/这一行的抽样失败数；分析认定。")
    return (_lead(data, LEVELS, "停在") if kv.get("lead") and chart else "") + chart


def fig_reach(ctx, by="", level="3,5", **kv):
    """Progress curves: share of trials at level >= L by each moment (share of the time limit), successes vs failures;
    one small chart per level, or by=agent one per agent (the three strongest unless agent= lists them) at the first
    level given."""
    rows = _prog(ctx, {k: v for k, v in kv.items() if not (by == "agent" and k == "agent")}, outcome="")
    xs = [i / 100 for i in range(101)]                      # every whole percent, so 25 % is a grid point
    w = (lambda r: r["weight"]) if common.WEIGHTS else (lambda r: 1.0)
    def curve(rs, lv):
        tot = sum(w(r) for r in rs) or 1
        return [sum(w(r) for r in rs if r["reach"][lv] is not None and r["reach"][lv] <= x + 1e-9) / tot for x in xs]
    def series(rs, lv):
        out = []
        for oc, lab, col in (("success", "成功", "--ok"), ("failure", "失败", "--n1")):
            mine = [r for r in rs if r["outcome"] == oc]
            if len(mine) >= 5:
                out.append((lab, col, len(mine), curve(mine, lv)))
        return out
    levels = [int(x) for x in level.split(",")]
    name = lambda lv: f"第 {lv} 级（{PROG['level'][str(lv)][0]}）" + ("或更高" if lv < 5 else "")
    count = lambda ss: "，".join(f"{lab} {n} 个" for lab, _, n, _ in ss)
    if by == "agent":
        agents = kv["agent"].split(",") if kv.get("agent") else Q.ORDER[:3]
        panels = [(a, series([r for r in rows if r["agent"] == a], levels[0])) for a in agents]
        panels = [(f"{a} · {name(levels[0])}（{count(ss)}）", ss) for a, ss in panels]
        row = f"每张小图是一个 agent 的抽样 trial，到达{name(levels[0])}"
    else:
        panels = [(f"{name(lv)}（{count(series(rows, lv))}）", series(rows, lv)) for lv in levels]
        row = "每张小图是一个进展等级"
    return C.lines(panels, xs, note=BASIS + "到达时刻取第一次到达这一级或更高一级的时刻。",
                   read="纵轴 = 已到这一级的 trial 占比，横轴 = 用时占时限；分析认定。")


def fig_grasp3(ctx, by="agent", **kv):
    """Failures whose primary cause is grasp / contact, in the three display classes the child sections use."""
    rows = [{**r, "g3": display_cause(ctx, r)} for r in _filter(Q.review_rows(ctx), kv)
            if r["outcome"] == "failure" and r["primary"] == "grasp-contact"]
    data = [(lab, Q.tally(rs, lambda r: [r["g3"]])) for lab, rs in _groups(rows, by, int(kv.get("min", 5)))]
    chart = C.stack(data, GRASP3, unit="抽样 trial", sample=True,
                    read="每段 = 一类抓取失败的抽样失败数/这一行抓取失败的抽样数。")
    return (_lead(data, GRASP3, "") if kv.get("lead") and chart else "") + chart


def figures(ctx) -> dict:
    return {"loop": lambda **kv: fig_loop(ctx, **kv), "tech": lambda **kv: fig_tech(ctx, **kv),
            "perception": lambda **kv: fig_perception(ctx, **kv), "tools": lambda **kv: fig_tools(ctx, **kv),
            "calls": lambda **kv: fig_calls(ctx, **kv), "timeuse": lambda **kv: fig_timeuse(ctx, **kv),
            "lanes": lambda **kv: fig_lanes(ctx, **kv), "endings": lambda **kv: fig_endings(ctx, **kv),
            "profile": lambda **kv: fig_profile(ctx, **kv), "time": lambda **kv: fig_time_chart(ctx, **kv),
            "process": lambda **kv: fig_calls(ctx, **kv), "modes": lambda **kv: fig_modes_chart(ctx, **kv),
            "common": lambda **kv: fig_common_chart(ctx, **kv), "remedy": lambda **kv: fig_remedy(ctx, **kv),
            "fixes": lambda **kv: fig_fixes(ctx, **kv), "grasp": lambda **kv: fig_grasp(ctx, **kv),
            "dist": lambda **kv: fig_dist(ctx, **kv), "integrity": lambda **kv: fig_integrity(ctx, **kv),
            "fixrank": lambda **kv: fig_fixrank(ctx, **kv), "reason": lambda **kv: fig_reason(ctx, **kv),
            "reasonkinds": lambda **kv: fig_reasonkinds(ctx, **kv), "excluded": lambda **kv: fig_excluded(ctx, **kv),
            "crit": lambda **kv: fig_crit(ctx, **kv), "crit_time": lambda **kv: fig_crit_time(ctx, **kv),
            "after": lambda **kv: fig_after(ctx, **kv), "stuck": lambda **kv: fig_stuck(ctx, **kv),
            "reach": lambda **kv: fig_reach(ctx, **kv), "progress": lambda **kv: fig_reach(ctx, **kv),
            "grasp3": lambda **kv: fig_grasp3(ctx, **kv), "unsolved": lambda **kv: fig_unsolved(ctx, **kv),
            "deliv": lambda **kv: fig_deliv(ctx, **kv), "noreturn": lambda **kv: fig_noreturn(ctx, **kv),
            "nrafter": lambda **kv: fig_nrafter(ctx, **kv), "end": lambda **kv: fig_end(ctx, **kv),
            "overlap": lambda **kv: fig_overlap(ctx, **kv), "venn": lambda **kv: fig_venn(ctx, **kv),
            "trio": lambda **kv: fig_trio(ctx, **kv), "dots": lambda **kv: fig_dots(ctx, **kv)}
