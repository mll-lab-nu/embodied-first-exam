"""Builds evidence/medium_layout/r1_move_eval.{md,png,json} from the raw result lists (A: R1 only, B: R2 only, C: both).
Usage: python r1_move_report.py resAB.json resC.json"""
import json, sys, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import r1_move_summary as S
import r1_move_plot as G
import r1_move_eval as R
import gen_jobs_r1move as J

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evidence", "medium_layout")
res = []
for f in sys.argv[1:]:
    res += json.load(open(f))
GROUPS = dict(A="A 只挪 R1", B="B 只挪 R2", C="C R1 与 R2 一起挪")
for o in res:
    R.SPEC = o["job"]["spec"]; _rings, _ = R.place_patched(R.YAW, R.T0); R.SPEC = {}
    _s3 = o["geo"]["start_to_R3"]
    o["geo"] = R.geometry(_rings, R.M.ROPE + np.array([0, 0, 0.75]), None); o["geo"]["start_to_R3"] = _s3      # recomputed (adds the entry-side numbers)
    o["strict_flags"], o["loose_flags"] = S.flags(o, True), S.flags(o, False)
    o["first_fail_strict"], o["first_fail_loose"] = S.first_fail(o["strict_flags"]), S.first_fail(o["loose_flags"])
    o["disp_m"], o["rot_deg"] = S.disp(o["job"]["spec"])
    o["spec_txt"] = S.label(o["job"]["spec"])
base = next(o for o in res if o["job"]["group"] == "A" and o["job"]["spec"]["R1"] == [0, 0, 0])


def rows(g):
    return [o for o in res if o["job"]["group"] == g]


def key(o):
    return (round(o["disp_m"], 4), o["rot_deg"])


def best(g, strict=True):
    ok = [o for o in rows(g) if all((o["strict_flags"] if strict else o["loose_flags"]).values())]
    if g == "C":        # C only counts when R1 really moves (otherwise it is group B)
        ok = [o for o in ok if any(abs(x) > 1e-9 for x in o["job"]["spec"]["R1"])]
    return sorted(ok, key=key)


def robust(o):          # total strict R2-exit-receive poses (static probe + cone-20 stroke), both arms
    return sum(o["R2_probe"][s]["poses"] for s in ("left", "right")) + sum(o["R2_recv_cone20"][s]["poses"] for s in "lr")


def fmt(o):
    p = o["R2_probe"]; c = o["R2_recv_cone20"]
    return (f"| {o['spec_txt']} | {100*o['disp_m']:.1f} | {o['rot_deg']:.0f} | {S.lr(o['R3_feed'])} | {S.lr(o['R3_recv'])} | {o['R3_hand']['RL']}/{o['R3_hand']['LR']} | {S.lr(o['R2_feed'])} "
            f"| {p['left']['poses']}/{p['right']['poses']} | {p['left']['ik_unsolvable']}/{p['right']['ik_unsolvable']} | {c['l']['poses']}/{c['r']['poses']} | {S.lr(o['R2_recv'])} | {S.lr(o['R1_feed'])} "
            f"| {o['R2_hand']['RL']}/{o['R2_hand']['LR']} | {o['R2recv_R1feed_pairs']['RL']}/{o['R2recv_R1feed_pairs']['LR']} | {o['first_fail_loose'] or '-'} | {o['first_fail_strict'] or '-'} |")


HEAD = ("| 挪动 | 位移 cm | 转角 ° | R3 喂 左/右 | R3 接 左/右 | R3 转交 RL/LR | R2 喂 左/右 | R2 出口接收(静态) 左/右 | 其中 IK 不可解 左/右（共 270 候选） | R2 出口接收(cone20 行程) 左/右 | R2 接(行程0.07-0.20) 左/右 | R1 喂 左/右 | R2 转交 RL/LR "
        "| R2接→R1喂 转交对 RL/LR | 第一个不行(宽) | 第一个不行(严) |\n|" + "---|" * 16)

