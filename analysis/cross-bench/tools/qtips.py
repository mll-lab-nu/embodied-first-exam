"""Plain-Chinese hover text for every {{q:…}} number: what the denominator is and what the numerator counts.

tip(name, kv, value) -> str ("" when there is nothing useful to say). The words come from the codebook and figs, so a
code reads the same here as in the charts.
"""
from __future__ import annotations
import json, os, re
import common
import figs as FG
import queries as Q
from common import HERE

CB = FG.CB
SITE = json.load(open(os.path.join(HERE, "meta/site.json")))
BENCH = {b: v["name"] for b, v in SITE["benches"].items()}
STAGE = {k[0]: k[1] for k in FG.STAGES}
LOOP = {k[0]: k[1] for k in FG.LOOP}
TECH = dict(FG.TECH_ANN)
PERC = dict(FG.PERCEPTION)
FLAG = {**{f"tech_{k}": v for k, v in FG.TECH}, **{f"int_{k}": v for k, v in FG.INTEGRITY}}
GRASP = {k[0]: k[1] for k in FG.GRASP}
FAMILY = {k[0]: k[1] for k in FG.FAMILIES}
PHASE = {"q1": "前四分之一", "q2": "第二个四分之一", "q3": "第三个四分之一", "q4": "最后四分之一"}
WINDOW = {"short": "很短", "mid": "中等", "long": "很长"}
MED = {"dec_frac": "决定性错误发生的时刻", "nr_frac": "到不可挽回点的时刻", "fs_frac": "第一个征兆出现的时刻"}
SKIP = {"scope", "field", "value", "fmt", "flag", "with", "say", "at", "min", "show", "combo", "n"}
PROG = CB["progress_zh"]
RZ = CB["reason_zh"]
# progress-2 fields (meta/prompts/progress.md) -> codebook table; noticed reuses progress-1's yes / no / unclear names
PROG2 = {"no_return": PROG["no_return"], "end": PROG["end"], "nr_after": PROG["nr_after"],
         "nr_noticed": {k: v for k, v in PROG["noticed"].items() if k != "n/a"}}
PROG_NAMES = {"crit": {k: v[0] for k, v in PROG["critical"].items()}, "after": {k: v[0] for k, v in PROG["after"].items()},
              "noticed": {k: v[0] for k, v in PROG["noticed"].items()},
              "stuck": {k: f"第 {k} 级·{v[0]}" for k, v in PROG["level"].items()}, "best": {k: f"第 {k} 级·{v[0]}" for k, v in PROG["level"].items()},
              **{f: {k: v[0] for k, v in t.items()} for f, t in PROG2.items()}}
PROG_DEF = {f: {k: v[1] for k, v in t.items()} for f, t in PROG2.items()}
PROG_WHAT = {"crit": "关键点是", "after": "关键点之后的做法是", "noticed": "对关键点的察觉情况是", "stuck": "最后停在", "best": "最高到达",
             "no_return": "不可挽回点是", "end": "结束方式是", "nr_after": "不可挽回点之后的做法是", "nr_noticed": "对不可挽回点的察觉情况是"}
PROG_NOT = {"stuck": "最后停的不是", "best": "最高到的不是"}                 # value=!… of a field whose phrase has no 是
# value=!x,… where x is the "nothing happened" code: said as a plain phrase
PROG_SOME = {"crit": ("none", "有关键点"), "no_return": ("none", "有不可挽回点"), "nr_noticed": ("n/a", "有不可挽回点"),
             "after": ("n/a", "关键点之后还有时间做事"), "nr_after": ("n/a", "不可挽回点之后会话还持续了一分钟以上")}
PROG_MED = {"crit_t": "关键点落在时限的位置（占时限的比例）", "left": "关键点时还剩的时间占时限的比例",
            "left_min": "关键点时还剩的分钟数", "best_t": "第一次到达最高一级的时刻（占时限的比例）",
            "stuck_share": "停在最后一级的时间占会话用时的比例",
            "nr_t": "不可挽回点落在时限的位置（占时限的比例）", "nr_min": "不可挽回点发生在会话开始后的分钟数",
            "nr_left": "不可挽回点时离时限还剩的分钟数", "wasted": "不可挽回点之后继续做无用功的分钟数"}
PROG_MED_ONLY = {"nr_t": "有不可挽回点", "nr_min": "有不可挽回点", "nr_left": "有不可挽回点", "crit_t": "有关键点", "left": "有关键点",
                 "left_min": "有关键点"}
