"""Build the native HTML deck from the frozen weekly evidence."""
from pathlib import Path
from html import escape as esc
import json

OUT = Path(__file__).resolve().parent
REPORT = OUT.parent
ROOT = REPORT.parents[2]
OLD = ROOT / "docs/presentations/.weekly_2026_09_19"
inventory = {g["id"]: g for g in json.loads((REPORT / "demo_inventory.json").read_text())}
progress = {t["task_id"]: t for t in json.loads((REPORT / "report.json").read_text())["tasks"]}
audit = json.loads((REPORT / "token_audit.json").read_text())
media = {}
for row in json.loads((OLD / "embedded_media.json").read_text()):
    media.setdefault(row["group"], []).append({
        "camera": row["camera"],
        "src": "media/" + Path(row["playback_file"]).name,
        "poster": "posters/" + Path(row["poster"]["image"]).name,
        "duration": float(row["playback_probe"]["duration"]),
        "width": row["playback_probe"]["width"],
        "height": row["playback_probe"]["height"],
    })
slides = []


def slide(slug, chapter, title, body, subtitle="", notes="", kind="", tag=""):
    slides.append(dict(id=slug, chapter=chapter, title=title, body=body,
                       subtitle=subtitle, notes=notes, kind=kind, tag=tag))


slide("motivation", "01 · Motivation", "Complex spatial constraints.", '''
<div class="hero-copy"><p class="hero-name">TopoGym<span class="period">.</span></p>
<h1>A benchmark for<br><span>complex spatial constraints.</span></h1>
<p class="hero-question">物体之间、物体自身的约束，<br>如何决定一条可执行的动作路径？</p>
<div class="hero-keywords"><span>Geometry</span><span>Contact</span><span>Action sequence</span></div></div>
<div class="hero-visual" aria-label="Cast Coil 与解绳结的工程 demo 画面">
<figure><img src="posters/coil_base_cam_low.jpg" alt="两个刚性卷绕件的装配"><figcaption>Object ↔ object</figcaption></figure>
<figure><img src="posters/knot_base_cam_low.jpg" alt="绳子与自身形成的结"><figcaption>Object ↔ self</figcaption></figure></div>
<div class="hero-bottom"><span>RESEARCH IN PROGRESS</span><span>Task space → Demos → Evaluation → Policies</span></div>
''', notes="研究动机：以 complex spatial constraint benchmark 为主线，考察几何、接触和动作次序共同约束下的可执行路径。11 个任务是当前候选池，尚未冻结为最终 benchmark。封面来自工程 demo，不表示受测 agent 已解决。材料沿用 2026-09-19 周报及用户本轮研究讨论。", kind="cover")

slide("task-space", "02 · Task space", "从两个维度组织任务", '''
<div class="matrix">
<div class="matrix-corner">约束关系 × 物体性质</div><div class="matrix-axis">Rigid / 刚性</div><div class="matrix-axis">Deformable / 可形变</div>
<div class="matrix-row">Object ↔ object<small>物体与其他物体</small></div>
<article><h3>互锁 · 窄通路 · 接触</h3><p>Coil / Keyhole / Claws<br>Hedgehog / Lock / Buzz Wire</p></article>
<article><h3>穿引 · 收束</h3><p>Rope Threading<br>Fiber Bundling</p></article>
<div class="matrix-row">Object ↔ self<small>物体与自身</small></div>
<article class="quiet"><h3>待扩展的任务空间</h3><p>关节化 / 多部件结构</p><span class="pill">候选方向</span></article>
<article><h3>自接触 · 缠结 · 折叠</h3><p>Knot Untying<br>Blanket Flatten</p></article>
</div>
<p class="bottom-note">Horseshoe Ring 跨越刚性构件与可动链条；这些维度允许交叉。</p>
''', subtitle="用约束机制寻找任务，而后验证可解性与难度。", tag="UNDER DEVELOPMENT",
notes="这是正在整理的任务提议框架，不是互斥分类。Horseshoe Ring 包含刚性马蹄/环和可动链条，不能笼统视为全部刚性。严格刚体自身几何不变，因此 object–self / rigid 格中仅列待探索的关节化或多部件结构。难度还可能受净空、需要回退的次数、可见性、变形和操作长度影响；这些是候选轴，尚未证明单调难度。")


