"""Build the new lock environment, settle its initial state, and render stills.

    .venv-gs121-nyx/bin/python -m demos.environment_bootstrap.lock_picking_inspect

This entry never executes the lock oracle or records an execution video.
The close-up cameras are inspection views, not a proposed policy camera rig.
"""
from dataclasses import asdict
from html import escape
import json
from pathlib import Path

import hydra
import numpy as np

from topogym.tasks.lock_picking.runner import run
from topogym.tasks.lock_picking.certificate import certificate
from topogym.tasks.lock_picking._staged_lock_geometry import LockGeometry, variant_geometry
from topogym.tasks.lock_picking.scene import LockPickingSceneBuilder


def geometry_checks(cfg):
    g = variant_geometry(LockGeometry.from_config(cfg.task.geometry), str(cfg.task.variant), int(cfg.task.seed))
    proof = certificate(g, cfg.task.rotor_stops)
    if proof['minimum_required_decoupling_retreats'] != 2:
        raise ValueError('Expected the same necessary two-retreat angular family')
    # Reuse the documented nominal witness with the NEW metric pitch. This
    # verifies tab/rotor correspondence through the changed axial gaps.
    states = [
        (0, -60, [0, 0, 0]), (1, -60, [0, 0, 0]), (2, -60, [0, 0, 0]),
        (2, -45, [15, 15, 0]), (1, -45, [15, 15, 0]), (1, -75, [-15, 15, 0]),
        (1.5, -75, [-15, 15, 0]), (1.5, -45, [-15, 15, 0]), (2, -45, [-15, 15, 0]),
        (2, -15, [15, 45, 0]), (1, -15, [15, 45, 0]), (1, -45, [-15, 45, 0]),
        (1.5, -45, [-15, 45, 0]), (1.5, -15, [-15, 45, 0]), (2, -15, [-15, 45, 0]),
        (2, 0, [0, 60, 0]), (3, 0, [0, 60, 0]), (4, 0, [0, 60, 0]),
    ]
    checked = 0
    for before, after in zip(states, states[1:]):
        for f in np.linspace(0, 1, 101):
            d = before[0] + f * (after[0] - before[0])
            angle = before[1] + f * (after[1] - before[1])
            discs = np.array(before[2]) + f * (np.array(after[2]) - before[2])
            if g.clearance(d, angle, discs):
                raise ValueError('Longer-pitch witness intersects a rotor')
            if any(not stop.bounds_deg[0] <= value <= stop.bounds_deg[1]
                   for value, stop in zip(discs, cfg.task.rotor_stops)):
                raise ValueError('Witness exceeds rotor stops')
            checked += 1
    base_min = g.tip_x(0) - g.grip_offset - .025
    base_max = g.disc_x(3) + .045
    table_center = float(cfg.env.world.table.pos[0])
    table_half = float(cfg.env.world.table.size[0]) / 2
    if not table_center-table_half <= base_min < base_max <= table_center+table_half:
        raise ValueError('Longer mechanism base extends past the tabletop')
    return dict(layout=asdict(g), certificate=proof, witness_samples_checked=checked,
                witness_passed=True, base_x_bounds_m=[base_min, base_max],
                base_on_table=True, key_rear_tab_to_grip_m=g.grip_offset-3*g.pitch,
                insertion_stroke_m=4*g.pitch)


