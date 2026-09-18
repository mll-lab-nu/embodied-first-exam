"""Build a local review page from recorded first-night experiment reports."""
from html import escape
import hashlib
import json
from pathlib import Path

from topogym.tasks.catalog import TASK_IDS, load_card


def review_introduction(root):
    parts = [
        '<h1>TopoGym 环境搭建与验证</h1>',
        '<p><code>environment_bootstrap</code> 指新版十项任务第一轮工程搭建与验证。'
        '本目录保存参数快照、资产核对、实例配置、生成资产、图片、视频和测试报告；'
        '环境实现源码在 <code>topogym/tasks/</code>，可复现配置在 <code>configs/</code>。</p>',
        '<p>2026-09-15 起的运行记录与后续初态 review。局部试验通过、初态建场与完整任务执行分别注明，'
        '不能仅凭展示页面认定任务已完成部署。</p>',
        '<p><a href="catalog/baselines.json">十项参数清单</a> · '
        '<a href="asset_audit/report.json">资产核对</a> · '
        '<a href="verification/summary.json">首轮验证汇总</a> · '
        '<a href="../../topogym/tasks/README.md">源码与产物目录说明</a></p>',
    ]
    if (root / 'cleanup_validation/summary.json').is_file():
        parts.append('<p><a href="cleanup_validation/index.html">目录整理后的运行检查</a> · '
                     '<a href="../../legacy/README.md">旧版只读存档说明</a></p>')
    if (root / 'default_presentation/report.json').is_file():
        parts.extend([
            '<section><h2>默认渲染与背景：Nyx + 封闭实验室</h2>',
            '<p>共享场景已接入 compact_lab：四面墙、顶棚、地板、柜体和门。'
            '录制与数据 RGB 采集共用 Nyx 相机接口。</p>',
            '<p><a href="default_presentation/index.html">打开默认场景预览与检查报告</a> · '
            '<a href="default_presentation/config.yaml">实例配置</a></p>',
            '<a href="default_presentation/index.html"><img style="max-width:100%" '
            'src="default_presentation/initial_room.png" alt="默认封闭实验室"></a>',
            '<p>本项验证渲染与相机链路；下方历史任务图像保留各自运行时的配置。</p></section>',
        ])
    claws = root / 'interlocked_claws/reference_initial'
    if (claws / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="interlocked-claws-preview"><h2>Claw：原始互锁件与参考初态</h2>',
            '<p>直接导入作者公开的两个原始 OBJ（14,780 / 14,480 面），保留精确结构、'
            '初始装配、双臂位姿及放置支架。原三角网格初态间隙约 5.06 mm。</p>',
            '<p><a href="interlocked_claws/reference_initial/index.html">打开场景、拆件检查与模型下载</a> · '
            '<a href="interlocked_claws/reference_initial/inspection_report.json">几何及实际加载报告</a></p>',
            '<a href="interlocked_claws/reference_initial/index.html"><img style="width:100%" '
            'src="interlocked_claws/reference_initial/initial_detail.png" alt="原始 Claw 互锁件"></a>',
            '<p>当前为零物理步的基础场景；抓持约束、完整路径与动力学脱困尚未验收。</p></section>',
        ])
    threading = root / 'rope_threading/wang_initial'
    if (threading / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="rope-threading-preview"><h2>绳穿三环：Wang 参考初态</h2>',
            '<p>1.1 m、8 mm 自由绳，三个 138 mm 通孔圆环与侧置支架；'
            '原始空间布局与材料方向保留，接入完整 ALOHA 双臂和 FEM+IPC。</p>',
            '<p><a href="rope_threading/wang_initial/index.html">打开基础场景、七路初态图与环绕预览</a> · '
            '<a href="rope_threading/wang_initial/inspection_report.json">几何和短时静置报告</a></p>',
            '<a href="rope_threading/wang_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="rope_threading/wang_initial/initial_detail.png" alt="自由绳、三个圆环及侧置支架"></a>',
            '<p>此页保留早期建模预览。严格审计已修复底座法兰与绳端初态穿插；'
            '<a href="../environment-solvability/rope_threading/physics_v5/index.html">查看当前物理验收与执行状态</a>。'
            '初态环绕不算完整机器人 demo。</p></section>',
        ])
    knot = root / 'knot_untying/trefoil_initial'
    if (knot / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="knot-untying-preview"><h2>解绳结：一个松 Trefoil 单结</h2>',
            '<p>一根 8 mm 开放绳，总长约 1.074 m，两端各预留 180 mm。'
            '三个交叉上下交替；FEM+IPC 自接触采用直绳材料参考态，两端自由。</p>',
            '<p><a href="knot_untying/trefoil_initial/index.html">打开基础场景、俯视图与视频</a> · '
            '<a href="knot_untying/trefoil_initial/inspection_report.json">网格与短时静置报告</a></p>',
            '<a href="knot_untying/trefoil_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="knot_untying/trefoil_initial/initial_detail.png" alt="开放绳上的单个松结"></a>',
            '<p>当前为基础场景，机器人抓绳、解结与双臂可达性尚未验证。</p></section>',
        ])
    fiber = root / 'fiber_bundling/branched_initial'
    anchored_fiber = root / 'fiber_bundling/anchored_initial'
    if (anchored_fiber / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="fiber-anchored-preview"><h2>光纤收束（当前）：固定电源终端与承托支架</h2>',
            '<p>电缆尾端永久连接固定终端；约 830 mm 的弯曲粗线提供操作余量，前部工作段放在开放托架上。'
            '判定要求分叉端先入孔、细线与前端护套通过，尾端保持连接；反面／中段先入孔或移动终端无效。</p>',
            '<p><a href="fiber_bundling/anchored_initial/index.html">打开新场景、终端特写和预览视频</a> · '
            '<a href="../environment-solvability/fiber_bundling/anchored_attachment/report.json">固定连接与施力检查</a></p>',
            '<a href="fiber_bundling/anchored_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="fiber_bundling/anchored_initial/initial_detail.png" alt="固定电源终端、连续电缆和开放托架"></a>',
            '<p>当前是新版模型与局部检查；下方自由电缆 demo 仅作历史参考，不能用于新版验收。</p></section>',
        ])
    if (fiber / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="fiber-bundling-preview"><h2>历史自由电缆：粗绳末端分叉与窄环</h2>',
            '<p>黑色 24 mm 电缆护套中露出 8 根 2.4 mm 彩色绝缘线，露出长度 80 mm；'
            '出口先沿轴向约 16 mm，再逐渐自然外弯，可见护套切口与短铜丝线头。根部位置固定；'
            '零刚度阻尼关节允许碰撞后保留形变，已通过卸载检查。闭环孔内径 27 mm，抓取目标仅为粗绳。</p>',
            '<p><a href="fiber_bundling/branched_initial/index.html">打开基础场景、细节图与视频</a> · '
            '<a href="fiber_bundling/branched_initial/inspection_report.json">静置检查</a> · '
            '<a href="fiber_bundling/contact_probe/index.html">碰撞与卸载形变验证</a></p>',
            '<a href="fiber_bundling/branched_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="fiber_bundling/branched_initial/initial_detail.png" alt="分叉细绳与固定窄环"></a>',
            '<p>完成范围为资产、基础场景与局部诊断；完整机器人捋顺穿环尚未执行。</p></section>',
        ])
    keyhole = root / 'cast_keyhole/assembly_initial'
    if (keyhole / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="cast-keyhole-preview"><h2>Cast Keyhole：双板槽道迷宫基础场景</h2>',
            '<p>选用有官方 16 步拆解图的标准 Keyhole。金件为开口叉，银件为封闭阶梯孔；'
            '按厂家照片重建轮廓，尺寸和下部孔道穿插初态为工程设定。</p>',
            '<p><a href="cast_keyhole/assembly_initial/index.html">打开装配、单件检查与相机视频</a> · '
            '<a href="cast_keyhole/assembly_initial/inspection_report.json">碰撞加载与静置报告</a></p>',
            '<a href="cast_keyhole/assembly_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="cast_keyhole/assembly_initial/parts_inspection.png" alt="Keyhole 金叉与银色封闭阶梯孔"></a>',
            '<p>商业实物有解不代表重建模型已验证；完整路径及机器人操作待验收。</p></section>',
        ])
    coil = root / 'cast_coil/assembly_initial'
    coil_demo = root.parent / 'demo_metadata/cast_coil/2026-09-17_aloha_full'
    if (coil_demo / 'archive_validation.json').is_file():
        demo = json.loads((coil_demo / 'result.json').read_text())
        archived = json.loads((coil_demo / 'archive_validation.json').read_text())
        if archived.get('passed') and demo.get('success') and demo.get('complete'):
            parts.extend([
                '<section id="cast-coil-full-demo"><h2>Cast Coil：完整双臂物理拆解</h2>',
                '<p>从张爪预抓取开始，双侧接触后辅助抓持，抬升、三段拆解、分别放置、解除辅助、撤回并自由静置。'
                '保留 ALOHA 四路相机及近景，共五路同步录像；原型解法，不是商业实物官方八步复现。</p>',
                '<p><a href="../demo_metadata/cast_coil/2026-09-17_aloha_full/index.html">打开完整录像与执行证据</a> · '
                '<a href="../demos/cast_coil/">独立 MP4 副本</a></p></section>',
            ])
    coil_audit = root.parent / 'environment-solvability/cast_coil/photo_reference_v1'
    coil_official = root.parent / 'environment-solvability/cast_coil/official_guided_v1'
    coil_solution = root.parent / 'environment-solvability/cast_coil/solvability_explanation_v1'
    if (coil_solution / 'result.json').is_file():
        solution = json.loads((coil_solution / 'result.json').read_text())
        if solution.get('current_prototype_solvable') and (coil_solution / 'index.html').is_file():
            parts.extend([
                '<section id="cast-coil-solution"><h2>Cast Coil：当前原型有解，怎么解</h2>',
                '<p>当前实体的完整三段路径复核通过：左移、转 −90°、右移分离。'
                '为避开桌面，先将两件整体抬高 70 mm；纯摩擦抓持和官方八步仍待验证。</p>',
                '<p><a href="../environment-solvability/cast_coil/solvability_explanation_v1/index.html">打开动作坐标、可拖动路径和桌面余量说明</a></p></section>',
            ])
    if (coil_official / 'result.json').is_file():
        trial = json.loads((coil_official / 'result.json').read_text())
        parts.extend([
            '<section id="cast-coil-official-trial"><h2>Cast Coil：官方指导解法试验</h2>',
            f'<p>现有 3 倍原型，{trial["tested_candidates"]} 次候选搜索，'
            f'{trial["valid_four_move_prefixes"]} 条四步前缀通过；该次试验尚未进入完整八步或机器人执行。</p>',
            '<p><a href="../environment-solvability/cast_coil/official_guided_v1/index.html">打开逐步结果、碰撞图及独立网格复核</a></p></section>',
        ])
    if (coil_audit / 'result.json').is_file():
        parts.extend([
            '<section id="cast-coil-qualification"><h2>Cast Coil：物理与可解性审查</h2>',
            '<p>连续几何证书、受力接触正反对照、时间步减半对照及三种整体布局 / 尺度实例。'
            '原型三段路径与官方八步示意分别记录；该轮台架审查不包含完整机器人执行。</p>',
            '<p><a href="../environment-solvability/cast_coil/photo_reference_v1/index.html">打开审查结论与各项结果</a> · '
            '<a href="../environment-solvability/cast_coil/photo_reference_v1/result.json">完整报告</a></p></section>',
        ])
    if (coil / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="cast-coil-preview"><h2>Cast Coil：金银方形卷绕件基础场景</h2>',
            '<p>两个独立自由刚体，四层交替装配，保留中央通孔、侧桥和内侧缺口。'
            '依据官方装配照片、拆件照片与分解示意重建；尺寸与转动窗口仍为原型假设。</p>',
            '<p><a href="cast_coil/assembly_initial/index.html">打开装配、单件检查与绕行视频</a> · '
            '<a href="cast_coil/assembly_initial/inspection_report.json">几何和落桌检查报告</a></p>',
            '<a href="cast_coil/assembly_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="cast_coil/assembly_initial/initial_detail.png" alt="Cast Coil 金银方形卷绕件"></a>',
            '<p>此页为基础场景检查；完整解法与双臂执行结论以各自报告为准。</p></section>',
        ])
    horseshoe = root / 'horseshoe_ring/assembly_initial'
    if (root / 'horseshoe_ring/aloha_full/index.html').is_file():
        parts.extend([
            '<section id="horseshoe-aloha"><h2>Horseshoe Ring：ALOHA 全流程运动学预演</h2>',
            '<p>五刚体教程原型，翻转、折合、交接、换抓和完整脱环；四路 ALOHA 观测及实验室视角。'
            '谜题几何路径已通过连续检查，机器人力驱动抓取尚未验证。</p>',
            '<p><a href="horseshoe_ring/aloha_full/index.html"><strong>打开完整演示</strong></a> · '
            '<a href="horseshoe_ring/aloha_full/replay_report.json">预演报告</a></p>',
            '<a href="horseshoe_ring/aloha_full/index.html"><img style="width:100%" '
            'src="horseshoe_ring/aloha_full/initial_oblique.png" alt="ALOHA 双臂马蹄环预演"></a></section>',
        ])
    if (root / 'horseshoe_ring/lab_initial/index.html').is_file():
        parts.extend([
            '<section id="horseshoe-lab"><h2>Horseshoe Ring：实验室场景与尺寸对照</h2>',
            '<p>早期九刚体双马蹄装配已放入共用实验室、桌面与机械臂环境。该旧原型取环尚未验收；'
            '内径 132.8 / 136.8 mm 的大环通过直接滑出检查，只作为正对照。</p>',
            '<p><a href="horseshoe_ring/lab_initial/index.html">实验室初始场景</a> · '
            '<a href="../environment-solvability/horseshoe_ring/index.html">官方视频参考、尺寸对照与路径检查</a> · '
            '<a href="horseshoe_ring/oversized_control/index.html">大环正对照回放</a></p>',
            '<a href="horseshoe_ring/lab_initial/index.html"><img style="width:100%" '
            'src="horseshoe_ring/lab_initial/initial_room.png" alt="共用实验室中的双马蹄装配"></a></section>',
        ])
    full_fiber = root / 'fiber_bundling/full_bundle_demo'
    if (full_fiber / 'index.html').is_file():
        full_report = json.loads((full_fiber / 'report.json').read_text())
        full_status = '完整穿环检查通过' if full_report['passed'] else '尚未完成完整穿环'
        drift_mm = max(full_report['protected_shape_changes_m'].values(), default=0.)*1000
        parts.extend([
            f'<section><h2>历史自由电缆：逐根整理与整束穿环 · {full_status}</h2>',
            '<p>当前固定终端版本已改变边界条件和成功标准，本历史结果不能用于新版验收。</p>',
            '<p>仅操纵粗绳，依次用固定环外侧整理八根电线；全部容入孔径后，一次推进整束穿环。'
            f'已整理电线累计最大形变 {drift_mm:.3f} mm。当前为显式夹持端执行，尚未执行机械臂抓取。</p>',
            '<p><a href="fiber_bundling/full_bundle_demo/index.html">打开全流程 demo 与阶段跳转</a> · '
            '<a href="../environment-solvability/fiber_bundling/stability_cpu/index.html">稳定性检查</a> · '
            '<a href="fiber_bundling/full_bundle_demo/timestep_validation.json">全流程减半步长复核</a></p>',
            '<video controls preload="metadata" poster="fiber_bundling/full_bundle_demo/initial.png" '
            'src="fiber_bundling/full_bundle_demo/demo.mp4"></video></section>',
        ])
    single_fiber = root / 'fiber_bundling/single_strand_demo'
    if (single_fiber / 'index.html').is_file():
        parts.extend([
            '<section><h2>历史自由电缆：整理一根红色细线</h2>',
            '<p>仅驱动粗绳夹持端，利用固定环完成线头对准、送进、回拉整理与方向校正。'
            '细线全程被动；局部夹持端演示尚未执行机械臂实际抓取或整束穿环。</p>',
            '<p><a href="fiber_bundling/single_strand_demo/index.html">打开带阶段字幕的过程 demo</a> · '
            '<a href="fiber_bundling/single_strand_demo/report.json">物理检查</a></p>',
            '<video controls preload="metadata" poster="fiber_bundling/single_strand_demo/initial.png" '
            'src="fiber_bundling/single_strand_demo/demo.mp4"></video></section>',
        ])
    if (horseshoe / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="horseshoe-initial-preview"><h2>Horseshoe Ring：双马蹄完整装配初态</h2>',
            '<p>两个开口马蹄件、两条各三链节的短链和一个独立目标圆环；九个自由刚体通过真实孔洞与接触互套。</p>',
            '<p><a href="horseshoe_ring/assembly_initial/index.html"><strong>打开完整装配演示：全景、俯视、连接近景与视频</strong></a> · '
            '<a href="horseshoe_ring/assembly_initial/inspection_report.json">实际检查报告</a></p>',
            '<a href="horseshoe_ring/assembly_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="horseshoe_ring/assembly_initial/initial_overview.png" alt="双马蹄、两条短链和中央目标圆环"></a>',
            '<p>按用户照片重建结构；尺寸、链节数与端部构造仍为原型假设。初态演示不代表合法取环路径或机器人操作已验证。</p></section>',
        ])
    hedgehog = root / 'hedgehog_in_cage/classic_initial'
    if (hedgehog / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="hedgehog-initial-preview"><h2>刺球出笼：CLASSIC 三星初态</h2>',
            '<p>十刺球、固定笼体与静止 Panda + Robotiq 2F-85。原型统一放大 3 倍；视频只移动相机。</p>',
            '<p><a href="hedgehog_in_cage/classic_initial/index.html"><strong>打开初态演示：机器人全景、笼体近景与视频</strong></a> · '
            '<a href="hedgehog_in_cage/classic_initial/inspection_report.json">初态检查</a></p>',
            '<a href="hedgehog_in_cage/classic_initial/index.html"><img style="width:100%;max-width:100%" '
            'src="hedgehog_in_cage/classic_initial/initial_overview.png" alt="静止机械臂与 CLASSIC 十刺球"></a>',
            '<p>基于官方照片与外形尺寸的参数化重建，非官方 CAD；当前仅完成静态展示，精确刺位、退出路径和物理稳定性待验证。</p></section>',
        ])
    preview = root / 'lock_picking/spaced_initial'
    if (preview / 'inspection_report.json').is_file():
        parts.extend([
            '<section id="lock-initial-preview"><h2>开锁初态：增大间距，逐片看清锁眼</h2>',
            '<p>锁片 / 钥匙凸片间距从 85 增至 150 mm，握柄偏移同步从 300 增至 495 mm。'
            '三片锁眼边缘已加鲜黄色轮廓，下方为同一新环境的原始正视近景。</p>',
            '<p><a href="lock_picking/spaced_initial/index.html"><strong>打开新初态页面：三片近景 + 机构斜视图</strong></a> · '
            '<a href="lock_picking/spaced_initial/inspection_report.json">初态检查</a> · '
            '<a href="lock_picking/spaced_initial/config.yaml">实例配置</a></p>',
            '<div style="display:flex;gap:10px">' + ''.join(
                f'<a style="flex:1" href="lock_picking/spaced_initial/initial_disc{i}_face.png">'
                f'<img style="width:100%;max-width:100%" src="lock_picking/spaced_initial/initial_disc{i}_face.png" alt="D{i} 锁眼正视图"></a>'
                for i in range(1, 4)) + '</div>',
            '<p>已完成初态渲染、短暂静置与两次必要回退的几何核验；加长后的机器人可达性和完整物理执行待验证。'
            '下方 85 mm 原实例的运行成绩不代表新间距已通过全程验收。</p></section>',
        ])
    return parts