def task_table(rows):
    result = '<div class="table-legend"><span><i class="dot done"></i>指定范围已达到</span><span><i class="dot partial"></i>部分 / 验证中</span><span><i class="dot pending"></i>未验收</span></div>'
    result += '<table class="task-table"><thead><tr><th>Task / 核心约束</th><th>场景</th><th>物理 + demo</th><th>随机接口</th><th>逐例验收</th><th>当前阶段</th></tr></thead><tbody>'
    labels = {2: "指定范围已达到", 1: "部分完成或验证中", 0: "未验收"}
    for task_id, name, mechanism, status, demo_id in rows:
        result += f'<tr><td><a href="#{demo_id}">{name} <span class="jump-arrow">↗</span></a><small>{mechanism}</small></td>'
        for stage in progress[task_id]["stages"]:
            result += f'<td><i class="dot { {2:"done",1:"partial",0:"pending"}[stage] }" role="img" aria-label="{labels[stage]}"></i></td>'
        result += f'<td class="task-status">{status}</td></tr>'
    return result+'</tbody></table>'


rigid = [
    ("cast_coil", "Cast Coil", "卷绕件装配", "基础执行；随机动力学待验收", "demo-coil"),
    ("cast_keyhole", "Cast Keyhole", "槽齿绕行与回退", "参数实例验证；终态保持抓持", "demo-keyhole"),
    ("horseshoe_ring", "Horseshoe Ring", "折合、交接与取环", "基础复验；新三族待补复验", "demo-horseshoe"),
    ("hedgehog_in_cage", "Hedgehog in Cage", "姿态与孔隙匹配", "原型验证；随机后代待执行", "demo-hedgehog"),
    ("lock_picking", "Lock Picking", "接触与必要回退", "基础成功；新三族为 IK 预演", "demo-lock"),
    ("interlocked_claws", "Interlocked Claws", "非凸互锁与分离", "B0/C0 物理通过；生成待接入", "demo-claws"),
    ("buzz_wire_3d", "Buzz Wire 3D", "沿空间轨迹约束通行", "F3 主运行成功；复验未完成", "demo-buzz"),
]
soft = [
    ("fiber_bundling", "Fiber Bundling", "多芯线共同穿环", "基础穿环；严格线形收敛未过", "demo-fiber"),
    ("knot_untying", "Knot Untying", "自缠结与接触", "v9 解结；网格 / 交接待验收", "demo-knot"),
    ("rope_threading", "Rope Threading", "柔性绳穿三环", "仅前段；完整三环尚未成功", "demo-rope"),
    ("blanket_flatten", "Blanket Flatten", "解扭与展开", "复杂初态尚未展平成功", "demo-blanket"),
]
slide("tasks-rigid", "03 · Tasks", "候选任务 · 刚性构件为主", task_table(rigid),
subtitle="先看核心约束与进度，再看完整画面。", notes="四阶段数值直接读取 reports/weekly/2026-09-19/report.json，与原 progress.svg 保持一致。绿色只表示周报明确限定的实例/协议范围内达到，不代表全族或正式 benchmark 已合格。Horseshoe Ring 包含可动链条。Claws 列表进度含 B0/C0 新物理证据，后面的主展示沿用前版选定的 A0，其资格限制单独标注。工程快照 18:27 CDT；具体更新以周报备注为准。")
slide("tasks-soft", "03 · Tasks", "候选任务 · 可形变物体", task_table(soft)+'''
<div class="wide-callout"><span class="callout-mark">↗</span><div><strong>从“能展示”走向“可评测”</strong><p>完整执行、物理可靠性、随机实例验收，需要分别推进。</p></div></div>
''', subtitle="形变与自接触打开新的任务空间，也带来验证难点。", notes="四阶段状态与原周报一致。Fiber 三类是按线数划分的稀疏/标准/密集，不要求三类具有本质不同的 IK 策略。Knot v9 有成功解结轨迹，但 P3 网格收敛与通用双手交接未过。Rope 只展示抓取前段。Blanket v10 复杂麻花初态未达到展平成功标准。")