# --- candidates
cands = {}
for g in "ABC":
    s = best(g, True)
    tr = [o for o in s if o["rot_deg"] == 0]
    cands[g] = dict(min=s[0] if s else None, min_translation=tr[0] if tr else None, robust=max(s, key=robust) if s else None, n_strict=len(s), n_loose=len(best(g, False)))
# no candidate -> the most promising: only the entry-side check fails (smallest move), else most strict receive poses among rows failing at R2_recv
def fails(o):
    return [s for s in S.STEPS if not o["strict_flags"][s]]


for g in "ABC":
    nf = [o for o in rows(g) if (g != "C" or any(abs(x) > 1e-9 for x in o["job"]["spec"]["R1"])) and all({k: v for k, v in o["strict_flags"].items() if k != "entry_side"}.values())]
    cands[g]["ignoring_entry"] = min(nf, key=key) if nf else None
    if cands[g]["min"] is None:
        only = sorted([o for o in nf if fails(o) == ["entry_side"]], key=key)
        cand = [o for o in rows(g) if o["first_fail_strict"] == "R2_recv"]
        cands[g]["promising"] = only[0] if only else (max(cand, key=robust) if cand else None)

json.dump(dict(baseline=base["job"], results=res, candidates={g: {k: (v["job"]["spec"] if isinstance(v, dict) else v) for k, v in c.items()} for g, c in cands.items()}),
          open(os.path.join(OUT, "r1_move_eval.json"), "w"), default=str, indent=0)

# --- IK-unsolvable statistics
def iku(g):
    r = rows(g)
    return (sorted({o["R2_probe"]["left"]["ik_unsolvable"] for o in r}), sorted({o["R2_probe"]["right"]["ik_unsolvable"] for o in r}))
for g in "ABC":
    print(g, "ik_unsolvable left", iku(g)[0][:4], "...", iku(g)[0][-2:], "right", iku(g)[1][:4], iku(g)[1][-2:])
print({g: (c["n_strict"], c["n_loose"], c["min"]["spec_txt"] if c["min"] else None) for g, c in cands.items()})


# --- figure
plt.rcParams.update({"font.size": 24})
SHORT = dict(ready="准备", pick="捡绳", transition="过渡", R3_feed="R3喂", R3_recv="R3接", R3_hand="R3转交", R2_feed="R2喂", R2_recv="R2接", R2_hand="R2转交",
             R1_feed="R1喂", R2_to_R1="R2→R1", geometry="几何", entry_side="入口侧")
fig = plt.figure(figsize=(32, 36), dpi=100)
gs = fig.add_gridspec(2, 2, hspace=0.30, wspace=0.10)
pick = {g: (cands[g]["min"] or cands[g].get("promising")) for g in "ABC"}


def note(g, o):
    p, c = o["R2_probe"], o["R2_recv_cone20"]
    st = "全部步骤可行（严判据）" if o is cands[g]["min"] else "仍不可行：未通过 " + "、".join(SHORT.get(x, x) for x in fails(o)).replace("entry_side", "入口侧")
    return (f"挪动 {o['spec_txt']}\n位移 {100*o['disp_m']:.0f} cm（两环各自计），转角合计 {o['rot_deg']:.0f}°\n"
            f"R2 出口接收 左/右：静态 {p['left']['poses']}/{p['right']['poses']}，cone20 行程 {c['l']['poses']}/{c['r']['poses']}\n"
            f"IK 不可解 左/右（共 270）：{p['left']['ik_unsolvable']}/{p['right']['ik_unsolvable']}（原位 {base['R2_probe']['left']['ik_unsolvable']}/{base['R2_probe']['right']['ik_unsolvable']}）\n"
            f"R2 中心到 R1 环面的法向距离 {100*o['geo']['r2_to_r1plane_normal']:.0f} cm（原位 {100*base['geo']['r2_to_r1plane_normal']:.0f} cm；<0 = R2 在 R1 出口侧）\n"
            f"R1 喂 左/右 {S.lr(o['R1_feed'])}；{st}")