# thinking-error level after the when-1 split (queries.level2): a both label not yet split is 未细分
LEVEL2 = {**{k: v[0] for k, v in RZ["level"].items() if k != "both"}, "both": "未细分"}
LEVEL2_DEF = {**{k: v[1] for k, v in RZ["level"].items() if k != "both"}, "both": "高低层都有，还没判定哪个在先"}
# groups of review causes (codebook cause; queries.reason_rows pgroup = the group of the primary cause)
# names of label fields, trial columns and features without a table in figs (meta/codebook.json *_zh maps)
FIELD = CB["field_zh"]
AZ, IZ, VZ, TZ, FZ = CB["approach_zh"], CB["integrity_zh"], CB["validity_zh"], CB["trial_zh"], CB["feature_zh"]
DELIV = {k: v for k, v, _ in FG.DELIV}
LISTS = {"tech", "perception", "integrity", "secondary", "paradigm", "kinds", "groups", "any_fix", "any_subtype", "got",
         "tasktype", "cap"}  # match by membership: 含 (tasktype / cap: the Atlas fields, a task has several)
CAUSE_GROUP = {"understanding": "理解任务", "interface": "接口与约定", "perception": "感知", "control": "控制与接触",
               "planning": "计划", "method": "方法", "verification": "验证", "time": "时间与预算", "metacognition": "自我监控",
               "deliverable": "交付", "external": "外部原因", "other": "其他"}


def _names(field: str, vals: str, name: str = "", sep: str = "或") -> str:
    """'a,b' of one field -> 「甲」或「乙」. `name` is the q kind: kind is an integrity event kind in q:int (a thinking-error
    kind elsewhere), family a fix group in q:fix (a task family elsewhere: its own name)."""
    def one(v):
        if field == "kind" and name == "int":
            return AZ["integrity"].get(v, [v])[0]
        if field == "family" and name != "fix":
            return v
        if field in ("primary", "secondary", "any_cause"):
            return CB["cause_zh"].get(v, [v])[0]
        if field in ("fix", "any_fix"):
            return CB["fix_zh"].get(v, [v])[0]
        if field in FG.CODE_ZH:
            return FG.CODE_ZH[field].get(v, [v])[0]
        if field in ("level",):
            return RZ["level"].get(v, [v])[0]
        if field in ("level2", "when"):
            return LEVEL2.get(v, v)
        if field in ("kind", "kinds"):
            return RZ["kind"].get(v, [v])[0]
        if field == "groups":
            return RZ["group"].get(v, [v])[0]
        if field == "pgroup":
            return CAUSE_GROUP.get(v, v)
        if field in PROG_NAMES:
            return PROG_NAMES[field].get(v.lstrip("!"), v)
        table = {"stage": STAGE, "loop": LOOP, "tech": TECH, "perception": PERC, "subtype": GRASP, "any_subtype": GRASP,
                 "family": FAMILY, "would_pass": CB["would_pass_zh"], "who": CB["who_zh"], "dec_phase": PHASE, "nr_phase": PHASE,
                 "window": WINDOW, "claim": {k: v[0] for k, v in FG.CLAIM.items()}, "mode": FG.MODE_NAME, "bench": BENCH,
                 "category": FG.CAT_NAME, "outcome": {"success": "成功", "failure": "失败"}, "deliverable": DELIV,
                 **{f: {k: x[0] for k, x in t.items()} for f, t in AZ.items() if f != "note"},
                 **{f: {k: x[0] for k, x in t.items()} for f, t in {**IZ, **VZ, **TZ}.items() if f != "note"},
                 "rule_source": {k: x[0] for k, x in IZ["rule"].items()}, "way": LOOP}.get(field, {})
        return table.get(v, v)
    return sep.join(f"「{one(v)}」" for v in vals.split(","))


def _is(field: str, v: str, name: str = "") -> str:
    """field=v as a phrase from the field's name: 做法是「Code to Control（闭环）」; a list field 含; v=!a,b -> 不是「甲」「乙」."""
    neg, vals = v.startswith("!"), v.lstrip("!")
    lst = field in LISTS or (field == "kind" and name == "int")
    verb = ("不含" if lst else "不是") if neg else ("含" if lst else "是")
    label = "越界行为" if field == "kind" and name == "int" else FIELD.get(field, field)
    return f"{label}{verb}{_names(field, vals, name, '' if neg else '或')}"


