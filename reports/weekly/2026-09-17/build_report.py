"""Build the local weekly review from an explicit evidence snapshot.

Run from any directory. This script only writes this report directory and reads
existing project artifacts; it does not run simulations or change demo archives.
"""
from pathlib import Path
import html
import json
import os
from inspection_data import GATES, INSPECTIONS, STATUS_LABELS

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
E = html.escape


def task(key, title, status, summary, axes, representatives, figure, caption, links, notes):
    return dict(id=key, title=title, status=status, summary=summary, axes=axes,
                representatives=representatives, figure=figure, caption=caption,
                links=links, notes=notes)


TASKS = [
    task('cast_keyhole', 'Cast Keyhole · 槽形解锁', '9 / 9 外形代表已有物理 demo',
         '三种动作机制、每类三款明显不同的外轮廓已经完成；随机生成器另有三个通过验证的连续样本。',
         [
             ['F1 长行程错齿', '加长穿齿行程，依次通过错齿', '种子行程 ×1.20；探索 ×1.10–1.35'],
             ['F2 偏心开口', '侧偏、上移后绕过转向窗口', '种子右偏 6 mm、上移 3 mm；探索右偏 4.5–9 mm，上移为其一半'],
             ['F3 前送—转向—回退', '深入下腔 → 转动 → 回退 → 横移分离', '种子转动 25°、回退 25.5 mm；探索 20–30°、回退约 19.5–31.5 mm'],
         ],
         [[f'{f}_{s}', title, '完整物理 demo'] for f, names in [
             ('F1', ['圆冠长梯', '方冠宽肩', '渐缩楔架']),
             ('F2', ['豆形偏头', '斜肩偏头', '梨形偏头']),
             ('F3', ['圆腹回钩', '方腹折返', '双腹葫芦'])]
          for s, title in zip('ABC', names)],
         'runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_comparison/nine_silhouettes.png',
         '九款真实生成外形的同尺度对照；对应九条成片见下方。',
         [['生成空间与命令', 'runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/variant_space.json'],
          ['随机样本验证', 'runs/demo_metadata/cast_keyhole/2026-09-17_families_v1_generator/generator_manifest.json']],
         ['九款代表和三个随机样本均通过 1 ms / 0.5 ms 物理执行与独立复核；不代表整个连续采样域都通过。',
          '外形宽高倍率 0.96–1.04、模板横移 −0.5–0.5 mm；材质库独立于 family。每次变动需重新验证机构、碰撞与物理执行。',
          '视频从预抓取开始，双指接触后辅助抓持，完成分离后双臂保持；未包含拾取、落桌释放或纯摩擦抓取验证。']),
    task('cast_coil', 'Cast Coil · 卷绕件拆解', '3 个家族种子有 demo；9 个新外形待录制',
         '已有基线、三个运动反推种子，以及三个基线单参数外观 demo。最新九款可见结构已通过几何与 IK，不能借用旧种子视频作为新结构的物理证据。',
         [
             ['A 偏心转动', '滑开 → 绕偏移轴转 90° → 移出', '偏心 e=3/6/9 mm；滑开 27.75/33.75/39.75 mm；左侧斜切 9/12/15 mm'],
             ['B 分段错位', '45° → 高度错位 → 再 45° → 移出', '错位 h=3/6/9 mm；四角为逐渐增大的直角台阶'],
             ['C 旋转推进', '转 90°时同步轴向推进 → 移出', '推进 a=3/6/9 mm；四角斜切 9/12/15 mm，近似八边形'],
         ],
         [[f'{f}{i}', label, '几何 + IK 已检查；新外形无物理录像']
          for f, names in [('A', ['轻偏心 3 mm', '中偏心 6 mm', '大偏心 9 mm']),
                           ('B', ['低台阶 3 mm', '中台阶 6 mm', '高台阶 9 mm']),
                           ('C', ['短推进 3 mm', '中推进 6 mm', '长推进 9 mm'])]
          for i, label in enumerate(names, 1)],
         'runs/environment-solvability/cast_coil/family_space_20260917/visible_overview.png',
         '九个新可见结构：图示是几何结果，尚无对应完整物理视频。',
         [['可交互九宫格', 'runs/environment-solvability/cast_coil/family_space_20260917/index.html'],
          ['最新家族空间', 'docs/develop/tasks/cast_coil_family_space_zh.md'],
          ['基线单参数外观对照', 'runs/demo_metadata/cast_coil/2026-09-17_appearance_single_v1/index.html']],
         ['每类以 6 mm 为新基型；候选轴为机制尺寸 θ、厚度倍率 d=0.90–1.10、轮廓微调 δ∈{−0.75,0,+0.75} mm；轮廓长度 L=6+θ+δ。参数需联动，不是任意组合都可解。',
          '已有外观单轴 demo：正面缩小 5%、叠层加厚 10%、外角切角 5.25 mm；它们属于原始基线，不等于最新 A1–C3 九款。',
          '三个旧种子及外观 demo 均为接触后辅助抓持的物理执行，完整拆解、分别落桌、解除辅助并自由静置。新九款仍缺动力学和录像。']),
    task('hedgehog_in_cage', 'Hedgehog in Cage · 刺球出笼', 'A1 / B1 / C1 有 demo；6 个外形待实现',
         '采用最新 v2：三个动作 family 各配原型、鼓腹、八棱收腰三种外形。三条父路径已有完整物理证据，默认浅木色刺球、深木色笼子。',
         [
             ['A 单斜窗绕出', '侧移配合倾斜，穿过偏置斜窗', '已验证侧移 10 mm、倾角 −4°；后续探索 8–12 mm、−5°至−3°'],
             ['B 双门槛换层', '出主笼 → 换层对齐 → 通过外置挡板', '第二挡板约 X=220 mm；后续探索 210–230 mm，保持双阶段通过'],
             ['C 螺旋导向', '位置与姿态同步转向，沿连续扭带退出', '已验证新增转向 36°、径向距离 200 mm；探索 32–40°、190–210 mm'],
         ],
         [[f'{f}{i}', f'{prefix} · {shape}', '完整物理 demo' if i == 1 else '设计规格；未实现／未验收']
          for f, prefix in [('A', '单斜窗'), ('B', '外置双门槛'), ('C', '螺旋导向')]
          for i, shape in enumerate(['原型轮廓', '鼓腹厚框', '八棱收腰'], 1)],
         'runs/environment-solvability/hedgehog_in_cage/family_design_v2/family_grid.png',
         'v2 设计示意：第一列对应已有父实例，后两列是候选外形，不能视作已生成模型。',
         [['v2 九宫格规划', 'runs/environment-solvability/hedgehog_in_cage/family_design_v2/index.html'],
          ['三个家族同步播放', 'runs/demo_metadata/hedgehog_in_cage/2026-09-17_family_representatives_v1/index.html'],
          ['参数与验收规则', 'docs/develop/tasks/hedgehog_in_cage_family_space_zh.md']],
         ['鼓腹：中段半径增加 12–18 mm，端部增加 0–4 mm；八棱收腰：肩部增加 12–18 mm、腰部增加 0–3 mm，腰肩比 0.80–0.90。高度暂固定 240 mm。',
          '先保留父机关与完整机器人运动空间，在其外增材形成外观；首批复用父运动，六个候选仍须逐一做几何和完整物理验收。',
          '三个父 demo 均从 S2 预抓取开始，接触后辅助抓持，取出、落桌、释放、撤离和静置。A→B→C 只可作动作复杂度的暂定顺序，尚无实测难度排名。']),
    task('horseshoe_ring', 'Horseshoe Ring · 马蹄环取环', '4 份全程运动学预演；物理执行未完成',
         '原版与三个 IK 种子都有全程动态视频。最新规划是 F1/F2/F3 × R/U/E 九个配对；九款有几何证据，新增六款外形尚缺机器人验证。',
         [
             ['F1 高位回环', '左手抬高、绕回、再抓目标环', '种子 compact_roll_planned；已有完整运动学预演'],
             ['F2 侧向大弧', '侧面扫入，沿外侧通道换抓', '种子 wide_roll_planned；仍需与 F3 拉开可见路线差异'],
             ['F3 分段回抓', '先退让、调整腕姿，再接近抓取', '种子 longer_regrasp_planned；仍需强化分段回抓特征'],
         ],
         [[f'{f}_{s}', name, '机器人运动学预演' if s == 'R' else '几何证据；机器人配对待验收']
          for f in ['F1', 'F2', 'F3']
          for s, name in [('R', '经典轮廓 + 圆环'), ('U', '宽体 U 形；体量 ×1.18、椭圆比 1.05'), ('E', '椭圆相位型；椭圆比 1.15')]],
         'runs/environment-solvability/horseshoe_ring/family_space_plan_v1/representatives.png',
         '同尺度部件中心线对照，不是装配姿态；动作差异请看动态预演及路线图。',
         [['九格与 IK 路线', 'runs/environment-solvability/horseshoe_ring/family_space_plan_v1/index.html'],
          ['四款全程动态对照', 'runs/demo_metadata/horseshoe_ring/2026-09-17_trace_scene_variants_v1/index.html'],
          ['耦合形状探索', 'runs/environment-solvability/horseshoe_ring/coupled_shape_variants_v1/index.html'],
          ['最新空间规划', 'docs/develop/tasks/horseshoe_ring_family_space_zh.md']],
         ['外观轴包括马蹄轮廓（宽 U、收腰／内凹的早期探索）、目标环椭圆度与相位、链长；必须联合采样并重算抓点和 IK。不能给椭圆环增加无人控制的转动。',
          '每条视频约 69.08 秒，physics_steps=0；换抓基于运动学接触假设。完整播放不代表完整动力学执行。',
          '先强化 F2/F3 的路线区别，再做 F1_U/F1_E，随后扩展四个配对。原版仍单列为 original 变体。']),
    task('interlocked_claws', 'Interlocked Claws · 嵌合体脱困', 'A0 有完整参考执行；另外 8 款为计划',
         '规划三个动作与结构差异明显的 family：圆杆回钩、螺旋冠、正交双窗。当前只有 A0 原始网格完成参考全过程。',
         [
             ['A 空间互绕', '保留原参考的通过顺序，改变绕行与出平面避让', 'A0 原版；A1 横跨 ×1.25、深度 ×0.85；A2 宽 ×0.85、高 ×1.25、深 ×1.20'],
             ['B 螺旋推进', '相对旋转 100°并同步推进，再侧退', 'B0 40 mm；B1 矮宽扇翼 32 mm；B2 细高长冠 50 mm'],
             ['C 换轴翻转', '内推 → 第一轴翻转 → 窗间转移 → 第二轴翻转 → 退出', 'C0 标准双窗；C1 横移约 56 mm（基型 40 mm）；C2 增加腔深与升降'],
         ],
         [[f'{f}{i}', name, '完整参考物理执行；接触鲁棒性未通过' if f == 'A' and i == 0 else '候选设计；未建模／未验证']
          for f, names in [('A', ['经典回钩', '宽展浅钩', '高窄深钩']),
                           ('B', ['标准螺旋冠', '矮宽扇翼', '细高长冠']),
                           ('C', ['标准双窗', '横向宽跨', '高阶深腔'])]
          for i, name in enumerate(names)],
         'runs/concept_design/interlocked_claws/2026-09-17_three_structures_v1/three_structures_concept.png',
         '已有概念图，仅表达三种结构方向；不代表 B/C 已完成 CAD 或物理验证。',
         [['九款规划页', 'runs/environment-solvability/interlocked_claws/family_space_plan_v1/index.html'],
          ['完整空间规划', 'docs/develop/tasks/interlocked_claws_family_space_zh.md'],
          ['参考执行可靠性报告', 'runs/demo_metadata/interlocked_claws/2026-09-17_reference_full_v1/reliability_report.json']],
         ['A0 的 158.6 秒录像覆盖 12 阶段、落架释放和自由静置；两种时间步完整参考执行通过，使用预抓取与理想刚性辅助抓持。',
          'generic_contact_robustness_passed=false：受阻接触对照仍有失败。完整参考执行成立，但不能据此宣称通用接触鲁棒性或纯摩擦抓取通过。',
          'B 的冠高、层间距和推进量，以及 C 的窗偏移、腔深和转移行程需联动；所有尺寸目前是设计目标。先验收三个基型，再扩展六款外观及随机生成。']),
    task('lock_picking', 'Lock Picking · 三锁片钥匙机构', '9 款已有几何 + IK；代表视频尚缺',
         '当前版本固定三齿，用 1/2/3 次必要回退作为宏观 family。S/M/L 仅调整可见几何，盘距保持或扩大，旧小间距方案已停用。',
         [
             ['F1 一次回退', '回退一次，复位 30°后再插入', 'D1 两槽：−30°、0°；D1 限位 ±15°'],
             ['F2 两次回退', '依次复位 28°、32°', 'D1 三槽：−60°、−32°、0°；限位 ±16°'],
             ['F3 三次回退', '三次各复位 24°', 'D1 四槽：−72°、−48°、−24°、0°；限位 ±12°'],
         ],
         [[f'{f}_{s}', name, '几何与解锁 IK 已检查；尚无代表录像']
          for f in ['F1', 'F2', 'F3']
          for s, name in [('S', '小盘通视：盘径 130 mm / 盘距 150 mm'),
                          ('M', '标准基型：盘径 160 mm / 盘距 150 mm'),
                          ('L', '大盘加宽：盘径 190 mm / 盘距 180 mm')]],
         'runs/environment-solvability/lock_picking/family_space_v2/representatives.svg',
         '最新 v2，三齿固定；盘距均不小于 150 mm，旧 v1 的 68–102 mm 范围不再使用。',
         [['v2 九宫格', 'runs/environment-solvability/lock_picking/family_space_v2/index.html'],
          ['最新规则', 'docs/develop/tasks/lock_picking_family_space_zh.md'],
          ['宽间距基准 demo', 'runs/environment-solvability/lock_picking/spaced_initial/index.html']],
         ['联合范围：R=65–95 mm，max(150,150×R/80)≤p≤180 mm；钥匙齿间距=p、握柄偏移=3p+45 mm、全插入行程=4p。三齿数量轴已撤回。',
          '九款新实例的机器人场景碰撞、抓起／松手与接触动力学尚未验收；必要回退下界限定于声明的同轴准静态模型。',
          '150 mm 盘距基准有一次完整成功执行，但仅 agentview 一路全程录像；既非九款代表的录像，也未满足三视角归档。优先补 F1_M/F2_M/F3_M。']),
    task('fiber_bundling', 'Fiber Bundling · 多芯线穿环收束', '4 / 12 实例已归档；其余处理中',
         '变体只控制线数 N 与环内半径 R，形成稀疏、标准、密集三类。它们是几何类别，尚未证明对应三种不同 IK 机制或难度。',
         [
             ['稀疏 sparse', 'N∈{4,5,6}，代表为 4 芯', '每类均使用 R=12.8–15.0 mm；不绑定线数和孔径'],
             ['标准 standard', 'N∈{7,8,9,10}，代表为 8 芯', '固定单线半径 1.2 mm、护套半径 12 mm、根部圆半径 8 mm'],
             ['密集 dense', 'N∈{11,…,16}，代表为 16 芯', '根部最小间隙与实际碰撞孔径需检查；更多线意味着更多接触对'],
         ],
         [[f'N{n}_R{r}', f'{n} 芯 · 内半径 {r} mm · 细铜杆支架',
           '完整 demo；严格时间步线形对照通过' if n == 4 else '几何已生成；完整执行／复核／归档处理中']
          for n in [4, 8, 16] for r in [12.8, 13.5, 15.0]],
         'runs/environment_bootstrap/fiber_bundling/2026-09-17_density_radius_v1/density_scene_comparison.png',
         '4 / 8 / 16 芯的同视角实际场景，均为 R=13.5 mm；图像不代表全程执行均已完成。',
         [['两参数九格示意', 'runs/environment_bootstrap/fiber_bundling/2026-09-17_density_radius_v1/density_radius_grid.png'],
          ['变体与材料定义', 'docs/develop/tasks/fiber_bundling_density_radius_zh.md'],
          ['12 个实例的执行清单', 'runs/environment-solvability/fiber_bundling/variant_demos_v1/README.md'],
          ['逐实例状态', 'runs/environment-solvability/fiber_bundling/variant_demos_v1/status.json']],
         ['已归档旧支柱 8 芯 / R13.5：视频约 176.95 秒，两种时间步均成功，严格全程线形对照未通过（最大差约 4.93 mm）。',
          '已归档细铜杆 4 芯 / R12.8、R13.5、R15.0 三款：各 116.7 秒，严格线形对照均通过。新支柱直径 5 mm，不能继承旧矩形支柱的物理证据。',
          '九个正式几何代表之外，还规划 5 芯、6 芯 / R13.5 作为过渡；连同旧 8 芯共 12 个实例。5 芯两次运行已通过、待归档；6 芯和新 8 芯 / R13.5 主运行成功，仍待独立复核与归档。',
          '只抓粗护套，接触后辅助夹持，最终全部细线与前端护套穿环，末态仍夹持；没有强制逐根顺序。材料为可保留形变的被动关节链近似，并非已标定的真实铜线本构。']),
]