for g, pos in (("A", gs[0, 0]), ("B", gs[0, 1]), ("C", gs[1, 0])):
    ax = fig.add_subplot(pos)
    o = pick[g]
    if o is None:
        ax.axis("off"); continue
    G.draw_group(ax, {n: tuple(v) for n, v in o["job"]["spec"].items()},
                 f"({g}) {GROUPS[g]}：{'最小可行挪动' if o is cands[g]['min'] else '最有希望（仍不可行）'}\n灰虚线=原位，蓝=新位，红箭头=挪动", note(g, o))
    for t in ax.texts:
        if t.get_fontsize() < 21:
            t.set_fontsize(21)
sub = gs[1, 1].subgridspec(1, 2, wspace=0.55)
for k, (g, xs, ys) in enumerate((("A", [0, 3, 6, 9, 12], [0, 3, 6, 9, 12]), ("B", [-10, -6, -3, 0, 3, 6, 10], [-10, -6, -3, 0, 3, 6, 10]))):
    ax = fig.add_subplot(sub[k])
    nm = "R1" if g == "A" else "R2"
    Z = np.full((len(ys), len(xs)), np.nan); FF = {}
    for o in rows(g):
        v = o["job"]["spec"][nm]
        if abs(v[2]) < 1e-9 and round(v[0] * 100) in xs and round(v[1] * 100) in ys:
            iy, ix = ys.index(round(v[1] * 100)), xs.index(round(v[0] * 100))
            Z[iy, ix] = o["R2_probe"]["left"]["poses"]; FF[(iy, ix)] = o["first_fail_strict"]
    ax.imshow(Z, origin="lower", cmap="YlGn", vmin=0, vmax=max(5, np.nanmax(Z)))
    for iy in range(len(ys)):
        for ix in range(len(xs)):
            if np.isnan(Z[iy, ix]):
                ax.text(ix, iy, "×", ha="center", va="center", fontsize=22, color="#999"); continue
            ff = FF[(iy, ix)]
            other = ff not in (None, "R2_recv")
            ax.text(ix, iy + (0.12 if other else 0), "%d" % Z[iy, ix], ha="center", va="center", fontsize=22, color="k")
            if other:
                ax.text(ix, iy - 0.25, SHORT[ff], ha="center", va="center", fontsize=15, color="#b03a2e")
    ax.set_xticks(range(len(xs))); ax.set_xticklabels(xs); ax.set_yticks(range(len(ys))); ax.set_yticklabels(ys)
    ax.set_xlabel(f"{nm} 的 dx (cm)，+x 远离机器人", fontsize=22); ax.set_ylabel("dy (cm)，+y 向左", fontsize=22)
    iu = iku(g); lo, hi = iu[0][0], iu[0][-1]
    ax.set_title(f"({'D' if g == 'A' else 'E'}) 只挪 {nm}，转角 0\n左手 R2 出口接收\n静态可行姿态数\nIK 不可解(左) {lo}" + (f"–{hi}" if hi != lo else "（恒定）") + "/270",
                 fontsize=21)
    if g == "A":
        ax.text(0, -0.42, "×=几何无效/未算；格内小红字=该格第一个不行的其他步骤（严判据）\n绿星=材料起点(被喂入)，橙点=材料终点；红箭头=挪动", transform=ax.transAxes, fontsize=21, va="top")
    ax.tick_params(labelsize=20)
fig.savefig(os.path.join(OUT, "r1_move_eval.png"), bbox_inches="tight")
print("png", fig.get_size_inches() * 100)


# --- markdown
def cand_rows(lst):
    return "\n".join(fmt(o) for o in lst)