# Keep overview pairs; give every task an adjacent wrist-view page.
demos = [
    ("coil", "Cast Coil", "卷绕件装配", "coil_base", "cam_high", "cam_low", "完整基础 demo", "预抓取 · 接触辅助 · 装配后释放", ""),
    ("keyhole", "Cast Keyhole", "钥匙孔拆解", "keyhole_base", "cam_high", "cam_low", "完整拆解", "预抓取 · 接触辅助 · 拆解后仍夹持", ""),
    ("horseshoe", "Horseshoe Ring", "马蹄环", "horseshoe_base", "cam_high", "cam_low", "完整基础 demo", "辅助抓持 · 取环后落桌 · 基础双步长通过", ""),
    ("hedgehog", "Hedgehog in Cage", "刺球出笼", "hedgehog_side", "agentview", "front_oblique", "完整原型 demo", "固定六刺侧孔 v2 · 预抓取 / 接触辅助 · 取出后释放", ""),
    ("lock", "Lock Picking", "开锁", "lock_base", "agentview", "front_oblique", "基础成功轨迹", "150 mm / 两回退 · 实测状态重渲染", "被动夹爪连杆按开合量重建；本片不是一次新的动力学执行。新三族仍是 IK 预演，不能继承基础版结果。"),
    ("claws", "Interlocked Claws", "互锁爪 · A0", "claws_a", "cam_high", "cam_low", "资格受限", "A0 全过程 · 理想辅助抓持 · 原非凸接触限制仍在", "沿用此前主展示选定的 A0 基础变体。B0/C0 的 MuJoCo 动力学与双步长验证不能继承到 A0。"),
    ("buzz", "Buzz Wire 3D", "立体电流棒", "buzz_f3", "agentview", "front_oblique", "复验中", "F3 四关 v3 · 摩擦抓持 · 状态重渲染 · 小步长复验未完", "主物理运行 106.92 s，三路视频 106.96 s。仅说明这一原型主运行成功，不代表全族资格已完成。"),
    ("fiber", "Fiber Bundling", "光纤收束", "fiber_base", "agentview", "front_oblique", "验证中", "8 芯 / R13.5 mm · 辅助抓持 · 线形收敛未通过", "两档步长均完成穿环但末态仍夹持。只能抓粗护套，不能碰细线；严格全程线形收敛未通过。"),
    ("knot", "Knot Untying", "解绳结", "knot_base", "cam_high", "cam_low", "验证中", "三叶结 v9 · 接触辅助 · 网格收敛 / 通用交接待验收", "75 s 连续解结、释放和静置。本轨迹通过不等于新结型或通用算法完成验收。"),
    ("rope", "Rope Threading", "绳穿三环", "rope_prefix", "cam_high", "cam_low", "局部片段", "抓取 → 抬升 → 释放 · 尚无三环成功全过程", "视频 29.05 s，只含可播放前段，不含三环完成；不能作为完整任务成功见证。"),
    ("blanket", "Blanket Flatten", "被子展平", "blanket_latest", "agentview", "front_oblique", "未成功尝试", "复杂麻花初态 v10 · 末态覆盖 45.4% · 尚未展平", "179.5 s，2 fps 实测状态重渲染，八次保护释放。v8 的 75.7% 仍不算成功；旧简单初态的成功不能替代当前复杂初态。"),
]
def demo_body(group, cameras):
    single = len(cameras) == 1
    play_label = "播放" if single else "同时播放"
    seek_label = "播放进度" if single else "同步进度"
    return (
        f'<div class="demo-grid{" single" if single else ""}" data-group="{group}" data-cameras="{",".join(cameras)}"></div>'
        f'<div class="demo-controls"><button class="pair-play primary">{play_label}</button><button class="pair-reset">回到开头</button>'
        f'<label>{seek_label} <input class="pair-seek" aria-label="{seek_label}" type="range" min="0" max="1000" value="0" step="1"></label>'
        '<span class="pair-time">0:00 / 0:00</span><span class="media-error" role="status"></span></div>'
    )