def main():
    root=Path(__file__).resolve().parents[1]/'runs/environment_bootstrap'
    root.mkdir(parents=True,exist_ok=True)
    experiments=[
        ('新版开锁：完整单臂固定实例','lock_picking/handle_clearance','success'),
        ('三链环：悬挂、加载、卸载夹具试验','horseshoe_ring/contact_refined','passed'),
        ('三链环：时间步减半对照','horseshoe_ring/timestep_half','passed'),
        ('电流棒：平面单弯与碰壁对照','buzz_wire_3d/bend_contact','passed'),
        ('开锁：正确／错误朝向局部对照','lock_picking/aperture_controls','passed'),
    ]
    parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        '<title>TopoGym 环境搭建与验证</title><style>',
        'body{max-width:1100px;margin:32px auto;padding:0 20px;font:17px/1.65 system-ui;background:#f5f6f8;color:#202c38}',
        'section{background:white;border:1px solid #d9e0e6;border-radius:12px;padding:22px;margin:22px 0}',
        'a{color:#1167a6}video{width:100%;max-height:620px}img{max-width:48%;vertical-align:top}',
        'table{border-collapse:collapse;width:100%}td,th{border-bottom:1px solid #ddd;padding:10px;text-align:left}',
        '.pass{color:#17683b}.fail{color:#ad2929}</style>']
    parts.extend(review_introduction(root))
    summary=[]
    coil_relative='../environment-solvability/cast_coil/photo_reference_v1/result.json'
    if (root/coil_relative).is_file():
        coil_report=json.loads((root/coil_relative).read_text())
        summary.append(dict(title='Cast Coil：原型物理与可解性审查',task_id='cast_coil',path=coil_relative,
            passed=bool(coil_report['local_physics_passed'] and coil_report['timestep_comparison']['passed']),
            prototype_geometry_solvable=coil_report['prototype_geometry_solvable'],
            formal_demo_qualified=coil_report['formal_demo_qualified'],
            formal_demo_generated=coil_report['formal_demo_generated']))
    for title,relative,success_key in experiments:
        folder=root/relative;path=folder/'report.json'
        if not path.exists():continue
        report=json.loads(path.read_text());passed=bool(report.get(success_key,False))
        artifacts=[]
        for artifact in sorted(folder.rglob('*')):
            if not artifact.is_file() or artifact.name=='artifact_manifest.json':continue
            digest=hashlib.sha256()
            with artifact.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
            artifacts.append(dict(path=str(artifact.relative_to(folder)),bytes=artifact.stat().st_size,
                                  sha256=digest.hexdigest()))
        (folder/'artifact_manifest.json').write_text(json.dumps({
            'scope':'Post-run integrity of generated artifacts; shared assets are identified in runtime configs',
            'files':artifacts},indent=2)+'\n')
        summary.append(dict(title=title,path=str(path.relative_to(root)),passed=passed))
        parts.append(f'<section><h2>{escape(title)}</h2><p class="{"pass" if passed else "fail"}">{"本次检查通过" if passed else "本次检查未通过"}</p>')
        fields=[]
        for key,label,scale,unit in (
            ('seconds','模拟时长',1,'s'),('simulated_seconds','模拟时长',1,'s'),
            ('max_contact_penetration','最大穿透',1000,'mm'),('max_penetration_m','最大穿透',1000,'mm'),
            ('max_key_fixture_contact_force','最大钥匙—机构力',1,'N'),
            ('topology_failure_steps','互套关系错误步数',1,'')):
            if key in report:fields.append(f'{label}：{report[key]*scale:.3f} {unit}')
        parts.append('<p>'+escape('；'.join(fields))+'</p>')
        parts.append(f'<p><a href="{relative}/report.json">实际报告</a> · <a href="{relative}/artifact_manifest.json">产物哈希</a></p>')
        if (folder/'probe.mp4').exists():parts.append(f'<video controls preload="metadata" src="{relative}/probe.mp4"></video>')
        elif (folder/'final_agentview.png').exists():
            parts.append(f'<img src="{relative}/initial_agentview.png"><img src="{relative}/final_agentview.png">')
        elif (folder/'final.png').exists():
            parts.append(f'<img src="{relative}/initial.png"><img src="{relative}/final.png">')
        parts.append('</section>')
    parts.append('<section><h2>十项基线参数卡</h2><table><tr><th>任务</th><th>准备的第一步</th></tr>')
    for task in TASK_IDS:
        card=load_card(task)
        parts.append(f'<tr><td><a href="../../configs/task_cards/{task}.yaml">{escape(card["title_zh"])}</a></td><td>{escape(card["first_probe"])}</td></tr>')
    parts.append('</table><p>未在上方列出物理结果的任务，本晚完成的是参数、资产或局部试验准备。</p></section></html>')
    (root/'index.html').write_text('\n'.join(parts))
    (root/'review_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(root/'index.html')


if __name__=='__main__':main()