def geo_row(name, o):
    g = o["geo"]; cd, rg, a = g["center_dist"], g["ring_gap"], g["arc_final_from_start_tip"]
    return (f"| {name} | {100*cd['R1R2']:.1f} / {100*cd['R2R3']:.1f} | {100*rg['R1R2']:.1f} / {100*rg['R2R3']:.1f} | {100*g['r2_to_r1plane_normal']:.1f} | {100*g['r2_to_r1_inplane']:.1f} | "
            f"{g['r2exit_vs_r1travel_deg']:.0f} | {g['chord_R2R1_vs_R2_exit_deg']:.0f} | {g['chord_R2R1_vs_R1_travel_deg']:.0f} | "
            f"{a['R1']:.2f} / {a['R2']:.2f} / {a['R3']:.2f} | {1.1 - a['R3']:.2f} |")


GEO_HEAD = ("| 布局 | 环心距 R1–R2 / R2–R3 (cm) | 环面最小间隙 R1–R2 / R2–R3 (cm) | R2 中心到 R1 环面的法向距离 (cm) | 其面内偏移 (cm) | R2 出口方向与 R1 环面法向夹角 (°) "
            "| R2 出口方向与 R2→R1 连线夹角 (°) | R2→R1 连线与 R1 行进方向夹角 (°) | 绳在各环的穿越点离材料起点端的弧长下界 R1 / R2 / R3 (m) | 绳余量 1.1−R3 弧长 (m) |\n|" + "---|" * 11)
md = []
P = md.append
nA, nB, nC = (len(rows(g)) for g in "ABC")
invalid = {}
for g, f in (("A", J.jobs_A), ("B", J.jobs_B), ("C", J.jobs_C)):
    invalid[g] = [j for j in f() if not J.check(j)[0]]
mA, mB, mC = (cands[g]["min"] for g in "ABC")
P("# R1 / R2 挪动的离线评估（yaw 195，反向穿法：材料起点先穿 R3 → R2 → R1，右手捡绳）\n")
P("只评估，不改任何文件、不跑 Isaac。工具 `tools/r1_move_eval.py`（评估）、`gen_jobs_r1move.py`（扫描点）、`r1_move_summary.py`（判据）、`r1_move_plot.py` / `r1_move_report.py`（图与本文）；"
  "原始数据 `r1_move_eval.json`，图 `r1_move_eval.png`。numpy 离线，6 进程，OMP_NUM_THREADS=1。\n")
P("## 结论\n")
P(f"1. **只挪 R1（A，{nA} 个有效点，位移 0–12 cm × 转角 ±15°）：没有任何挪动让全部步骤可行。** 不是 R2 出口接收的 IK 不可解变少——"
  f"R2 出口接收的 270 个候选里，左手 IK 不可解 **恒为 228**、右手 **恒为 219**，在 A 的全部 {nA} 个挪动里一个都没变（R2、两臂基座都没动，R1 只进碰撞项）。"
  f"R1 挪开只是把“撞 R1 环”的候选（原位左 41 / 右 47）放出来：例如 R1 (+12,+9) cm、+15° 时左 31 / 右 31 个候选可行（14 / 17 个姿态）。"
  f"但凡让 R2 出口接收有解（cone20 行程>0）的 A 挪动，R2 中心都落到 R1 环面的出口侧（法向距离 ≤ 0，原位 +10 cm）：绳头出 R2 后得绕过 R1 再从另一面穿入，"
  f"入口侧检查通过且 R2 出口接收 cone20 行程>0 的 A 挪动：0 个。A 里最接近的是 R1 (+12,+9) cm、+15°（位移 15 cm，全部离线步骤都过，仅入口侧不过：法向 −8.8 cm）。")