def _flag(f: str, v: str) -> str:
    """A trial feature used as a field or filter (ended_after_hint=1 / 0)."""
    return FZ[f][0] if v not in ("0", "", "!1") else f"不属于「{FZ[f][0]}」"


def _not(field: str, v: str, name: str = "") -> str:
    """agent / bench / mode / category, plain: 'a,b' -> 甲、乙; '!a,b' -> 除甲、乙以外."""
    names = (_names(field, v.lstrip("!"), name, "、").replace("「", "").replace("」", "") if field != "agent"
             else "、".join(Q.agent_list(v.lstrip("!"))))           # agent=main: the six MAIN_AGENTS
    return (f"除 {names} 以外的 agent" if field == "agent" else f"除{names}以外" if field == "category" else f"除 {names} 以外") if v.startswith("!") else names


def _define(field: str, vals: str) -> str:
    """'（definition）' of a single value of a progress-2 or thinking-error field ("" for several values or none known)."""
    if "," in vals or vals.startswith("!"):
        return ""
    d = (PROG_DEF.get(field, {}).get(vals) or (LEVEL2_DEF.get(vals) if field == "level2" else "")
         or (RZ["group"].get(vals, ["", ""])[1] if field == "groups" else ""))
    return f"（{d}）" if d else ""


def _prog_phrase(k: str, v: str, define: bool = False) -> str:
    """A progress field and value as a phrase: crit=time-out -> 关键点是「超时」; v=!a,b -> the rest (no_return=!none ->
    有不可挽回点); define adds the definition of a single value."""
    if not v.startswith("!"):
        return PROG_WHAT[k] + _names(k, v) + (_define(k, v) if define else "")
    vals = v[1:].split(",")
    base, some = PROG_SOME.get(k, (None, ""))
    rest = [x for x in vals if x != base]
    neg = PROG_NOT.get(k) or PROG_WHAT[k].replace("是", "不是", 1)
    return "、".join(([some] if base in vals else []) + ([neg + _names(k, ",".join(rest)).replace("」或「", "」「")] if rest else []))


def _prog_kv(kv: dict) -> dict:
    """The filters a progress query really applies (queries.prog_kv), outcome first, then the label version."""
    full = Q.prog_kv(kv)
    head = {k: full[k] for k in ("outcome", "v2", "v1") if k in full}
    return {**head, **{k: v for k, v in full.items() if k not in head}}


def _filters(kv: dict, name: str = "") -> str:
    """The filters of a placeholder as a short phrase (empty when none); `name` is the q kind (see _names)."""
    out = []
    for k, v in kv.items():
        if k in SKIP:
            continue
        if k in ("agent", "mode", "bench", "category"):
            out.append(_not(k, v, name))
        elif k == "outcome":
            out.append({"success": "成功的", "failure": "失败的"}.get(v, "成功和失败的"))
        elif k == "v2":                                       # set by queries.prog_kv for a progress-2 field
            out.append("标注了不可挽回点和结束方式的" + ("，成功的 trial 没有这项标注时按「无不可挽回点」「达成目标」算"
                                                       if kv.get("outcome") != "failure" else ""))
        elif k == "filter":                                   # q:rate filter=drop (queries.perf_pool)
            out.append("不算被内容过滤器掐断的会话" if v == "drop" else _is(k, v, name))
        elif k == "v1":
            out.append("只算旧版（关键点）标注的")
        elif k in ("base", "task"):
            n = len(v.split(","))
            out.append(f"指定的 {n} 个任务" if n > 1 else f"任务 {v}")
        elif k == "primary":
            out.append(f"主因是{_names(k, v)}")
        elif k == "stage":
            out.append(f"决定性错误在{_names(k, v)}阶段")
        elif k == "fix":
            out.append(f"分析认为最该补的一步是{_names(k, v)}")
        elif k == "family" and name == "fix":
            out.append(f"分析认为最该补的一步属于{_names(k, v, name)}一组")
        elif k == "family":
            out.append(_is(k, v, name))
        elif k == "kind" and name == "int":
            out.append(_is(k, v, name))
        elif k == "success":
            out.append(_names(k, v, name).strip("「」") + "的" if v in ("0", "1") else _is(k, v, name))
        elif k in FZ:
            out.append(_flag(k, v))
        elif k == "exception" and v == "":
            out.append("harness 没有报异常")
        elif k == "planned_budget":
            out.append("按预算排了计划" if v == "True" else "没有按预算排计划")
        elif k == "would_pass":
            out.append(f"判为{_names(k, v)}翻盘")
        elif k == "who":
            out.append(f"要由{_names(k, v)}改")
        elif k in ("level", "level2"):
            out.append(f"层级是{_names(k, v)}")
        elif k == "when":
            out.append(f"高低层都有、先后判为{_names(k, v)}")
        elif k == "groups":
            out.append(f"高层错误含{_names(k, v)}一类")
        elif k == "pgroup":
            out.append(f"主因属于{_names(k, v)}一类")
        elif k in ("kind", "kinds"):
            out.append(f"{'第一类高层错误是' if k == 'kind' else '高层错误含'}{_names(k, v)}")
        elif k == "subtype":
            out.append(f"方式是{_names(k, v)}")
        elif k == "reviewer":                                  # reviewer=!sonnet,haiku: the subset whose label is reliable for this field
            out.append("只算这一项标注可靠的分析")                 # user rule 10-18: never name the model that wrote an analysis
        elif k == "loop":
            out.append(f"做法是{_names(k, v)}")
        elif k == "clock_aware":
            out.append("看过时钟" if v == "True" else "没看过时钟")
        elif k in PROG_WHAT:                                  # crit=!none,time-out -> 有关键点、关键点不是「超时」
            out.append(_prog_phrase(k, v))
        else:
            out.append(_is(k, v, name))
    if kv.get("with"):
        out.append(Q.CORE_ALL if Q.ACTIVE == "core" and kv["with"] == "main" else f"只算{'六家主要 agent（' + '、'.join(Q.MAIN_AGENTS) + '）' if kv['with'] == 'main' else '、'.join(kv['with'].split(','))}都评过分的评测项")
    return "；".join(out)


