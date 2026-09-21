"""Build a portable browser presentation from the rendered deck and embedded media."""
from pathlib import Path
import json
import os
from urllib.parse import quote
from zipfile import ZipFile, ZIP_DEFLATED

OUT = Path(__file__).resolve().parent
ASSETS = OUT / '.weekly_2026_09_19'
NAME = 'TopoGym_Weekly_2026-09-19'
manifest = json.loads((OUT / f'{NAME}.manifest.json').read_text())


def relative(path):
    return quote(os.path.relpath(path, OUT), safe='/._-')


slides = []
assets = set()
for row in manifest['slides']:
    n = row['number']
    bg = ASSETS / f'slide-{n:02d}.jpg'
    assets.add(bg)
    movies = []
    for m in manifest['embedded_movies']:
        if m['slide'] != n:
            continue
        assets.update([Path(m['playback_file']), Path(m['poster'])])
        movies.append(dict(camera=m['camera'], group=m['group'], src=relative(m['playback_file']),
                           poster=relative(m['poster']), duration=m['duration_s'],
                           x=m['x']/13.333333*100, y=m['y']/7.5*100,
                           width=m['width']/13.333333*100, height=m['height']/7.5*100))
    slides.append(dict(number=n, title=row['title'], section=row['section'],
                       background=relative(bg), movies=movies))

template = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TopoGym 周报 · 2026-09-19 · 可播放演示</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101e31;color:#e6edf5;font-family:system-ui,"Noto Sans CJK SC",sans-serif;min-height:100vh;display:flex;flex-direction:column}
header,footer{display:flex;align-items:center;gap:12px;padding:10px 18px;flex-wrap:wrap}header{border-bottom:1px solid #33435a}strong{font-size:16px}button,select,a.button{background:#1b2d44;border:1px solid #506176;color:#eef6fc;border-radius:7px;padding:8px 12px;font:inherit;font-size:13px;cursor:pointer;text-decoration:none}button:hover,a.button:hover{background:#29465e}button:disabled{opacity:.4;cursor:default}button:focus-visible,select:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid #77cdb8;outline-offset:3px}select{max-width:min(54vw,500px)}.spacer{flex:1}#play{background:#137d69;border-color:#239a83}
main{flex:1;display:flex;align-items:center;justify-content:center;min-height:0;padding:8px 12px}#stage{position:relative;width:min(calc(100vw - 24px),calc((100vh - 152px)*16/9));aspect-ratio:16/9;background:#f5f7fa;box-shadow:0 8px 32px #0007;overflow:hidden}#background{width:100%;height:100%;display:block}video{position:absolute;background:#182438;object-fit:contain;outline:1px solid #31445c}footer{justify-content:center;min-height:60px;font-size:13px}#seek{width:clamp(100px,28vw,420px);accent-color:#77cdb8}.hint{color:#adbdce;font-size:12px}#error{color:#ffb7a9}body:fullscreen #stage{width:min(calc(100vw - 24px),calc((100vh - 152px)*16/9))}@media(max-width:650px){header,footer{gap:7px;padding:7px}.hint{display:none}select{max-width:58vw}#stage{width:calc(100vw - 16px)}main{padding:8px}header strong{font-size:13px}}
</style></head><body>
<header><strong>TopoGym · 周报</strong><select id="pages" aria-label="选择幻灯片"></select><span class="spacer"></span><a class="button" href="TopoGym_Weekly_2026-09-19.pptx">内嵌视频 PPT</a><button id="full">全屏</button></header>
<main><div id="stage" role="region" aria-label="演示幻灯片"><img id="background" alt=""><div id="videos"></div></div></main>
<footer><button id="prev" aria-label="上一页">← 上一页</button><span id="count"></span><button id="next" aria-label="下一页">下一页 →</button><button id="play">一起播放</button><button id="reset">从头播放</button><input id="seek" type="range" min="0" max="1000" step="1" value="0" aria-label="同步视频进度"><span id="time"></span><span class="hint" id="hint">方向键翻页 · 空格播放 / 暂停 · 双击画面全屏视频</span><span id="error" role="status"></span></footer>
<script>
const slides=__SLIDES__;
const $=id=>document.getElementById(id);
let index=0, videos=[], together=false;
const labels={cam_high:'高位',cam_low:'低位',cam_left_wrist:'左腕',cam_right_wrist:'右腕',agentview:'全景',front_oblique:'斜前',wrist:'腕部'};
slides.forEach((s,i)=>{const o=document.createElement('option');o.value=i;o.textContent=`${String(i+1).padStart(2,'0')} / ${s.title}`;$('pages').append(o)});
function pause(){together=false;videos.forEach(v=>v.pause());$('play').textContent='一起播放'}
function show(i){
 pause();videos.forEach(v=>{v.removeAttribute('src');v.load()});videos=[];$('videos').replaceChildren();
 index=Math.max(0,Math.min(slides.length-1,i));const s=slides[index];$('background').src=s.background;$('background').alt=`${s.section}：${s.title}`;$('stage').setAttribute('aria-label',s.title);
 s.movies.forEach(m=>{const v=document.createElement('video');v.src=m.src;v.poster=m.poster;v.preload='metadata';v.controls=true;v.muted=true;v.playsInline=true;v.setAttribute('aria-label',`${s.title} · ${labels[m.camera]} · ${m.duration} 秒`);v.style.cssText=`left:${m.x}%;top:${m.y}%;width:${m.width}%;height:${m.height}%`;
 v.addEventListener('error',()=>{$('error').textContent='视频加载失败，请保留整个浏览器版文件夹。'});
 v.addEventListener('dblclick',()=>{if(v.requestFullscreen)v.requestFullscreen().catch(()=>{})});
 $('videos').append(v);videos.push(v)});
 $('pages').value=index;$('count').textContent=`${index+1} / ${slides.length}`;$('prev').disabled=index===0;$('next').disabled=index===slides.length-1;
 ['play','reset','seek','time'].forEach(id=>$(id).hidden=!videos.length);$('seek').value=0;$('error').textContent='';updateTime();history.replaceState(null,'',`#slide=${index+1}`);
}
function stamp(n){if(!Number.isFinite(n))return '0:00';return `${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,'0')}`}
function updateTime(){if(!videos.length)return;const v=videos[0],d=v.duration||slides[index].movies[0].duration;$('time').textContent=`${stamp(v.currentTime)} / ${stamp(d)}`;$('seek').value=d?v.currentTime/d*1000:0}
async function play(reset=false){if(!videos.length)return;const t=reset?0:videos[0].currentTime;videos.forEach(v=>{if(Number.isFinite(v.duration))v.currentTime=t});together=true;$('error').textContent='';$('play').textContent='全部暂停';const result=await Promise.allSettled(videos.map(v=>v.play()));if(result.some(r=>r.status==='rejected')){pause();$('error').textContent='请再次点击播放，或使用各视频的播放控件。'}}
$('play').onclick=()=>{if(videos.some(v=>!v.paused))pause();else play()};$('reset').onclick=()=>play(true);
$('seek').addEventListener('input',()=>{const d=videos[0]?.duration;if(Number.isFinite(d)){videos.forEach(v=>{v.currentTime=d*Number($('seek').value)/1000});updateTime()}});
$('prev').onclick=()=>show(index-1);$('next').onclick=()=>show(index+1);$('pages').onchange=()=>show(Number($('pages').value));
$('full').onclick=async()=>{try{if(document.fullscreenElement)await document.exitFullscreen();else await document.body.requestFullscreen()}catch(e){$('error').textContent='可使用浏览器的全屏菜单。'}};
document.addEventListener('keydown',e=>{if(['INPUT','SELECT','BUTTON','VIDEO','A'].includes(e.target.tagName))return;if(e.key==='ArrowRight'||e.key==='PageDown'){e.preventDefault();show(index+1)}if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();show(index-1)}if(e.code==='Space'){e.preventDefault();$('play').click()}if(e.key==='Home')show(0);if(e.key==='End')show(slides.length-1)});
function tick(){if(videos.length){const lead=videos[0];if(together&&!lead.paused&&!lead.seeking){videos.slice(1).forEach(v=>{if(v.readyState>=3&&!v.seeking&&Math.abs(v.currentTime-lead.currentTime)>.2)v.currentTime=lead.currentTime})}if(together&&videos.every(v=>v.ended))pause();updateTime()}requestAnimationFrame(tick)}
show(Number((location.hash.match(/slide=(\d+)/)||[])[1]||1)-1);tick();
</script></body></html>'''

html = template.replace('__SLIDES__', json.dumps(slides, ensure_ascii=False).replace('</', '<\\/'))
page = OUT / f'{NAME}.html'
page.write_text(html)
(ASSETS / 'web_slides.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2)+'\n')
readme = '''TopoGym 周报 · 2026-09-19 浏览器演示版