mBt = cands["B"]["min_translation"]
P(f"2. **只挪 R2（B，{nB} 个有效点，另有 {len(invalid['B'])} 个因底座出桌/底座间隙<2 cm/环间隙<2 cm 未评估）：有可行挪动，{cands['B']['n_strict']} 个全部步骤可行（严判据）。** "
  f"最小（位移优先）= {mB['spec_txt']}（只转不平移）；最小纯平移 = {mBt['spec_txt']}（3 cm）。R2 挪动**会**改变 R2 出口接收的 IK 不可解个数"
  f"（左 {iku('B')[0][0]}–{iku('B')[0][-1]}、右 {iku('B')[1][0]}–{iku('B')[1][-1]}，原位 228 / 219），因为出口点相对臂基座的位置变了；"
  f"同时 R2 喂的解数也大增（原位 左 0 / 右 6 → R2 转 −20°：左 12 / 右 19）。最稳（严判据下 R2 出口接收姿态最多）= {cands['B']['robust']['spec_txt']}。")
P(f"3. **R1、R2 一起挪（C，{nC} 个有效点）：{cands['C']['n_strict']} 个全部可行；R1 真的动了的最小者 = {cands['C']['min']['spec_txt']}（两环各 3 cm，合计 6 cm）。** "
  f"相对 B 没有增益：C 里所有能过的点，R2 出口接收的可行都来自 R2 的动（沿 +y 的平移或 −20° 转），R1 的动只改 R1 喂（左 14 → 7 或 0，R1 转 −15° 时 0）。")
P("4. 选哪个：**挪 R2 即可，不需要挪 R1**；R2 只需转 −20°（不平移）或沿 +y 3 cm。数字很小（左手 1–6 个姿态），属“刚好可行”而非“宽裕”，见局限。\n")
P("## 判据与方法（与 layout_eval 一致，加 R2 出口接收的静态探针）\n")
P("- 路线：反向（材料起点先穿，R3 → R2 → R1），布局固定 yaw 195、t=(0.54,0.12)、绳起点 yaw 90°、t=(0.58,−0.05)；挪动 = 环、底座、立柱一起平移 (dx,dy)，并绕经过环心的竖直轴转（转的是法向的水平方位角，环高度、倾角不变）。R3、绳起点、没挪的环不动。")
P("- 每个挪动跑 `layout_eval.evaluate_layout`（thetas=[0]）：ready、捡绳、捡绳末态→喂入、R3 喂/接/转交、R2 喂/接/转交、R1 喂；喂/接 = `stroke_solutions` 行程（法向偏差 ≤25°，approach 每 30°，IK 多起点 margin 0.03，胶囊间隙 ≥1 cm）。")
P("- **R2 出口接收（用户定义，静态探针）**：绳与夹爪 z 轴夹角 ≤20°（5 个方向：法向、±15° 方位/俯仰）、approach 每 30°（不从下方）、绳横在指垫上（±z）、grip 点取 R2 面后 0.05/0.07/0.10 m（按新位的环心和法向重算）→ 270 个候选/臂；IK 多起点 margin 0.03，间隙 ≥1 cm（对三个环 + 桌面；未算对另一臂的碰撞）。"
  "“姿态数”= 至少一个 grip 深度可行的不同 (方向, approach, ±z)；另给“IK 不可解”个数（270 候选里无 IK 解的数）和“撞哪个环”。")
P("- 另列 R2 出口接收的行程版（`stroke_diag`，cone 20°，面后 0.07→0.20 m，与 `yaw315_r2recv.json` 同法）和 layout_eval 的 R2 接（cone 25°）。原位这两个行程版左 0 / 右 0（cone20）与左 1 / 右 0（cone25），与实跑卡在 R2 出口一致；静态探针原位左 1 / 右 0，比实跑乐观。")
P("- **宽判据**：所有步骤 >0，R2 出口接收 = 静态探针任一臂 >0（原位就通过，不能区分）。**严判据（本文用它选最小）**：R2 出口接收 = 静态探针任一臂 >0 **且** 与 cone20 行程同臂 >0（原位不通过，和实跑一致）；其余步骤同宽；"
  "“R2→R1 衔接”= 能接 R2 的臂同时能喂 R1，或不同臂的 接→喂 转交对 >0（手间距 ≥12 cm、胶囊 ≥1 cm）；“几何”= R1/R2/R3 底座角点和立柱落在桌面碰撞体内（margin 0.01，x 0.3025..0.8975，y ±0.65）、底座间隙 ≥2 cm、环间最小间隙 ≥2 cm；"
  "“入口侧”= R2 中心在 R1 环面入口侧（沿 R1 行进方向 (c1−c2)·t1 > 2 cm）且 R3 在 R2 入口侧（(c2−c3)·t2 > 2 cm）——挪动后绳头出 R2 必须能从 R1 的入口面穿入，不绕到环后面。")