for slug, english, chinese, gid, left, right, status, scope, detail in demos:
    warn = slug in {"claws", "buzz", "fiber", "knot", "rope", "blanket"}
    notes = f'{english} — {inventory[gid]["title"]}。{inventory[gid]["scope"]} {detail}\n所有可选视角来自同一次执行。演示副本保留完整时间与帧数，播放器倍速不改变原片。\n来源：demo_inventory.json / {gid}；{inventory[gid]["evidence"]}。'
    tag = f'<span class="pill {"amber" if warn else "green"}">{status}</span>'
    slide("demo-"+slug, "03 · Demos", english, demo_body(gid, [left, right]),
        subtitle=f'{chinese} <span class="separator">/</span> {scope}', kind="demo",
        tag=tag, notes=notes)
    available = {m["camera"] for m in media[gid]}
    wrists = ["wrist"] if "wrist" in available else ["cam_left_wrist", "cam_right_wrist"]
    assert set(wrists) <= available, f"Missing wrist media for {gid}"
    wrist_label = "Wrist / 腕部视角" if len(wrists) == 1 else "Left wrist + Right wrist / 左右腕部视角"
    slide("demo-"+slug+"-wrist", "03 · Demos", english+" · Wrist",
        demo_body(gid, wrists),
        subtitle=f'{wrist_label} <span class="separator">/</span> {scope}', kind="demo wrist",
        tag=tag, notes=notes+"\n本页单独展示腕部相机；与前一页主视角来自同一次执行。")


def pilot_chart():
    labels = ["Coil 001", "Coil 002", "Horseshoe", "Keyhole", "Hedgehog", "Lock Picking", "Claws · 进行中"]
    parts = ['<svg class="pilot-chart" viewBox="0 0 1200 420" role="img" aria-labelledby="pilot-title pilot-desc">',
             '<title id="pilot-title">探索性 pilot 的累计 token 用量</title>',
             '<desc id="pilot-desc">七次运行的原生 input 加 output 用量；均超出原 2M 目标。Claws 为进行中的快照下界。没有严格预算下的成功率。</desc>']
    for t in [0, 20, 40, 60, 70]:
        x = 185+t/70*810
        parts.append(f'<path d="M{x} 37V371" stroke="#d8e0e4"/><text x="{x}" y="405" text-anchor="middle" class="axis-label">{t}M</text>')
    for i, (label, ep) in enumerate(zip(labels, audit["episodes"])):
        value = ep["episode_usage"]["total_tokens"]
        prefix = "≥ " if not ep["closed_episode"] else ""
        y = 62+i*47
        parts.append(f'<text x="0" y="{y+6}" class="bar-label">{label}</text><rect x="185" y="{y-13}" width="{value/1e6/70*810}" height="24" rx="4" fill="{"#b27b31" if prefix else "#167b72"}"/><text x="1196" y="{y+6}" text-anchor="end" class="bar-value">{prefix}{value/1e6:.2f}M</text>')
    x = 185+2/70*810
    parts.append(f'<path d="M{x} 29V379" stroke="#b65e50" stroke-width="2" stroke-dasharray="5 4"/><text x="{x}" y="19" text-anchor="middle" class="budget-label">原目标 2M</text></svg>')
    return ''.join(parts)


slide("pilot", "04 · Evaluation", "先看已有 pilot，再定义正式评测", '''
<div class="stat-strip"><div><strong>6</strong><span>个任务</span></div><div><strong>7</strong><span>次运行</span></div><div><strong>0</strong><span>次已观察到成功</span></div><div class="stat-caption">6 次 failed · 1 次仍为 ready<br>冻结于 09.19 / 18:24:55 CDT</div></div>
'''+pilot_chart()+'''
<p class="bottom-note alert">7/7 均已超过原 2M 目标；这批结果尚不能回答“3M 下能否完成”。</p>
''', subtitle="原生累计 input + output；沿用已有用量图与冻结数据。", tag="EXPLORATORY PILOT",
notes="这是原 slides 第 15 页 token 用量图的 HTML/SVG 重排版。数值直接来自 token_audit.json。Coil 001 4,420,724；Coil 002 69,452,496；Horseshoe 2,819,223；Keyhole 12,487,795；Hedgehog 2,109,472；Lock Picking 3,821,375；Claws ≥23,376,797。结束轮次包含最终答复，进行中的 Claws 是下界。cached input、reasoning output 分别包含在 input、output，不重复加。现有 pilot 未实行实时硬预算，全部受测 adapter 的完整物理资格仍未完成，且部分 session 含旧上下文。不能称作严格 2M/3M 的成功率或 GPT-6 的能力上限；ready 不等于 succeeded。联网约定也不完全统一：非 Coil 禁联网，Coil 允许通用资料但结果称未联网研究。")