def _what(field: str, value: str, name: str = "") -> str:
    """What the numerator counts, for field=value; `name` is the q kind (see _names)."""
    if field == "primary":
        return f"主因是{_names(field, value)}"
    if field == "secondary":
        return f"次因含{_names(field, value)}"
    if field == "any_cause":
        return f"主因或次因含{_names(field, value)}"
    if field == "stage":
        return f"决定性错误在{_names(field, value)}阶段"
    if field == "clock_aware":
        return "看过时钟" if value == "True" else "没看过时钟"
    if field == "planned_budget":
        return "按预算排了计划" if value == "True" else "没有按预算排计划"
    if field in ("dec_phase", "nr_phase"):
        return f"{'决定性错误' if field == 'dec_phase' else '不可挽回点'}落在时限的{_names(field, value)}"
    if field == "fix":
        return f"分析认为最该补的一步是{_names(field, value)}"
    if field == "any_fix":
        return f"分析列出的可补步骤（最该补的一步或其他可补的步骤）含{_names(field, value)}"
    if field == "family" and name == "fix":
        return f"分析认为最该补的一步属于{_names(field, value, name)}一组"
    if field == "who":
        return f"分析认为最该补的一步要由{_names(field, value)}来做"
    if field == "would_pass":
        return f"判为只做这一处改动、这次{_names(field, value)}成功"
    if field in ("subtype", "any_subtype"):
        return f"抓取失败方式是{_names(field, value)}"
    if field == "level":
        return f"层级是{_names(field, value)}"
    if field == "level2":
        return f"层级是{_names(field, value)}{_define(field, value)}"
    if field == "when":
        return f"高低层都有、先后判为{_names(field, value)}"
    if field in ("kind", "kinds") and name != "int":
        return f"{'第一类' if field == 'kind' else ''}高层错误是{_names(field, value)}"
    if field == "groups":
        return f"高层错误含{_names(field, value)}一类{_define(field, value)}"
    if field == "pgroup":
        return f"主因属于{_names(field, value)}一类"
    if field in ("bench", "mode", "category", "agent"):
        return f"属于{_names(field, value)}"
    if field in ("outcome", "success") and not value.startswith("!") and "," not in value:
        return _names(field, value).strip("「」")
    if field in FZ:
        return _flag(field, value)
    return _is(field, value, name)


UNIT = {"rev": "条随机抽样的分析记录", "ann": "条随机抽样的做法标注（每条对应一个分析过的 trial）", "fix": "个随机抽样分析过的失败（有改动标注）",
        "grasp": "个随机抽样的抓取/接触失败（分析里主因或次因是抓取/接触）", "reason": "个随机抽样分析过的失败（有高层错误标注）",
        "int": "条越界分析记录（从有越界信号或被监控标到的 trial 里抽样）"}