P("- 最小 = 位移（各环位移之和）先、转角（合计）后；C 只在 R1 确实动了（平移或转角 ≠ 0）时计入。\n")
P("## 每组汇总\n")
P("| 组 | 有效点 | 未评估(几何无效) | 严判据全可行 | 宽判据全可行 | 严判据下第一个不行的步骤分布 | IK 不可解 左 | IK 不可解 右 |\n|---|---|---|---|---|---|---|---|")
from collections import Counter
for g in "ABC":
    cnt = Counter(o["first_fail_strict"] or "全可行" for o in rows(g))
    iu = iku(g)
    P(f"| {GROUPS[g]} | {len(rows(g))} | {len(invalid[g])} | {cands[g]['n_strict']} | {cands[g]['n_loose']} | " + "，".join(f"{k} {v}" for k, v in cnt.most_common()) +
      f" | {iu[0][0]}–{iu[0][-1]}{'（恒定）' if iu[0][0] == iu[0][-1] else ''} | {iu[1][0]}–{iu[1][-1]}{'（恒定）' if iu[1][0] == iu[1][-1] else ''} |")
P("\n注：A 里“准备（ready）”不通过的 23 个点全部是 dy ≥ 6 cm 的点（dy ≥ 6 共 45 点）：ready 姿态的无碰撞路径被挪过来的 R1 挡住。")
P("\n## (1) 最小可行挪动及每步解数\n")
P("格式：左/右 = 左手/右手可行解数；“转交”RL = 右喂左接，LR = 左喂右接。R2 出口接收(静态)=姿态数；IK 不可解 = 270 个候选里无 IK 的个数。\n")
P(HEAD)
P(fmt(base).replace(base["spec_txt"], "原位（不挪）"))
for tag, g, key_ in (("A 最有希望", "A", "promising"), ("B 最小(位移优先)", "B", "min"), ("B 最小纯平移", "B", "min_translation"), ("B 最稳", "B", "robust"), ("C 最小(R1 动)", "C", "min"), ("C 最稳", "C", "robust")):
    o = cands[g].get(key_)
    if o:
        P(fmt(o).replace(o["spec_txt"], f"**{tag}**：" + o["spec_txt"]))
P("\nA 没有可行挪动：第一个不行的步骤。严判据下 A 的 87 个点里：R2 出口接收 62 个（cone20 行程=0 或静态=0）、准备 23 个、入口侧 2 个（即 R1 (+12,+9)/(+12,+12) cm +15°：其余全过，R2 面落到 R1 出口侧）。")
P("**R1 的位置对 R2 出口接收有没有影响**：有，但只通过碰撞项：IK 不可解个数在 A 的 87 个挪动里完全不变（左 228 / 右 219），可行姿态数的增加只来自“撞 R1 环”的候选被放出来（R1 (+12,+9) cm、+15°：撞 R1 左 41→1、右 47→0；同时撞 R2 左 0→10、右 4→20）。"
  "R1 大挪动（+12,+9 cm）后左手静态姿态 14、cone20 行程 5，但同时 R2 在 R1 出口侧，入口侧检查不过。\n")
P("### 与 IK 不可解的关系（数据）\n")
P(f"- A（只挪 R1）：IK 不可解 左 {iku('A')[0]}、右 {iku('A')[1]}，87 个挪动全部相同。\n- B（只挪 R2）：左 {iku('B')[0][0]}–{iku('B')[0][-1]}，右 {iku('B')[1][0]}–{iku('B')[1][-1]}（原位 228 / 219）；热图 E 给出 dx,dy 方向。\n"
  f"- C：左 {iku('C')[0][0]}–{iku('C')[0][-1]}，右 {iku('C')[1][0]}–{iku('C')[1][-1]}，由 R2 的挪动决定（和同样 R2 挪动的 B 行一致）。\n")