slide("difficulty", "04 · Evaluation", "3M tokens，能走到哪一档难度？", '''
<div class="budget-hero"><strong>3M</strong><div><h3>GPT-6 Astra · Offline</h3><p>外部硬计量 · 干净会话 · 同一交互协议</p></div><span class="pill amber">待实现 / 待运行</span></div>
<div class="difficulty-ladder"><article><span>L1</span><h3>基准实例</h3><p>已验证的完整路径</p></article><span class="flow-arrow">→</span><article><span>L2</span><h3>参数变化</h3><p>净空 / 姿态 / 形变</p></article><span class="flow-arrow">→</span><article><span>L3</span><h3>结构与序列</h3><p>回退 / 交接 / 多阶段</p></article></div>
<div class="budget-sweep"><span>Budget sweep <small>提案</small></span><b>0.5M</b><b>1M</b><b>2M</b><b class="selected">3M</b><span>× 固定难度实例</span></div>
<p class="bottom-note">难度档位由统一条件下的表现校准；参数更大或更多，并不自动等于更难。</p>
''', tag="EVALUATION PROPOSAL",
notes="用户本轮提出检验 Astra 在 3M 下能完成什么难度。0.5/1/2/3M sweep 是建议设置，不是既有实验。L1–L3 是校准框架，不能在实测前宣称严格单调难度。当前 bridge v1 文档仍限制累计预算最多 2M，且当前 session pilot 无硬计量；3M 需要后续更新配置/预算上限、外部原生 usage 计量与隔离后另开新 run，本次仅制作 presentation，不修改执行器。离线指 solver 无互联网访问；模型服务请求与本机 bridge 通信单独定义。每次调用前预留 input/output 额度，累计重复上下文也计入；预算耗尽时保留终态。")

slide("inputs", "04 · Evaluation", "两种输入条件，分别报告", '''
<div class="input-tracks"><article><span class="track-letter">A</span><span class="pill green">Observation only</span><h3>仅公开观测</h3><ul><li>RGB / segment clip</li><li>机器人本体状态与相机标定</li><li>统一 action interface</li></ul><p class="track-limit">不可访问 simulator 内部状态与资产</p></article>
<article><span class="track-letter">B</span><span class="pill">Privileged access</span><h3>开放指定 simulator 信息</h3><ul><li>A 的全部输入</li><li>物体几何 / 位姿 / 接触真值</li><li>按白名单固定可访问字段</li></ul><p class="track-limit">额外 rollout / state restore 权限另行定义</p></article></div>
<div class="shared-rule">相同实例 · 相同目标与动作接口 · 相同预算 · 分轨比较成功率</div>
''', subtitle="访问 simulator 专有信息，是需要显式控制的实验变量。", tag="UNDER DEVELOPMENT",
notes="Track A 不允许访问 simulator 内部，不代表没有环境交互：仍通过统一 action API 执行动作。Track B 提议额外开放物体 CAD/几何、真实位姿、接触等指定字段，但不是自动无限制访问；是否允许查询 simulator、额外 rollout、reset/restore 仍需另列条件并计量。两轨都不自动开放私有参考解和已有 demo。用宿主隔离和工具权限实现边界，不能仅靠提示词。当前 pilot 主要接近 A，但共享文件系统和旧上下文不满足正式隔离要求。")