def _prog_what(kv: dict) -> str:
    """What a q:prog numerator counts."""
    f, v = kv.get("field"), kv.get("value", "")
    return (f"到时限的 {kv.get('at', '100')}% 时已到达第 {v} 级（{PROG['level'].get(v, [v])[0]}）或更高" if f == "reach" else
            _prog_phrase(f, v, define=True) if f in PROG_WHAT else _what(f, v) if f else "符合条件")


def _feat(kv: dict) -> tuple[str, str, str, str]:
    """q:feat -> (pool, filters, what the numerator counts, how it is known). The pool is the scope's trials that left a
    trajectory (queries.q_feat): scope=finished takes every finished trial, the ones left out of the statistics too."""
    rest = {k: v for k, v in kv.items() if k != "flag"}
    if kv.get("scope") == "finished":
        v = rest.pop("validity", "") if not kv.get("validity", "").startswith("!") else ""
        pool = f"留下轨迹、判为{_names('validity', v)}的 trial" if v else "留下轨迹的跑完的 trial（含不计入统计的）"
    else:
        pool = ("Luna 没过的评测项上" if kv.get("scope") == "open" and Q.ACTIVE != "core" else "") + "留下轨迹的有效 trial"
    f = kv.get("flag", "")
    what, how = FZ[f] if f in FZ else (f"命令文本里出现「{FLAG.get(f, f)}」信号", "按文本识别，是近似值")
    return pool, _filters(rest, "feat"), what, how


def counted(name: str, kv: dict) -> str:
    """The caption of a {{bars:…}} strip, one sentence: what its k/n counts and out of what, in the words of tip() but
    without numbers (each row's own tip gives its filter and numbers). "" for a kind without k/n."""
    filt = _filters(kv, name)
    paren = lambda t: f"（{t}）" if t else ""
    if name == "rate":
        rest = _filters({k: v for k, v in kv.items() if k not in ("mode", "with", "agent")}, name)
        ags = Q.agent_list(kv["agent"]) if kv.get("agent") and not kv["agent"].startswith("!") else []
        who = ("三家合计" if sorted(ags) == sorted(Q.TRIO.values()) else "六家合计" if ags == list(Q.MAIN_AGENTS)
               else "、".join(ags) + ("合计" if len(ags) > 1 else "")) if ags else \
            _filters({"agent": kv["agent"]}, name) if kv.get("agent") else ""
        where = [who, "Luna 没过的" if kv.get("scope", "open") == "open" and Q.ACTIVE != "core" else "",
                 _not("mode", kv["mode"]) if kv.get("mode") else "", (Q.CORE_ALL if Q.ACTIVE == "core" else f"{_who_short(kv['with'])}都评过分的") if kv.get("with") else "", rest]
        return f"每条是做成数/评测项数{paren('，'.join(w for w in where if w))}；评分程序判定成败。"
    if name == "unsolved":
        rest = _filters({k: v for k, v in kv.items() if k not in ("with", "agent")}, name)
        return Q.batch_words(f"每条是无人做成数/{_who_short(kv.get('with') or kv.get('agent') or 'main', kv.get('min'))}都评过分的评测项数{paren(rest)}。")
    if name == "prog":
        filt = _filters(_prog_kv(kv))
        return f"每条 = {_prog_what(kv)}的数/有进展标注的抽样 trial 数{paren(filt)}；分析认定。"
    if name == "feat":
        pool, filt, what, how = _feat(kv)
        return f"每条 = {what}的数/{pool}数{paren(filt)}，{how}。"
    if name in UNIT:
        what = _what(kv["field"], kv.get("value", ""), name) if kv.get("field") else "符合条件"
        unit = UNIT[name][1:] if UNIT[name][0] in "条个" else UNIT[name]
        return f"每条 = {what}的数/{unit}数{paren(filt)}" + ("，按层加权" if common.WEIGHTS else "") + "。"
    return ""


def _who_short(v: str, at_least: str | None = None) -> str:
    """An agent list for a one-sentence caption: 六家 for the six main agents (with=main), else the names."""
    names = Q.agent_list(v)
    return f"至少 {at_least} 家" if at_least else "六家" if names == list(Q.MAIN_AGENTS) else "、".join(names)


OVERLAP = {"all3": "三家都做成", "astra+argon": "只有 GPT-6 Astra 和 Gemini 4 Argon 做成", "astra+opus": "只有 GPT-6 Astra 和 Opus 5.5 做成",
           "argon+opus": "只有 Gemini 4 Argon 和 Opus 5.5 做成", "astra": "只有 GPT-6 Astra 做成", "argon": "只有 Gemini 4 Argon 做成",
           "opus": "只有 Opus 5.5 做成", "none": "三家都没做成", "union": "三家里至少一家做成", "best": "三家里做成最多的那一家做成"}