def write_index(output):
    cards = [('disc1_face', 'D1 · 金色', '三个槽：−60°、−30°、0°；盘角限位 ±15°'),
             ('disc2_face', 'D2 · 蓝色', '一个槽：−60°；盘角限位 −10° 至 +75°'),
             ('disc3_face', 'D3 · 棕色', '一个槽：0°；连续旋转')]
    rows = ''.join(f'<figure><a href="initial_{name}.png"><img src="initial_{name}.png" alt="{title} 锁眼正面"></a>'
                   f'<figcaption><strong>{title}</strong><br>{desc}</figcaption></figure>' for name, title, desc in cards)
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>开锁 · 150 mm 间距初态</title>
<style>body{margin:0;background:#edf2f5;color:#243746;font:16px/1.75 system-ui}main{max-width:1380px;margin:auto;padding:32px 24px}h1{font-size:30px;margin:0 0 12px}header,section{background:white;padding:24px;border-radius:14px;margin-bottom:22px}a{color:#126b8b}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0;border:1px solid #d9e4eb;border-radius:10px;overflow:hidden}img{display:block;width:100%;height:auto}figcaption{padding:13px 18px}.wide{max-width:1120px;margin:auto}.note{background:#fff2d5;padding:13px 18px;border-radius:8px}code{overflow-wrap:anywhere;background:#edf2f5;padding:3px 6px}@media(max-width:850px){.grid{grid-template-columns:1fr}main{padding:16px}}</style><main>
<header><h1>开锁初始态：锁片间距 85 → 150 mm</h1>
<p>钥匙凸片间距同步改为 150 mm；握柄偏移由 300 改为 495 mm，保留末端凸片后方的 45 mm 余量。所有图片均来自同一个新环境的原始 Genesis 渲染。</p>
<p><a href="config.yaml">完整实例配置</a> · <a href="assets/">环境 URDF / 网格</a> · <a href="inspection_report.json">初态与几何检查</a> · <a href="../initial_state_review/index.html">85 mm 原实例及最少回退证明</a> · <a href="../../index.html">工程验证汇总</a></p>
<p class="note">本页完成建场、初态短暂静置与几何核验。加长后的抓取、机器人可达性及全程物理执行尚未验收。近景相机用于人工检查，未定义为策略输入。</p></header>
<section><h2>先看每一片锁眼</h2><p>锁眼边缘加了 1.5 mm 宽的鲜黄色轮廓。三张原始相机图像都从钥匙入口方向正对盘面；后两张相机位于盘间空隙。透过锁眼可看到后方零件。</p><div class="grid">'''+rows+'''</div></section>
<section><h2>增大间距后的完整机构</h2><figure class="wide"><a href="initial_mechanism_overview.png"><img src="initial_mechanism_overview.png" alt="150 mm 间距的完整三锁片机构"></a><figcaption>同一初态的机构斜视图，点击查看原图。</figcaption></figure></section>
<section><h2>机器人与加长钥匙的初始布局</h2><figure class="wide"><a href="initial_agentview.png"><img src="initial_agentview.png" alt="机器人及初始支撑上的加长钥匙"></a><figcaption>钥匙尚在支撑上；这张图不代表机器人已完成抓取。</figcaption></figure></section>
<section><h2>环境所在目录</h2><p><code>'''+escape(str(output))+'''</code></p><p>角度约束与原实例相同，模型内最少仍为两次回退；轴向行程由 340 增为 600 mm，需要后续重新验证执行。</p></section></main></html>'''
    (output/'index.html').write_text(page)


@hydra.main(version_base='1.3', config_path='../../configs', config_name='lock_picking_spaced_preview')
def main(cfg):
    cfg.run.inspect_only = True
    cfg.run.build_only = False
    cfg.recording.enabled = False
    output = Path(cfg.run.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = geometry_checks(cfg)
    run(cfg, scene_builder=LockPickingSceneBuilder)
    support = json.loads((output/'initial_support.json').read_text())
    report = dict(scope='initial_state_render_and_short_settle_only',
                  geometry_checks=checks, initial_support=support,
                  initial_weight_supported=bool(support['weight_supported']),
                  settle_steps=int(cfg.task.initialization.settle_steps),
                  simulated_seconds=float(cfg.env.sim.dt)*int(cfg.task.initialization.settle_steps),
                  full_task_rollout_performed=False, robot_reachability_qualified=False,
                  new_spacing_physics_qualified=False,
                  aperture_outlines=[json.loads((output/'assets'/f'disc{i}'/'aperture_outline.json').read_text())
                                     for i in range(3) if (output/'assets'/f'disc{i}'/'aperture_outline.json').exists()],
                  inspection_cameras=['mechanism_overview','disc1_face','disc2_face','disc3_face'])
    (output/'inspection_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    write_index(output)
    print(f'Initial-state review: {output / "index.html"}', flush=True)


if __name__ == '__main__':
    main()