slide("pipeline", "04 · Evaluation", "以 segment 为单位，闭环交互", '''
<div class="pipeline-flow"><article><span>01</span><h3>Observe</h3><p>clip + states</p></article><b>→</b><article><span>02</span><h3>Propose</h3><p>action segment</p></article><b>→</b><article><span>03</span><h3>Execute</h3><p>同一环境连续执行</p></article><b>→</b><article><span>04</span><h3>Review</h3><p>反馈 → 下一段</p></article></div>
<div class="pipeline-lower"><div class="file-tree"><span class="file-title">episode/</span><pre>task.json
initial/    <em>← 初始观测</em>
segments/
  0001/     <em>← action + trajectory + clip</em>
  0002/
index.json  <em>← 路径、时间戳、可读字段</em></pre></div>
<div class="interface-notes"><h3>Harness 管理输入与输出</h3><div><b>对齐</b><p>trajectory / state / video 共享时间戳</p></div><div><b>可读</b><p>prompt 指明目录、视角与读取方式</p></div><div><b>可审计</b><p>请求 ID、剩余预算、终态与错误类型</p></div></div></div>
''', subtitle="每次 action segment 后，返回对应的状态轨迹与视频。", tag="INTERFACE PROPOSAL",
notes="建议目录结构：每个 segments/0001/ 包含 action.py 或 actions.json、trajectory.jsonl、states.jsonl、clips/<camera>.mp4、manifest.json。trajectory 保存实际执行的机器人轨迹，不用命令目标假装已执行。manifest 记录 request_id、起止时刻、步数、相机路径和可公开状态字段；index.json 给出可读目录，不暴露私有 evaluator 数据。模型工具若支持 clip 则按路径读取；否则由 harness 根据时间戳抽帧后作为图像输入，不能假定模型仅收到视频路径就能看见视频。原协议 v1 已有逐 segment PNG frames 与状态，MP4、索引整理和通用 clip 输入是本轮提案。动作不可回滚；每段反馈来自同一连续 episode。")

slide("metrics", "04 · Evaluation", "固定场景，比较 success rate", '''
<div class="freeze-flow"><span>随机生成候选</span><b>→</b><span>逐实例资格验收</span><b>→</b><strong>冻结 test seeds</strong><b>→</b><span>所有 policy 共用</span></div>
<div class="metric-layout"><article class="metric-main"><span class="micro-label">PRIMARY METRIC</span><h3>Success rate</h3><p>按 task × difficulty × input track 分层</p><div class="formula">成功 episode / 预先约定的有效 episode</div><span class="pill">重复运行 + 95% CI</span></article>
<article class="metric-bars"><h3>图上的两种参照</h3><div><span class="random-symbol"></span><p><strong>Random policy bar</strong><br>相同动作约束与步数预算的随机策略基线</p></div><div><span class="ci-symbol">├──┤</span><p><strong>Error bar</strong><br>固定实例与策略重复的统计不确定性</p></div></article></div>
<p class="bottom-note">场景生成时随机，生成并验收后冻结；另报超预算、违规终止与基础设施错误。</p>
''', subtitle="固定的是测试场景；保留并报告策略执行的随机性。", tag="METRICS PROPOSAL",
notes="回应 random bar 的笔记，区分随机策略基线和成功率误差棒。Random policy 的动作空间、控制步长、segment 上限与终止规则必须固定；随机动作基线尚未运行，本页不填造成功率。场景 seed 及生成器/资产/初态版本冻结后，所有 policy 使用同一组测试实例；policy RNG seed 与重复次数另行记录。建议使用 95% CI，具体 Wilson 或分层 bootstrap 在样本数确定后预注册。超预算和策略违规属于任务失败类型；基础设施错误不默认为模型失败，要按预先约定的无效 trial 重试规则处理，并单列数量，禁止事后挑选。RL 的训练成本另报，不能和 code agent 的 token 预算直接等同。")

slide("policies", "05 · Policies", "三类 policy，同一个 harness", '''
<div class="policy-grid"><article><span class="card-no">01</span><span class="pill green">优先 baseline</span><h3>Code agents</h3><p>观察 → 写代码 → 执行 → 修订</p><div class="policy-footer">先定位规划与交互瓶颈</div></article>
<article><span class="card-no">02</span><span class="pill amber">探索方向</span><h3>VLA <small>/ + Code</small></h3><p>动作片段提议 → 轨迹与视频反馈</p><div class="policy-footer">跨任务可用性仍待确认</div></article>
<article><span class="card-no">03</span><span class="pill">规划中</span><h3>Pure RL</h3><p>交互学习 → 闭环执行</p><div class="policy-footer">训练成本与泛化单独报告</div></article></div>
<div class="harness-band"><strong>Shared harness</strong><span>Task adapter</span><span>Observation / action</span><span>Evaluator</span><span>Logging / budget</span></div>
''', subtitle="固定评测接口，更换求解策略。",
notes="三类 policy 是本轮研究规划，不是已完成的比较。Code agents 最接近现有 bridge 与 pilot。VLA 单独 baseline 与 VLA + code 的组合应分别报告。Pure RL 需要定义训练 split、训练交互成本、奖励和 test 泛化。所有 policy 对齐测试实例、动作空间、初态/抓持规则、成功条件与评测时交互步数；训练 compute、模型调用 token 和 wall time 保持各自可解释的资源报告。A/B 输入轨分别评测，不把有专有信息的 RL 结果直接混入 A 轨。")