RATE_POOL = "评测看板上评过分的评测项（每个 agent 每个评测项取最新一次合规运行，全量结果，不是抽样）"


def _who(kv: dict) -> str:
    """Whose grades make an unsolved cell (queries.run_cells): all six main agents by default."""
    names = Q.agent_list(kv.get("with") or kv.get("agent") or "main")
    return (f"至少 {kv['min']} 家（{'、'.join(names)}）" if kv.get("min") and not kv.get("with")
            else "六家主要 agent（" + "、".join(names) + "）" if names == list(Q.MAIN_AGENTS) else "、".join(names))


def _where(kv: dict) -> str:
    return "全部评测项" if kv.get("scope") == "all" or Q.ACTIVE == "core" else "Luna 没过的评测项"      # core: no Luna, every item


def tip(name: str, kv: dict, value: str) -> str:
    m = re.search(r"(\d+)/(\d+)", str(value))
    k, n = (m.group(1), m.group(2)) if m else ("", "")
    filt = _filters(kv, name)
    scope = "" if filt else "（不加筛选）"
    if name == "rate" and m:
        return (f"评测看板上评过分的评测项 {n} 个，其中成功 {k} 个（每个 agent 每个评测项取最新一次合规运行，全量结果，不是抽样）。"
                f"范围：{_where(kv)}" + (f"；{filt}" if filt else "") + "。")
    if name == "overlap" and m:
        return (f"分母：{n} 个" + (f"{Q.CORE_ALL}的评测项（评测看板的全量结果）" if Q.ACTIVE == "core" else f"六家主要 agent（{'、'.join(Q.MAIN_AGENTS)}）都评过分的评测项（评测看板的全量结果）")
                + (f"；{filt}" if filt else "") + f"。分子：其中{OVERLAP.get(kv.get('combo', 'all3'), kv.get('combo'))}的 {k} 个。")
    if name == "unsolved" and m:
        return (f"分母：{n} 个{_who(kv)}都评过分的评测项（任务×模式，评测看板的全量结果）" + (f"；{filt}" if filt else "")
                + f"。分子：其中没有一家成功的 {k} 个。")
    if name == "med":
        return f"{MED.get(kv.get('field'), kv.get('field'))}占时限比例的中位数" + (f"；{filt}" if filt else "") + "。"
    if name in ("prog", "progmed"):
        f = kv.get("field")
        filt = _filters(_prog_kv({x: y for x, y in kv.items() if x != "fmt"}))
        if name == "progmed":
            pool = f"有进展标注的随机抽样 trial{('（' + filt + '）') if filt else ''}" + (f"里{PROG_MED_ONLY[f]}的" if f in PROG_MED_ONLY else "")
            if kv.get("fmt") == "iqr":
                return f"{PROG_MED.get(f, f)}的四分位范围：参与计算的 trial 里，中间一半落在这个范围。参与计算的是{pool}。分析认定。"
            nm = re.search(r"（n=(\d+)）", str(value))
            return f"{PROG_MED.get(f, f)}的中位数" + (f"，{nm.group(1)} 个 trial 参与计算" if nm else "") + f"。参与计算的是{pool}。分析认定。"
        if m:
            return f"分母：{n} 个有进展标注的随机抽样 trial{('（' + filt + '）') if filt else ''}。分子：其中{_prog_what(kv)}的 {k} 个。分析认定。"
    if name == "feat" and m:
        pool, filt, what, how = _feat(kv)
        return f"分母：{n} 个{pool}{('（' + filt + '）') if filt else ''}。分子：其中{what}的 {k} 个（{how}）。"
    if name in UNIT and m:
        what = _what(kv["field"], kv.get("value", ""), name) if kv.get("field") else "符合条件"
        return (f"分母：{n} {UNIT[name]}{('（' + filt + '）') if filt else scope}。分子：其中{what}的 {k} 个"
                + ("（按层加权后取整）" if common.WEIGHTS else "") + "。")
    if name in UNIT and kv.get("fmt") == "pct":
        return f"占比的分母是{UNIT[name][1:] if UNIT[name][0] in '条个' else UNIT[name]}{('（' + filt + '）') if filt else ''}。"
    return ""