解压整个目录后，用 Chrome / Edge / Firefox 打开 TopoGym_Weekly_2026-09-19.html。
无需联网，无需安装 PowerPoint。若已有网站服务，也可按相同目录结构托管。
使用方向键翻页；任务页点“一起播放”同步播放三/四路视角，可统一拖动进度条。
Claws 第 9 页为 A0 基础变体；Rope / Blanket 等未完成情况已在原页标明。
主讲内容、数值与原周报冻结快照一致。画面中的底部补充外链是静态内容，
完整原片与证据请在仓库的周报中查看。浏览器视频来自内嵌 PPT 的同一压缩副本。
独立浏览器压缩包不重复包含 57 MB 的 PPT，PPT 可从单独交付的文件打开。
'''
with ZipFile(OUT / f'{NAME}_browser.zip', 'w', ZIP_DEFLATED, compresslevel=3) as z:
    # Hide the optional PPT link in the self-contained browser-only distribution.
    portable = html.replace('<a class="button" href="TopoGym_Weekly_2026-09-19.pptx">内嵌视频 PPT</a>', '')
    z.writestr(page.name, portable)
    z.writestr('使用说明.txt', readme)
    for p in sorted(assets):
        z.write(p, p.relative_to(OUT))
print(f'Saved {page}; {len(slides)} slides, 39 playable videos; portable browser ZIP ready.')