GAPS = [
    dict(id='rope_threading', title='Rope Threading · 绳穿三环', state='尚无完整成功 demo',
         text='场景及单环穿入／滑动／释放试验已建立；半时间步初始接触线形 RMS 差约 7.76 mm，超过 2 mm 门槛。其后显存不足中断，仍需先解决步长敏感性，再补三环、换手与回退全过程。',
         link='runs/environment-solvability/rope_threading/physics_v5/index.html'),
    dict(id='knot_untying', title='Knot Untying · 解绳结', state='完整成功录像仍在录制／验收',
         text='单手抓持、抬升、释放已通过；51 秒抽绳未解开，63 秒分段抽绳抽出自由端但留有回环。最新 v8 双手展开录像仍在执行，未形成完成报告及正式归档；此前 P3 网格对照也未通过。过程片段不能算完整成功解结 demo。',
         link='docs/develop/tasks/knot_untying_recording_attempt_zh.md'),
    dict(id='buzz_wire_3d', title='3D Buzz Wire · 立体电流棒', state='无完整机器人 demo · 补充盘点',
         text='今日未发现独立工程会话。现存材料为约 17 秒的平面局部接触试验；真正空间路径与机器人全过程尚缺。此项作为项目遗漏检查列入，不算今日新增工作。',
         link='runs/environment_bootstrap/buzz_wire_3d/bend_contact/report.json'),
    dict(id='horseshoe_gap', title='马蹄环 · 物理执行缺口', state='有全程预演；无完整物理 demo',
         text='原版和三个种子均为 physics_steps=0 的运动学预演；完整力驱动抓取、链动力学及换抓仍待验证。九款规划见第一类。', link='#horseshoe_ring'),
    dict(id='lock_gap', title='开锁 · 多视角归档缺口', state='有成功全程单视角；正式归档未齐',
         text='宽间距基准确有成功全程 agentview 录像，不应记成完全没有 demo；但缺三路同步完整视角，九款新代表尚无录像。变体计划见第一类。', link='#lock_picking'),
]