slide("vla-boost", "05 · Policies", "VLA 提议动作，GPT 继续修订", '''
<div class="vla-flow"><article><span class="micro-label">PROPOSAL</span><h3>VLA</h3><p>roll out 一个 segment</p></article><span class="flow-arrow">→</span><article class="clip-packet"><h3>同一 segment</h3><div><span>trajectory</span><b>+</b><span>rendered clip</span></div></article><span class="flow-arrow">→</span><article><span class="micro-label">REVISION</span><h3>GPT / Code agent</h3><p>解释偏差 · 修订后续动作</p></article></div>
<div class="revision-loop"><span>观察新反馈</span><span>←</span><strong>继续执行 revised segment</strong><span>←</span><span>基于当前真实状态</span></div>
<div class="wide-callout"><span class="callout-mark">?</span><div><strong>VLA 能否降低从零规划的成本？</strong><p>先验证单任务接口；跨机器人适配与动作可靠性仍是主要不确定性。</p></div></div>
''', subtitle="VLA 作为动作提议器，帮助启动与推进求解。", tag="SPECULATIVE / 待验证",
notes="用户提出 VLA roll out 一个 segment，将轨迹以及对应视频/仿真 clip 一起交给 GPT，让 GPT 在其基础上继续 interact/revise。这里默认 segment 已在当前环境执行，GPT 修订的是后续动作，不回滚已经执行的历史。若要让 VLA 在复制 simulator 中生成可编辑候选轨迹，需要独立的 privileged planning 条件和 rollout 预算，不能混到 A 轨。VLA + Code 的实现可行性尚未确认，需先测机器人动作空间、视频输入与轨迹对应关系。仅作为有待验证的 boosting 假设，不承诺提高成功率。")

slide("next", "06 · Next decisions", "下一步：收敛任务与评测边界", '''
<div class="decision-grid"><article><span>01 / TASKS</span><h3>哪些 task 留下？</h3><p>机制有代表性<br>同协议下有完整可解见证<br>物理与失败判据可靠</p></article><article><span>02 / DIFFICULTY</span><h3>哪些实例进入 3M 测试？</h3><p>从已验收基准开始<br>固定 seeds 与参数阶梯<br>实测校准难度</p></article><article><span>03 / HARNESS</span><h3>先把什么接通？</h3><p>segment 视频 / 状态索引<br>A / B 信息权限<br>硬预算与统一统计</p></article></div>
<div class="closing-line">Complex constraints.<span> Clear tasks. Measurable progress.</span></div>
''', subtitle="先冻结小规模、可解释的 benchmark，再扩任务与 policy。", tag="OPEN FOR DISCUSSION",
notes="任务保留标准是本轮讨论建议，不是已作出的删除决定。优先考虑约束机制有代表性、能按评测协议完整执行且成功/失败判据可靠的实例；物理数值故障不能当作困难任务。Rope 的完整三环、Blanket 复杂初态成功、Fiber/Knot 严格数值资格等仍需补齐。新加入目录的 Slotted Post Ring 只有静态初态演示且未在 11 任务周报基线中，本次不擅自加进主候选表。建议先做小批固定 seeds、干净 session、严格 offline、3M 硬预算的 Code agent 校准，再决定 task pruning 与 VLA/RL 扩展。")

slide("progress-source", "07 · Appendix", "原始四阶段进度图", '<img class="source-chart" src="progress.svg" alt="周报原始 11 项任务四阶段进度图">',
subtitle="原图保留；任务清单页已按相同数据重排。", notes="来源：reports/weekly/2026-09-19/progress.svg；配套数据 report.json。进度均为明确限定实例和协议范围内的状态，不折算为百分比。", tag="SOURCE FIGURE")

