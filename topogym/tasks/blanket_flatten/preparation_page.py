"""A local stage-by-stage player for controlled construction and gravity drop."""
import json
import numpy as np

LABELS = {
    'prepared_diagonal_corner': '斜折一角后',
    'prepared_longitudinal_1': '第一次纵折后',
    'prepared_transverse_1': '横折后',
    'prepared_longitudinal_2': '再次纵折后',
    'prepared_longitudinal_gather': '收成不等宽的纵向长褶后',
    'prepared_axial_bunching': '非对称纵向推挤后',
    'prepared_whole_bundle_twist': '整团扭转后',
    'prepared_lower_for_release': '降低至释放位置',
    'prepared_release': '撤掉控制，开始自由落桌',
    'initial_state_accepted': '落桌初态验收',
}


def write_page(output, report, trace, approved):
    fps = int(report['fps'])
    milestones = []
    for event in report['events']:
        if event['phase'] not in LABELS:
            continue
        index = min(len(trace['steps'])-1, int(np.searchsorted(trace['steps'], event['step'])))
        milestones.append(dict(label=LABELS[event['phase']], time=index/fps,
                               phase=event['phase'], image=f'{index:05d}_{trace["phases"][index]}_detail.jpg'))
    index = len(trace['steps'])-1
    milestones.append(dict(label='记录末态', time=index/fps, phase='recorded_end',
                           image=f'{index:05d}_{trace["phases"][index]}_detail.jpg'))
    data = dict(milestones=milestones, duration=(report['frame_count']-1)/fps,
                release=report['preparation'].get('release_seconds'), preparation=report['preparation'],
                success=approved, final=report['final'], twist_start=next(
                    (event['seconds'] for event in report['events'] if event['phase'] == 'prepare_whole_bundle_twist'), None))
    data['failure'] = report.get('error')
    for key, filename in [('twist', 'twist_review.json'), ('intersections', 'self_intersection_review.json'),
                          ('outcome', 'outcome_review.json')]:
        path = output.parent/filename
        data[key] = json.loads(path.read_text()) if path.exists() else None
    status = '初态与落桌后静置检查通过' if approved else '诊断尝试：未通过初态验收'
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>body{font:16px/1.65 system-ui,sans-serif;background:#eef2f4;color:#22313a;max-width:1450px;margin:auto;padding:28px}h1{font-size:28px}h2{font-size:21px}.note{padding:12px 18px;background:white;border-left:4px solid #397e9f}.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0}button,select{font:inherit;padding:7px 13px;border:1px solid #a4b6c1;border-radius:6px;background:white;cursor:pointer}.views,.stages{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}figure{margin:0}video,img{width:100%;display:block;border-radius:8px;background:#d8e0e4}figcaption{margin:6px 0}input{flex:1;min-width:200px}a{color:#175d87}small{color:#536671}@media(max-width:800px){.views,.stages{grid-template-columns:1fr}body{padding:16px}}</style>
<h1>__TITLE__</h1>
<p class="note"><b>__STATUS__</b>。预整形时由程序逐步控制布料，随后完全撤掉控制，从低处自由落桌。机械臂在旁停放；这是初态演示。</p>
<div class="row"><button id="play">三视角同步播放</button><button id="start">从头看折叠过程</button><button id="twistMotion">看整团拧转过程</button><button id="twist">看拧转后的结构</button><button id="drop">从自由落桌开始</button><label>速度 <select id="rate"><option value="0.25">0.25×</option><option value="0.5">0.5×</option><option value="1" selected>1×</option></select></label></div>
<div class="row"><input type="range" id="seek" aria-label="视频时间" min="0" step="0.05" value="0"><output id="time">0.00 s</output></div>
<div class="views"><figure><video muted playsinline preload="metadata" src="overview.mp4"></video><figcaption>场景全景</figcaption></figure><figure><video muted playsinline preload="metadata" src="detail.mp4"></video><figcaption>斜侧近景</figcaption></figure><figure><video muted playsinline preload="metadata" src="topdown.mp4"></video><figcaption>俯视</figcaption></figure></div>
<p id="metrics"></p>
<p id="shape"></p>
<p id="diagnosis"></p>
<h2>逐步形成的结构</h2><div class="stages" id="stages"></div>
<p><a href="detail.mp4">直接打开近景 MP4</a> · <a href="../report.json">物理与预整形报告</a> · <a href="../config.yaml">配置</a> · <a href="render_report.json">状态回放核验</a></p>
<small>预整形期间关闭布料重力，通过有速度上限、约束材料边长变化的控制引导折叠。PBD 处理材料约束和自接触。未写入粒子位置、重定义材料长度或重新绑定视觉顶点。恢复重力后不再施加预整形控制。配置中的角度是控制目标，实际效果以画面和阶段误差为准。视频逐帧呈现同一次记录，静帧取最近的 __FPS__ fps 采样点。</small>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent), videos=[...document.querySelectorAll('video')], el=id=>document.getElementById(id);
function pause(){videos.forEach(v=>v.pause());el('play').textContent='三视角同步播放';}
function seek(t){pause();videos.forEach(v=>{if(v.readyState)v.currentTime=t;else v.addEventListener('loadedmetadata',()=>v.currentTime=t,{once:true});});el('seek').value=t;el('time').value=t.toFixed(2)+' s';}
el('seek').max=data.duration;
el('play').onclick=async()=>{if(!videos[0].paused){pause();return;}if(videos[0].ended)seek(0);try{await Promise.all(videos.map(v=>v.play()));el('play').textContent='暂停';}catch(e){pause();el('time').value='请打开下方近景 MP4 链接观看';}};
el('start').onclick=()=>seek(0);const twisted=data.milestones.find(m=>m.phase==='prepared_axial_bunching')||data.milestones.find(m=>m.phase==='prepared_whole_bundle_twist');
el('twist').disabled=!twisted;el('twist').onclick=()=>seek(twisted.time);el('drop').disabled=data.release===null;el('drop').onclick=()=>seek(data.release);
el('twistMotion').disabled=data.twist_start===null;el('twistMotion').onclick=()=>seek(data.twist_start);
el('seek').oninput=e=>seek(Number(e.target.value));el('rate').onchange=e=>videos.forEach(v=>v.playbackRate=Number(e.target.value));
videos[0].ontimeupdate=()=>{let t=videos[0].currentTime;el('seek').value=t;el('time').value=t.toFixed(2)+' s';if(!videos[0].paused)videos.slice(1).forEach(v=>{if(v.readyState&&Math.abs(v.currentTime-t)>.1)v.currentTime=t;});};videos[0].onended=pause;
data.milestones.forEach(m=>{const f=document.createElement('figure'),im=document.createElement('img'),cap=document.createElement('figcaption'),b=document.createElement('button');im.src=m.image;im.alt=m.label;b.textContent=m.label+' · '+m.time.toFixed(2)+' s';b.onclick=()=>seek(m.time);cap.appendChild(b);f.append(im,cap);el('stages').appendChild(f);});
if(data.preparation.release_state){const r=data.preparation.release_state;el('metrics').textContent=`自由落桌前最低点离桌 ${(r.minimum_height_m*100).toFixed(1)} cm，最高点 ${(r.maximum_height_m*100).toFixed(1)} cm；记录末态覆盖率 ${(data.final.coverage_ratio*100).toFixed(1)}%。`;}
if(data.twist){el('shape').textContent=`端部相对转角估计 ${data.twist.approximate_relative_turn_deg.toFixed(1)}°，控制目标 ${data.twist.commanded_relative_twist_deg}°。这是布料变形下的近似测量。`;}
if(data.preparation.unmet_target_stages.length){el('shape').textContent+=' 未达到位置误差门槛的阶段：'+data.preparation.unmet_target_stages.map(n=>data.milestones.find(m=>m.phase==='prepared_'+n)?.label||n).join('、')+'。';}
if(data.intersections&&data.intersections.maximum_intersecting_faces){el('shape').textContent+=` 另有 ${data.intersections.intersecting_frames.length} 个采样帧检出网格自交，仍需修正。`;}
if(!data.success){el('diagnosis').textContent='未通过原因：'+(data.failure||'以物理报告为准');if(data.outcome&&Object.entries(data.outcome.final_initial_gates).filter(([k,v])=>!v).map(([k])=>k).join(',')==='landed'){el('diagnosis').textContent=`末态最高点 ${(data.outcome.maximum_height_m*100).toFixed(2)} cm，超过原有 ${(data.outcome.height_limit_m*100).toFixed(0)} cm 初态高度门槛；其余末态指标通过。本次没有进入额外 10 秒静置阶段。`;}}
if(twisted){videos.forEach((v,i)=>v.poster=twisted.image.replace('_detail.jpg','_'+['overview','detail','topdown'][i]+'.jpg'));seek(twisted.time);}
</script></html>'''
    title = ('宽度收成纵向长褶 → 整束拧转 → 低处落桌'
             if report['preparation'].get('construction') == 'longitudinal_gather'
             else '斜折一角 → 纵折 → 横折 → 再纵折 → 整团拧转')
    if any(stage['name'] == 'axial_bunching' for stage in report['preparation']['sequence']):
        title = '纵向长褶 → 整束拧转 → 非对称推挤 → 低处落桌'
    (output/'index.html').write_text(page.replace('__TITLE__', title).replace('__FPS__', str(fps))
        .replace('__STATUS__', status).replace('__DATA__', json.dumps(data, ensure_ascii=False).replace('</', '<\\/')))