EXTRA_KEYHOLE = [
    ['offset_window 偏心窗口', '小偏心绕行；仍兼容原解法', '物理与独立复查通过；全程工作目录录像 24.08 s，未正式归档'],
    ['double_gate 双重错槽', '增加两道不同高度的横向换槽', '物理报告通过；独立复核与完整录像未完成'],
    ['tilted_window 倾转穿窗', '25°侧转 + 8°出平面倾转，再恢复', '物理与复查通过；现有近景只到 13.25 s / 约 28.5 s 全流程，不作完整 demo'],
]


def rel(path):
    if path.startswith('#'):
        return path
    return os.path.relpath(ROOT / path, OUT)


def link(label, path):
    return f'<a href="{E(rel(path), quote=True)}">{E(label)}</a>'


def table(headers, rows):
    return '<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{E(x)}</th>' for x in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join(f'<td>{E(str(x))}</td>' for x in row) + '</tr>' for row in rows) + '</tbody></table></div>'


def inspection_html(task_id):
    item = INSPECTIONS[task_id]
    badges = ''.join(f'<span class="gate-badge gate-{item["gates"][g["id"]]["status"]}">{g["id"]} · {STATUS_LABELS[item["gates"][g["id"]]["status"]]}</span>' for g in GATES)
    rows = []
    for g in GATES:
        result = item['gates'][g['id']]
        refs = ' '.join(link(f'证据 {i}', p) for i, p in enumerate(result['references'], 1))
        rows.append(f'<tr><td>{g["id"]} · {E(g["title"])}</td><td><span class="gate-badge gate-{result["status"]}">{STATUS_LABELS[result["status"]]}</span></td><td>{E(result["evidence"])}</td><td>{E(result["gap"])}</td><td><div class="links">{refs}</div></td></tr>')
    return f'''<div class="inspection" id="inspect-{task_id}"><h3>五项门槛 Inspect</h3><div class="gate-strip">{badges}</div>
<p><strong>判断：</strong>{E(item['summary'])}</p><p><strong>现在可提炼：</strong>{E(item['extract_now'])}</p>
<p><strong>下一步：</strong>{E(item['next_step'])}</p><details><summary>展开五项依据、缺口与来源</summary><p class="caption">判断基准：{E(item['baseline'])}</p>
<div class="table-wrap"><table class="gate-detail"><thead><tr><th>门槛</th><th>状态</th><th>已有证据</th><th>缺口 / 范围</th><th>来源</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div></details></div>'''