P("## (2) 图\n\n![r1_move_eval](r1_move_eval.png)\n\nA/B/C 各画最好候选（A 无可行，画最有希望者并标出未通过的步骤）；灰虚线 = 原位，蓝 = 新位，红箭头 = 挪动，橙 X = R2 出口接收点（面后 5/7/10 cm，灰 x 为原位）；D/E = 只挪 R1 / 只挪 R2（转角 0）时左手 R2 出口接收静态姿态数热图，格内红字为该格因其他步骤第一个不行的步骤。\n")
P("## (3) 代价\n")
P(GEO_HEAD)
P(geo_row("原位", base))
for tag, g, key_ in (("A 最有希望", "A", "promising"), ("B 最小(只转 −20°)", "B", "min"), ("B 最小纯平移", "B", "min_translation"), ("B 最稳", "B", "robust"), ("C 最小(R1 动)", "C", "min"), ("C 最稳", "C", "robust")):
    o = cands[g].get(key_)
    if o:
        P(geo_row(tag + " " + o["spec_txt"].replace("；", " ; "), o))
P("\n弧长下界说明：绳全长 1.1 m（材料起点到终点）；反向穿法材料起点端先出 R1 约 0.10 m（假设值），穿越点离材料起点端的弧长 ≥ 0.10 + R1–R2 环心距（R2）、+ R2–R3 环心距（R3），取直线下界，不含绕弯和夹持余量；原位材料起点到 R3 环心直线 0.321 m。")
_rem = [1.1 - o["geo"]["arc_final_from_start_tip"]["R3"] for o in res if o["job"]["group"] in "ABC"]
P(f"绳长在全部 {len(res)} 个已评估挪动里都够：R3 穿越点弧长下界 {1.1-max(_rem):.2f}–{1.1-min(_rem):.2f} m，余量 {min(_rem):.2f}–{max(_rem):.2f} m（原位下界 {base['geo']['arc_final_from_start_tip']['R3']:.3f} m，余量 {1.1-base['geo']['arc_final_from_start_tip']['R3']:.2f} m）。“R2 中心到 R1 环面的法向距离”：原位 10.0 cm，且 R2 的出口方向与 R1 环面平行（90°，绳头得转大约 90° 才能穿 R1）；"
  "R2→R1 连线与 R1 行进方向夹角原位 54.6°，已大于 25° 锥（斜穿）；R1 的立柱在环缘（离环心 7.5 cm，位于环面内），R1 本身的几何没变；连线与 R1 行进方向夹角越大，越是贴着环面斜穿、越容易擦到环缘/立柱，所以“是否仍需斜穿/绕过支架”看这一列（本评估不模拟擦碰）。\n")
P("### 代价一句话\n")
g0 = base["geo"]
def sent(name, o):
    g = o["geo"]
    return (f"{name}：环心距 R1–R2 {100*g0['center_dist']['R1R2']:.1f}→{100*g['center_dist']['R1R2']:.1f} cm，R2–R3 {100*g0['center_dist']['R2R3']:.1f}→{100*g['center_dist']['R2R3']:.1f} cm；"
            f"R2 到 R1 环面法向 {100*g0['r2_to_r1plane_normal']:.1f}→{100*g['r2_to_r1plane_normal']:.1f} cm、面内偏移 {100*g0['r2_to_r1_inplane']:.1f}→{100*g['r2_to_r1_inplane']:.1f} cm；"
            f"连线与 R1 行进方向夹角 {g0['chord_R2R1_vs_R1_travel_deg']:.0f}→{g['chord_R2R1_vs_R1_travel_deg']:.0f}°，R2 出口方向与连线夹角 {g0['chord_R2R1_vs_R2_exit_deg']:.0f}→{g['chord_R2R1_vs_R2_exit_deg']:.0f}°；"
            f"绳余量 {1.1-g0['arc_final_from_start_tip']['R3']:.2f}→{1.1-g['arc_final_from_start_tip']['R3']:.2f} m。")
