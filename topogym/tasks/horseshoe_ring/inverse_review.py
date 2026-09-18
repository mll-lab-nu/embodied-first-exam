"""Local review of accepted inverse-scene variants and their differing traces."""
from html import escape
import json
from pathlib import Path

from .ik_trace import OUTPUT as FIXED_OUTPUT


def write_review(output):
    output = Path(output)
    summary = json.loads((output/"summary.json").read_text())
    accepted = [r for r in summary["results"] if r["passed"]]
    rows, figures, curves = [], [], []
    dynamic = ('<section><p><a href="../coupled_shape_variants_v1/index.html">'
        '马蹄轮廓、椭圆环与链长：新的耦合形状变体与完整几何回放</a></p>'
        '<p>此入口是几何可解性结果，新形状尚未完成机器人 IK 与物理执行。</p></section>') if (output.parent/'coupled_shape_variants_v1/index.html').exists() else ""
    if (output.parent/'family_space_plan_v1/index.html').exists():
        dynamic += ('<section><p><a href="../family_space_plan_v1/index.html">'
            '3 × 3 规划：IK family 与外观代表</a>（含几何与机器人配对的证据状态）</p></section>')
    if (output/"video_demos.json").exists():
        demos = json.loads((output/"video_demos.json").read_text())
        links = "".join(f'<li><a href="{escape(item["index"], quote=True)}">{escape(item["id"])}：完整独立视频与四路相机</a></li>'
                        for item in demos["instances"])
        dynamic += (f'<section><h2>完整动态对照 · 原版 + 三个变体</h2>'
            f'<p>左上原版，右上 compact，左下 wide，右下 longer。按同一时间轴同步，完整 {demos["frames"]/demos["fps"]:.2f} 秒。</p>'
            '<p>初态与终态相似是因为沿用同一解法族，尺寸仅改变约 ±4%。重点看 21–50 秒的交接与换抓路线差别。</p>'
            f'<video id="comparison" controls preload="metadata" style="width:100%" src="{escape(demos["videos"]["oblique"], quote=True)}"></video>'
            '<p><button onclick="document.getElementById(\'comparison\').currentTime=21">交接开始 · 21 秒</button> '
            '<button onclick="document.getElementById(\'comparison\').currentTime=29.67">右臂路线 · 29.7 秒</button> '
            '<button onclick="document.getElementById(\'comparison\').currentTime=45.33">左臂路线 · 45.3 秒</button></p>'
            f'<p><a href="{escape(demos["comparison_index"], quote=True)}">打开全景 / 近景完整对照页</a></p><ul>{links}</ul></section>')
    base = json.loads((FIXED_OUTPUT/"ik_trace.json").read_text())

    def compact(trace):
        return [[f["time_s"], *f["tcp_world"]["left"]["pos_m"], *f["tcp_world"]["right"]["pos_m"]]
                for f in trace["frames"]]

    curves.append(dict(name="seed", samples=compact(base)))
    for result in accepted:
        p, scene = result["proposal"], result["scene"]
        name = p["id"]
        trace = json.loads((output/name/"ik_trace.json").read_text())
        curves.append(dict(name=name, samples=compact(trace)))
        rows.append(f'<tr><td><a href="{name}/result.json">{escape(name)}</a></td>'
            f'<td>{scene["scale_ratio"]:.3f}×</td><td>{p["yaw_deg"]:g}°</td>'
            f'<td>{p["fold_roll_deg"]:+g}°</td><td>{p["ring_grasp_shift_deg"]:+g}°</td>'
            f'<td>{escape(p["chain_family"])}</td><td>{result["maximum_arm_joint_change_rad"]:.3f} rad</td>'
            f'<td>{result["geometry"]["minimum_clearance_lower_bound_m"]*1000:.4f} mm</td>'
            f'<td><a href="{name}/ik_trace.csv">CSV</a> · <a href="{name}/ik_trace.json">JSON</a> · '
            f'<a href="{name}/config.yaml">场景</a></td></tr>')
        inspection = output/name/"inspection"
        if (inspection/"review_06_detail.png").exists():
            figures.append(f'<h3>{escape(name)}</h3><div class="images"><img src="{name}/inspection/initial_detail.png" '
                f'alt="反推场景初态"><img src="{name}/inspection/review_06_detail.png" alt="同一变体的脱环终态"></div>')
    rejected = [r for r in summary["results"] if not r["passed"]]
    rejected_text = "、".join(escape(r["proposal"]["id"])+"："+escape(r["stage"]) for r in rejected) or "本批候选均通过筛选。"
    payload = json.dumps(curves, ensure_ascii=False).replace("</", "<\\/")
    (output/"index.html").write_text('''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Horseshoe · 从轨迹反推场景</title>
<style>body{max-width:1250px;margin:32px auto;padding:0 22px;background:#eef2f5;color:#243440;font:16px/1.7 system-ui}
section{background:white;border-radius:12px;padding:22px;margin:22px 0}table{width:100%;border-collapse:collapse}
td,th{padding:8px;text-align:left;border-bottom:1px solid #ddd}a{color:#096d8d}.notice{background:#fff1cc;padding:14px;border-radius:8px}
canvas{width:100%;background:#fbfcfd}input{width:80%}.images{display:grid;grid-template-columns:1fr 1fr;gap:10px}img{width:100%}
.scroll{overflow:auto}.flow{display:flex;flex-wrap:wrap;gap:12px}.flow span{background:#e4f2ef;padding:12px;border-radius:7px}</style>
<h1>先生成轨迹变体，再反推可解场景</h1>
<p class="notice">保留完整解法的阶段与接触约束，允许关节、抓持点、空手避障路径和场景参数改变。
这些是经过检查的运动学轨迹；未验证力驱动抓取、换抓和动力学执行。</p>'''+dynamic+'''
<section><div class="flow"><span>种子 TCP / 关节轨迹</span><span>受约束变形 + IK</span><span>FK 反推初态 / 尺度</span>
<span>匹配链环几何 + 重规划空手段</span><span>完整可解性与碰撞检查</span></div>
<p>两只初始夹爪的位置与朝向用于恢复场景位姿和尺度；链环形状从已有独立证书的几何族中筛选。
IK 不唯一决定物体 CAD。抓持段必须满足固定手物相对位姿，空手段可重新规划。</p></section>
<section><h2>通过的离散实例</h2><div class="scroll"><table><tr><th>实例 / 报告</th><th>尺度比</th><th>初始偏航</th>
<th>折合摆动</th><th>圆环抓点角偏移</th><th>链环族</th><th>最大关节变化</th><th>几何间隙下界</th><th>数据</th></tr>'''
        +"".join(rows)+'''</table></div><p>尺度比相对于已验证种子；各实例的尺寸、位姿、关节和夹爪开合均记录在文件中。
几何正证据不等于物理执行保证；机器人检查仍是逐帧采样。</p></section>
<section><h2>末端轨迹对比</h2><p>灰色为种子，青色为所选变体；分别显示左右指垫中心的世界 X、Y、Z 坐标。</p>
<select id="which"></select><label> 时间 <input id="time" type="range" min="0" max="828" value="0"><output id="stamp"></output></label>
<canvas id="plot" width="1200" height="500"></canvas></section>
<section><h2>场景初态与脱环终态</h2>'''+"".join(figures)+'''</section>
<section><h2>检查范围</h2><p>所有谜题部件使用同一正尺度和随时间变化的刚体变换，内部表面距离按尺度同比变化，
因此可从所选几何族的完整路径证书继承正间隙。每个实例另查新关节轨迹、桌面间隙、手物重建一致性与最终分离。
初态沿装配长轴正反向直接拉环仍失败；这不是对所有简单解法的穷举。</p>
<p>本批筛选：'''+rejected_text+'''</p><p><a href="summary.json">批次报告</a> ·
<a href="../fixed_ik_trace_v1/index.html">固定 trace 对照</a> ·
<a href="../../../demo_metadata/horseshoe_ring/2026-09-16_aloha_full/index.html">原始完整演示归档</a></p>
<p>参考动作已发生变化，适合研究同一解法族的几何与动作泛化；目前不覆盖任意 IK 曲线反推任意谜题或全新的解法策略。</p></section>
<script>const curves='''+payload+''';const pick=document.querySelector('#which'),slider=document.querySelector('#time'),canvas=document.querySelector('#plot'),ctx=canvas.getContext('2d');
curves.slice(1).forEach((v,i)=>pick.add(new Option(v.name,i+1)));
function draw(){if(curves.length<2)return;const chosen=curves[+pick.value],base=curves[0],index=+slider.value;
ctx.clearRect(0,0,1200,500);document.querySelector('#stamp').textContent=chosen.samples[index][0].toFixed(2)+' s';
for(let side=0;side<2;side++)for(let axis=0;axis<3;axis++){let col=1+side*3+axis,x=55+side*595,y=30+axis*157,w=530,h=112;
let vals=[...base.samples,...chosen.samples].map(f=>f[col]),lo=Math.min(...vals)-.01,hi=Math.max(...vals)+.01;
ctx.strokeStyle='#d6dee5';ctx.strokeRect(x,y,w,h);ctx.fillStyle='#354956';ctx.font='13px system-ui';ctx.fillText((side?'右':'左')+' XYZ'[axis+1]+' / m',x,y-9);
ctx.fillText(hi.toFixed(2),x-40,y+8);ctx.fillText(lo.toFixed(2),x-40,y+h);
[base,chosen].forEach((v,j)=>{ctx.strokeStyle=j?'#008e8a':'#b3bcc5';ctx.lineWidth=j?2:1.5;ctx.beginPath();v.samples.forEach((f,i)=>{let px=x+i*w/(v.samples.length-1),py=y+h-h*(f[col]-lo)/(hi-lo);i?ctx.lineTo(px,py):ctx.moveTo(px,py)});ctx.stroke()});
ctx.strokeStyle='#d27835';ctx.beginPath();let xx=x+index*w/(chosen.samples.length-1);ctx.moveTo(xx,y);ctx.lineTo(xx,y+h);ctx.stroke();}}
pick.onchange=draw;slider.oninput=draw;if(curves.length>1){pick.value=1;slider.max=curves[1].samples.length-1;draw()}</script></html>''')