def maturity_html(snapshot):
    rows = []
    for task_id, item in INSPECTIONS.items():
        badges = ''.join(f'<td><span class="gate-badge gate-{item["gates"][g["id"]]["status"]}">{STATUS_LABELS[item["gates"][g["id"]]["status"]]}</span></td>' for g in GATES)
        rows.append(f'<tr><td><a href="#inspect-{task_id}">{E(item["title"])}</a></td>{badges}<td>{E(item["extract_now"])}</td></tr>')
    definitions = table(['门槛', '达到什么程度', '可开始提炼什么'], [[f'{g["id"]} · {g["title"]}', g['criterion'], g['extract']] for g in GATES])
    return f'''<section id="maturity"><p class="eyebrow">INSPECT / EXTRACTION READINESS</p><h2>单任务五项门槛 · 十任务总览</h2>
<p class="caption">增补检查：{E(snapshot['inspected_at'])}。{E(snapshot['scope'])}</p>
<p>按证据逐项判断，不把 demo 数量当作完成度，也不把五项相加打分。“达到”只在对应基准和声明范围内成立；“部分达到”表示已有可复用部分但仍有明确缺口；“尚未验证”表示没有足够记录，不能据此断言实现必然失败。</p>
<p><strong>当前提炼重点：</strong>Keyhole 可优先抽取参数生成与验证阶段；Coil、刺球、开锁适合抽取任务契约和证据协议；光纤有可用的稀疏子集与参数 RNG；马蹄环可先抽取几何层邻域证书。Claws、绳穿环、解绳结、电流棒先收敛基准和局部验证。</p>
<p><strong>共性缺口：</strong>本轮未找到覆盖完整初态的新进程归档恢复验收；现有保存资料可支持 Spec / 加载接口的草案，但不能直接标为 G1 通过。G4 尚无一个任务在“无需逐例修补 + 完整接受 / 拒绝 + 实例顺序无关”三个要求上全部闭环。开锁的必要回退下界可作 G5 理论特征，其余难度标定仍缺实测。</p>
<div class="table-wrap"><table class="maturity-matrix"><thead><tr><th>任务</th><th>G1 恢复</th><th>G2 语义 / 有效性</th><th>G3 邻域</th><th>G4 批量</th><th>G5 难度</th><th>现在可提炼</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<details><summary>查看五项门槛及提炼边界</summary>{definitions}<p>本次补全的 G5 判据是建议采用的验收口径，不声称已有实测结果。需要任务有效性的参数比较，先排除数值错误与协议变化；理论动作成本与经验成功率分开记录。</p></details>
<div class="links"><a href="inspection.json">五项结构化检查</a><a href="inspection_snapshot.json">检查来源与哈希</a><a href="inspect_probes.json">光纤 seed 顺序复测</a></div></section>'''