sections = []
for i, s in enumerate(slides):
    title = '' if s['kind'] == 'cover' else f'<div class="slide-heading"><div><span class="eyebrow">{s["chapter"]}</span><h1>{s["title"]}</h1></div><div class="heading-tag">{s["tag"]}</div></div><p class="subtitle">{s["subtitle"]}</p>'
    sections.append(f'<section class="slide {s["kind"]}" id="{s["id"]}" aria-label="{esc(s["title"])}" data-chapter="{s["chapter"]}" hidden><div class="slide-content">{title}{s["body"]}</div><div class="slide-folio"><span>TOPOGYM <b>/</b> RESEARCH IN PROGRESS</span><span>{i+1:02} / {len(slides):02}</span></div></section>')

data = {"slides": [{k: s[k] for k in ('id', 'chapter', 'title', 'notes', 'kind')} for s in slides], "media": media}
document = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#f4f5f2"><title>TopoGym — Complex Spatial Constraint Benchmark</title><link rel="icon" href="data:,"><link rel="stylesheet" href="deck.css"></head>
<body><header class="app-header"><a class="brand" href="#motivation">TopoGym<span> / Research discussion</span></a><nav aria-label="章节"></nav><button id="overview-button" title="目录 (O)">目录 <kbd>O</kbd></button></header>
<main id="stage" aria-label="TopoGym 演示文稿">__SECTIONS__</main>
<footer class="app-footer"><div class="footer-left"><button id="previous" aria-label="上一页">←</button><span id="page-number" aria-live="polite"></span><button id="next" aria-label="下一页">→</button><span id="chapter-label"></span></div><div class="footer-right"><span class="keyboard-hint">← → 翻页 · Space 播放</span><button id="notes-button" title="讲者备注 (N)">备注 <kbd>N</kbd></button><button id="fullscreen-button" title="演示全屏 (F)">全屏 <kbd>F</kbd></button></div></footer>
<div class="progress-track"><div id="progress-fill"></div></div>
<dialog id="overview"><div class="dialog-heading"><div><span class="eyebrow">PRESENTATION MAP</span><h2>演示目录</h2></div><button class="dialog-close" aria-label="关闭目录">×</button></div><div id="overview-list"></div></dialog>
<dialog id="notes"><div class="dialog-heading"><div><span class="eyebrow">SPEAKER NOTES / EVIDENCE</span><h2 id="notes-title"></h2></div><button class="dialog-close" aria-label="关闭备注">×</button></div><div id="notes-body"></div><p class="notes-date">工程资料基于 2026-09-19 周报；研究提案单独标注。<br>快捷键：N 备注 · O 目录 · F 全屏 · Home / End 首末页。</p></dialog>
<div id="app-status" role="status" aria-live="polite"></div>
<noscript>请在浏览器中启用 JavaScript 以翻页与播放视频。</noscript>
<script id="deck-data" type="application/json">__DATA__</script><script src="deck.js"></script></body></html>'''
document = document.replace('__SECTIONS__', '\n'.join(sections)).replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/'))
(OUT / 'index.html').write_text(document)
(OUT / 'progress.svg').write_bytes((REPORT / 'progress.svg').read_bytes())
(OUT / 'speaker-notes.md').write_text('# TopoGym · 讲者备注与来源\n\n'+'\n\n'.join(f'## {i+1:02} · {s["title"]}\n\n{s["notes"]}' for i, s in enumerate(slides))+'\n')
(OUT / 'manifest.json').write_text(json.dumps({
    'title': 'TopoGym — Complex Spatial Constraint Benchmark',
    'slides': len(slides), 'demo_slides': len(demos)*2,
    'overview_demo_slides': len(demos), 'wrist_demo_slides': len(demos),
    'single_wrist_slides': sum('wrist' in {m['camera'] for m in media[d[3]]} for d in demos),
    'dual_wrist_slides': sum('cam_left_wrist' in {m['camera'] for m in media[d[3]]} for d in demos),
    'simultaneous_video_panes': 2,
    'available_videos': sum(map(len, media.values())), 'source_date': '2026-09-19',
    'media': media,
    'sections': [{k: s[k] for k in ('id', 'chapter', 'title')} for s in slides],
    'pilot_values_tokens': {ep['run_id']: ep['episode_usage']['total_tokens'] for ep in audit['episodes']},
    'proposed_budget_tokens': 3000000, 'strict_3M_results_available': False,
}, ensure_ascii=False, indent=2)+'\n')
print(f'Built {len(slides)} slides / {len(demos)*2} demo pages ({len(demos)} wrist pages) / {sum(map(len, media.values()))} videos.')