for name, o in (("B 最小（R2 只转 −20°）", mB), ("B 最小纯平移", mBt), ("C 最小（R1、R2 各 +3 cm）", mC), ("A 最有希望", cands["A"]["promising"])):
    P("- " + sent(name, o))
P("")
P("### 任务有没有变简单（结论）\n")
P("- **没有变简单。** B 的最小挪动（R2 只转 −20°）环心距、环面间隙、绳长需求都不变，只换来 R2 出口接收可行，且 R2 出口方向与 R2→R1 连线夹角从 36° 增到 56°（绳头出 R2 后要多转一段弯才到 R1），R2→R1 的路程（环心距 17.3 cm、法向 10.0 cm、面内偏移 14.1 cm）和斜穿 R1 的角度（55°）不变。")
P("- B 沿 +y 3 cm：R2→R1 面内偏移 14.1→11.2 cm、连线与 R1 行进方向夹角 55→46°（略缩短、略正），但 R2–R3 环心距 28.1→31.1 cm（略长）、R2 出口方向与连线夹角 36→45°；总体持平。")
P("- C（R1、R2 同向平移）：R1–R2 的相对位置不变，R2→R1 的一段一点没变，只是 R2–R3 变长 3 cm；没有简化。")
P("- A（只挪 R1 到能让 R2 出口接收有解的位置）：R2 落在 R1 环面的出口侧（法向 −8.8 cm），绳头出 R2 后要绕到 R1 背后再穿入，比原位**更难**。")
P("- 仍斜穿 R1：所有候选里 R2→R1 连线与 R1 行进方向的夹角都 ≥ 27°（B 最稳 27°，其余 46–55°），大于 25° 锥，R1 仍需斜穿/贴着环面穿，不会因为这个挪动变正。")
P("- 一句话：挪 R2（转 −20° 或沿 +y 3 cm）能让 R2 出口接收和 R1 喂入都有解，代价是绳头出 R2 后转弯更大（或 R2–R3 略长），任务总体不变简单；挪 R1 不能解决 R2 出口接收的 IK 不可解，且会让 R2 到 R1 一段更难。\n")
P("## 局限 / 不确定\n")
P("- 全是离线可达性 + 胶囊碰撞（不含绳的物理、指尖旋转、两臂同时在环附近的碰撞，静态探针不算对另一臂的碰撞）；原位宽判据也通过而实跑失败，所以“可行”只是必要条件。")
P("- 严判据下 B/C 的可行多是 1–6 个姿态（左手），右手 R2 出口接收 0（B 里右手静态仅在个别 R2 位置 >0），属边缘可行。")
P("- 入口侧阈值 2 cm、环间/底座间隙 2 cm 是我定的；R2 绕自身竖直轴转时，R2 的出口方向随之改变，R2 出口方向与 R2→R1 连线夹角变大（原位 36° → 56°），绳头出 R2 后到 R1 要多转一些弯。")
P("- 弧长是直线下界，没有算绕弯；材料起点端出 R1 的 0.10 m 为假设。")
P("- 图中热图格内小红字约 21 px（<28 px），其余文字 ≥28 px。\n")
P("## 全表\n")
for g in "ABC":
    P(f"### {GROUPS[g]}（{len(rows(g))} 个有效点）\n")
    P(HEAD)
    P(cand_rows(sorted(rows(g), key=key)))
    P("")
    if invalid[g]:
        P(f"几何无效、未评估（{len(invalid[g])} 个）：" + "；".join(S.label(j["spec"]) for j in invalid[g]) + "\n")
open(os.path.join(OUT, "r1_move_eval.md"), "w").write("\n".join(md))
print("md written")