def main():
    snapshot = json.loads((OUT / 'evidence_snapshot.json').read_text())
    inspect_snapshot = json.loads((OUT / 'inspection_snapshot.json').read_text())
    inspection_report = dict(gates=GATES, status_labels=STATUS_LABELS,
                             inspection=INSPECTIONS, **inspect_snapshot)
    (OUT / 'inspection.json').write_text(json.dumps(inspection_report, ensure_ascii=False, indent=2) + '\n')
    entries = snapshot['catalog']['entries']
    for t in TASKS:
        t['inspection'] = INSPECTIONS[t['id']]
        t['media'] = []
        for e in entries:
            if e['task_id'] != t['id'] or (t['id'] == 'cast_keyhole' and e['classification'] == 'kinematic_rehearsal'):
                continue
            directory = Path('runs/demo_metadata') / e['directory']
            videos = {k.removesuffix('.mp4'): str((ROOT / 'runs/demo_metadata' / v).resolve().relative_to(ROOT)) for k, v in e.get('video_files', {}).items()}
            preferred = ['detail', 'front_oblique', 'three_views', 'composite', 'extraction_front_oblique', 'preview', 'four_views', 'oblique', 'cam_high']
            camera = next((k for k in preferred if k in videos), next(iter(videos)))
            poster = next((str(directory / name) for name in ['initial_detail.png', 'initial_front_oblique.png', 'initial_cam_low.png', 'initial_agentview.png', 'initial_cam_high.png'] if (ROOT / directory / name).exists()), None)
            page = str(directory / 'index.html') if (ROOT / directory / 'index.html').exists() else str(directory / 'archive_manifest.json')
            t['media'].append(dict(title=e['title'], variant=e.get('variant'), kind=e['classification'],
                                   duration_s=e.get('duration_s'), scope=e['scope'], src=videos[camera], camera=camera,
                                   views=videos, poster=poster, page=page,
                                   manifest=str(directory / 'archive_manifest.json')))
    # These are comparisons of existing runs; never count them as new executions.
    comparisons = {
        'cast_keyhole': [('九款全过程并排对照', 'runs/demos/cast_keyhole/2026-09-17_families_v1_process_grid.mp4'),
                         ('九款灰色外形对照（非执行）', 'runs/demos/cast_keyhole/2026-09-17_families_v1_shape_grid.mp4')],
    }
    report = dict(date='2026-09-17', cutoff=snapshot['cutoff'], timezone='America/Chicago',
                  scope='今日会话及其引用的累计产物；不声称为整周逐日审计。', tasks=TASKS,
                  demo_only=[], gaps=GAPS, extra_keyhole=EXTRA_KEYHOLE,
                  sources=snapshot['sessions'], comparisons=comparisons,
                  inspection=inspection_report)
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    def video_card(m):
        kind = '运动学预演' if m['kind'] == 'kinematic_rehearsal' else '物理执行 · 辅助抓持'
        if m['title'].startswith('Claw'):
            kind = '完整参考执行 · 接触鲁棒性未通过'
        poster = f' poster="{E(rel(m["poster"]), quote=True)}"' if m.get('poster') else ''
        views = ''.join(f'<option value="{E(rel(p), quote=True)}" {"selected" if p == m["src"] else ""}>{E(k)}</option>' for k, p in m['views'].items())
        duration = f'{m["duration_s"]:.1f} s' if m.get('duration_s') else ''
        return f'''<article class="video-card"><div class="video-head"><span class="badge">{kind}</span><span>{duration}</span></div>
<video controls playsinline muted preload="none"{poster} src="{E(rel(m['src']), quote=True)}"></video>
<h4>{E(m['title'])}</h4><label>视角 <select class="camera">{views}</select></label>
<p>{E(m['scope'])}</p><div class="links">{link('播放页 / 清单',m['page'])} {link('直接打开 MP4',m['src'])} {link('归档证据',m['manifest'])}</div></article>'''

    contents = []
    for i, t in enumerate(TASKS, 1):
        content = f'<section class="task" id="{t["id"]}" data-search="{E(t["title"])}"><p class="eyebrow">01 / VARIANTS · {i:02d}</p><h2>{E(t["title"])}</h2><p class="status">{E(t["status"])}</p><p class="lead">{E(t["summary"])}</p>'
        content += inspection_html(t['id'])
        content += table(['宏观轴 / Family', '对应动作', '参数与形状关系'], t['axes'])
        content += f'<figure class="overview"><a href="{E(rel(t["figure"]),quote=True)}"><img loading="lazy" src="{E(rel(t["figure"]),quote=True)}" alt="{E(t["title"])} 变体对照"></a><figcaption>{E(t["caption"])}</figcaption></figure>'
        content += table(['代表 ID', '外观 / 参数', '当前证据状态'], t['representatives'])
        content += '<div class="notes">' + ''.join(f'<p>{E(n)}</p>' for n in t['notes']) + '</div>'
        content += '<div class="links">' + ' '.join(link(label, path) for label, path in t['links']) + '</div>'
        for title, path in comparisons.get(t['id'], []):
            content += f'<details><summary>{E(title)}</summary><video class="comparison" controls playsinline muted preload="none" src="{E(rel(path),quote=True)}"></video></details>'
        content += f'<h3>可播放的已有 demo <span class="small">{len(t["media"])} 个实例</span></h3>'
        if t['media']:
            content += '<div class="videos">' + ''.join(video_card(m) for m in t['media']) + '</div>'
        else:
            content += '<p>九款代表尚无完整录像；可查看上方基准 demo。基准只有一路完整相机。</p>'
        if t['id'] == 'lock_picking':
            p = 'runs/environment-solvability/lock_picking/spaced_initial/attempt06/episode_agentview.mp4'
            if not (ROOT / p).exists():
                candidates = list((ROOT / 'runs/environment-solvability/lock_picking/spaced_initial/attempt06').glob('*agentview*.mp4'))
                p = str(candidates[0].relative_to(ROOT)) if candidates else None
            if p:
                content += f'<video class="comparison" controls muted playsinline preload="none" src="{E(rel(p),quote=True)}"></video><p class="caption">基准成功执行 · 仅单视角 · 不计为九款新代表 demo。</p>'
                t['baseline_video'] = p
        if t['id'] == 'cast_keyhole':
            content += '<details><summary>另一会话遗留的三条候选：已暂停，保留计划与现有证据</summary><p>这组与 F1/F2/F3 不是同一批：原 session 切换到刺球任务后暂停，按实例区分完成状态。</p>'
            content += table(['候选', '变体轴', '当前产物'], EXTRA_KEYHOLE)
            p = 'runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/offset_window/recording/detail.mp4'
            content += f'<video class="comparison" controls muted playsinline preload="none" src="{E(rel(p),quote=True)}"></video><p class="caption">offset_window 全程工作目录录像；尚未正式归档，不计入已归档实例数。</p>'
            content += '<div class="links">' + link('暂停交接记录', 'runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/session_handoff.json') + link('三条候选说明', 'docs/develop/tasks/cast_keyhole_inverse_variants_zh.md') + '</div></details>'
        content += '</section>'
        contents.append(content)

    nav = ''.join(f'<a href="#{t["id"]}">{E(t["title"].split(" · ")[0])}</a>' for t in TASKS)
    gap_html = ''.join(f'<article class="gap {"has-inspection" if g["id"] in INSPECTIONS else ""}"><h3>{E(g["title"])}</h3><span class="badge">{E(g["state"])}</span><p>{E(g["text"])}</p>{link("查看证据 / 计划",g["link"])}{inspection_html(g["id"]) if g["id"] in INSPECTIONS else ""}</article>' for g in GAPS)
    source_rows = [[str(i+1), s['topic'], s['session_id'], s['start_local'][:16], s['end_local'][:16], s['note']] for i,s in enumerate(snapshot['sessions'])]
    document = f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>TopoGym Weekly Report · 2026-09-17</title><link rel="stylesheet" href="style.css"></head><body>
<header><p class="eyebrow">TOPOGYM / ENGINEERING REVIEW</p><h1>变体空间与完整 Demo</h1><p class="subtitle">Weekly Report · 2026.09.17</p>
<p>基于今天的全部本地工程会话及现有产物，按「变体与演示 → 仅演示 → 尚缺全流程」整理。</p>
<div class="stats"><div><strong>14</strong><span>工程 session 记录（含跨日续接）</span></div><div><strong>7</strong><span>有变体讨论的任务</span></div><div><strong>0</strong><span>无变体讨论的完整 demo 任务</span></div><div><strong>3 + 2</strong><span>无成功全程 + 物理／归档缺口</span></div></div>
<p class="caption">统计截止：{E(snapshot['cutoff'])} America/Chicago。今天活跃的 9 项任务，另补查电流棒；此前基线标为累计产物。只审计今天的 session，不冒充整周逐日统计。</p>
<div class="links"><a href="weekly-report.md">文字周报</a><a href="report.json">结构化清单</a><a href="#maturity">五项门槛 Inspect</a><a href="#sources">会话覆盖与依据</a><a href="validation.json">链接与视频核对</a></div></header>
<nav class="topnav"><a href="#maturity">五项门槛</a><a href="#variants">01 变体与 Demo</a><a href="#demo-only">02 仅 Demo</a><a href="#missing">03 尚缺全流程</a><button id="pause-all">暂停全部视频</button><label>倍速 <select id="speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select></label></nav>
<main>{maturity_html(inspect_snapshot)}<section class="intro" id="variants"><h2>01 · 有变体讨论：轴、代表与对应 Demo</h2><p>完整物理执行、全程运动学预演、几何 / IK 证据和待实现计划分别标注。辅助抓持、预抓取起点与末态范围保留在各实例旁；图示与对照拼图不计为新增执行。</p><div class="tasknav">{nav}</div>
<label class="search">查找任务 <input id="filter" type="search" placeholder="例如 Coil、刺球、Lock"></label></section>
{''.join(contents)}
<section id="demo-only"><p class="eyebrow">02 / DEMO ONLY</p><h2>无变体讨论，但已有完整 Demo</h2><p>本次没有符合该条件的独立任务。已有完整 demo 的任务今天均讨论了变体，已归入第一类，避免重复展示。</p></section>
<section id="missing"><p class="eyebrow">03 / REMAINING</p><h2>尚无完整成功 Demo，以及物理 / 归档缺口</h2><p>前三项尚无可交付的完整成功机器人 demo；后两项已有完整播放或单视角成功录像，但仍缺物理执行或规定归档。第一类各任务的未完成变体已逐项保留。</p><div class="gaps">{gap_html}</div></section>
<section id="sources"><p class="eyebrow">EVIDENCE / COVERAGE</p><h2>会话覆盖与依据</h2><p>扫描本机 Codex 当前及归档会话、Claude 项目记录，以 America/Chicago 的 2026-09-17 消息时间筛选；包括此前开立但今天继续执行的会话。共纳入 14 份工程记录，排除自动审批、系统记录及本周报会话。续接记录按来源保留，任务层面合并去重；今天没有发现 Claude 工程消息。</p>
<p>原始报告、匹配实例的归档清单与视频优先于早期总结。今日有多个会话曾混写 Keyhole / Coil / 刺球，已按用户后续纠正及实际任务资产归类；已停用的开锁小盘距、刺球旧 v1 外形不当作现行计划。</p>
{table(['#','主题','Session ID','今日首条','今日末条','说明'], source_rows)}
<p>本报告引用仓库内相对路径，HTML 与仓库一起使用。视频仍在原归档位置；本轮只整理报告，不重新运行仿真。正在运行的光纤和解绳结按截止时刻标注。</p><div class="links">{link('Demo 总目录','runs/demo_metadata/index.html')}{link('归档规范','AGENTS.md')}<a href="evidence_snapshot.json">来源快照</a></div></section>
</main><footer>TopoGym · 2026-09-17 · Evidence before status</footer><script src="report.js"></script></body></html>'''
    (OUT / 'index.html').write_text(document)

    def md_table(headers, rows):
        return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---'] * len(headers)) + ' |'] + ['| ' + ' | '.join(str(c).replace('|','／') for c in row) + ' |' for row in rows])
    def inspection_md(task_id):
        item = INSPECTIONS[task_id]
        rows = []
        for g in GATES:
            result = item['gates'][g['id']]
            refs = ' · '.join(f'[证据 {i}]({rel(p)})' for i, p in enumerate(result['references'], 1))
            rows.append([f'{g["id"]} {g["title"]}', STATUS_LABELS[result['status']], result['evidence'], result['gap'], refs])
        return ['**五项门槛 Inspect**', '', f'判断基准：{item["baseline"]}', '',
                md_table(['门槛','状态','已有证据','缺口 / 范围','来源'], rows), '',
                f'**总结：** {item["summary"]}', '', f'**现在可提炼：** {item["extract_now"]}', '',
                f'**下一步：** {item["next_step"]}', '']
    md = ['# TopoGym Weekly Report · 2026-09-17', '',
          f'统计截止：{snapshot["cutoff"]}（America/Chicago）。依据今天活跃的 14 份工程会话记录，覆盖 9 个任务；另补查电流棒。跨日续接纳入，审批及本报告会话排除。此前 demo 作为累计基础，不声称整个星期均已审计。', '',
          '[打开可播放周报](index.html) · [结构化清单](report.json) · [来源快照](evidence_snapshot.json)', '',
          '## 单任务五项门槛 · 十任务 Inspect', '',
          f'增补检查：{inspect_snapshot["inspected_at"]}。{inspect_snapshot["scope"]}', '',
          '逐项判定，不加总成等级。“达到”仅对声明范围成立；“尚未验证”不等于实现失败。G5 的具体判据是本次补全的建议口径。', '',
          md_table(['门槛','达到什么程度','可开始提炼'],[[f'{g["id"]} {g["title"]}',g['criterion'],g['extract']] for g in GATES]), '',
          md_table(['任务','G1 恢复','G2 语义 / 有效性','G3 邻域','G4 批量','G5 难度'],[[v['title']]+[STATUS_LABELS[v['gates'][g['id']]['status']] for g in GATES] for v in INSPECTIONS.values()]), '',
          '**提炼重点：** Keyhole 的参数生成 / 验证链；Coil、刺球、开锁的任务契约和证据协议；光纤的稀疏子集 / 参数 RNG；马蹄环的几何邻域证书。其余先收敛基准与局部验证。', '',
          '**共性缺口：** 未找到完整 G1 新进程归档恢复验收；G4 的免逐例修补、完整接受 / 拒绝、实例顺序无关尚未全部闭环。开锁仅有 G5 理论动作下界，实测难度尚未标定。已有保存资料可支持 Spec / 加载草案，不等同于恢复验收已经通过。', '',
          '[结构化五项检查](inspection.json) · [检查来源与哈希](inspection_snapshot.json) · [光纤 seed 顺序复测](inspect_probes.json)', '',
          '## 1. 有变体讨论：变体轴、代表与对应 demo', '']
    for t in TASKS:
        md += [f'### {t["title"]}', '', f'**{t["status"]}。** {t["summary"]}', '']
        md += inspection_md(t['id'])
        md += [md_table(['Family', '动作', '参数'],t['axes']), '', md_table(['代表','外形','状态'],t['representatives']), '']
        md += [f'- {n}' for n in t['notes']]
        md += ['', ' · '.join(f'[{label}]({rel(path)})' for label,path in t['links']), '', '可播放 demo：', '']
        for m in t['media']:
            tag = '运动学预演' if m['kind']=='kinematic_rehearsal' else '辅助抓持物理执行'
            md += [f'- [{m["title"]}]({rel(m["src"])})（{m["duration_s"]:.1f} s；{tag}）；[多视角 / 证据]({rel(m["page"])})。']
        if t.get('baseline_video'):
            md += [f'- [宽间距基准单视角完整成功录像]({rel(t["baseline_video"])}): 尚缺三视角正式归档，不属于九款新代表。']
        for label,path in comparisons.get(t['id'],[]):
            md += [f'- [{label}]({rel(path)})。']
        if t['id']=='cast_keyhole':
            md += ['', '**另一会话暂停的三条候选（与 F1/F2/F3 分开）：**', '', md_table(['候选','动作轴','当前状态'],EXTRA_KEYHOLE), '',
                   f'[offset_window 全程工作目录录像]({rel("runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/offset_window/recording/detail.mp4")}) · [交接记录]({rel("runs/environment-solvability/cast_keyhole/inverse_motion_variants_v1/session_handoff.json")})。']
        md += ['']
    md += ['## 2. 无变体讨论，但已有完整 demo', '', '本次为空。已有完整 demo 的任务今天均有变体讨论，统一放在第一类，不重复计数。', '', '## 3. 尚无完整成功 demo，以及物理 / 归档缺口', '']
    for g in GAPS:
        target = 'index.html'+g['link'] if g['link'].startswith('#') else rel(g['link'])
        md += [f'- **{g["title"]}：{g["state"]}。** {g["text"]} [证据]({target})', '']
        if g['id'] in INSPECTIONS:
            md += inspection_md(g['id'])
    md += ['## 来源与判断口径', '',
           '最新原始报告、匹配实例归档清单和实际视频优先于早期总结。旧实例成功不继承到新几何；图示、初态环绕、未结束录像不当作完整 demo；运动学预演与辅助抓持物理执行分别标注。', '',
           md_table(['主题','Session ID','说明'],[[s['topic'],s['session_id'],s['note']] for s in snapshot['sessions']]), '',
           '本轮只生成报告，不改写归档、启动仿真或把正在运行的任务提前标记完成。HTML 使用相对仓库链接，视频未复制到报告目录。', '']
    (OUT / 'weekly-report.md').write_text('\n'.join(md))
    (OUT / 'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(f'Built {OUT}/index.html: {len(TASKS)} variant tasks, {sum(len(t["media"]) for t in TASKS)} archived instance players.')


if __name__ == '__main__':
    main()
