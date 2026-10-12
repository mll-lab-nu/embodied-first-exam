"""Builds ../viewer.html: a self-contained 3D viewer (three.js r128 from cdnjs; the data inlined) of the snapshots."""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data")
tiers = json.load(open(os.path.join(D, "tiers_raw.json")))
snaps = json.load(open(os.path.join(D, "snapshots.json")))
plans = json.load(open(os.path.join(D, "plans.json")))
data = {}
for name, sn in snaps.items():
    t = tiers[sn["instance"]]
    data[name] = dict(source=sn["source"], instance=sn["instance"], ropes=sn["ropes"], regions=t["regions"],
                      fixtures=t["fixtures"], plan={r: i.get("path") for r, i in (plans.get(name) or {}).items()},
                      old=sn.get("old_layout_path") or {})
html = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Knot Placement Viewer</title>
<style>
:root{--bg:#f6f6f4;--fg:#222;--panel:#fff;--muted:#666}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#1b1d20;--fg:#e8e8e8;--panel:#26292d;--muted:#aaa}}
:root[data-theme="dark"]{--bg:#1b1d20;--fg:#e8e8e8;--panel:#26292d;--muted:#aaa}
body{margin:0;background:var(--bg);color:var(--fg);font:13px/1.4 system-ui,sans-serif}
#ui{position:absolute;top:8px;left:8px;background:var(--panel);padding:8px 10px;border-radius:8px;max-width:340px;box-shadow:0 1px 4px #0003}
#ui label{display:block;margin:2px 0}#src{color:var(--muted);font-size:11px;margin-top:4px}
canvas{display:block}
</style></head><body>
<div id="ui">
<b>Knot placement viewer</b> (task frame, metres; drag = rotate, wheel = zoom, right-drag = pan)<br>
<select id="snap"></select>
<label><input type="checkbox" id="t_ropes" checked> ropes (a blue, b orange; square = clamped end)</label>
<label><input type="checkbox" id="t_regions" checked> goal regions (green)</label>
<label><input type="checkbox" id="t_fix" checked> curb / posts / clamps (grey)</label>
<label><input type="checkbox" id="t_plan" checked> one feasible goal shape (green dashed)</label>
<label><input type="checkbox" id="t_old"> today's layout path (red dotted)</label>
<label><input type="checkbox" id="t_reach" checked> arm reach rings (0.585 m at &le;3 cm, 0.55 m at &le;11 cm)</label>
<label>height x<input type="range" id="zs" min="1" max="5" step="1" value="1"> <span id="zsv">1</span></label>
<div id="src"></div></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
const DATA = __DATA__;
const BASES = {left:[-0.469,-0.019], right:[0.469,-0.019]};
const W = () => window.innerWidth, H = () => window.innerHeight;
const renderer = new THREE.WebGLRenderer({antialias:true}); renderer.setSize(W(), H());
renderer.setPixelRatio(window.devicePixelRatio || 1); document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
scene.background = new THREE.Color(dark ? 0x1b1d20 : 0xf6f6f4);
const camera = new THREE.PerspectiveCamera(40, W()/H(), 0.01, 20);
scene.add(new THREE.AmbientLight(0xffffff, 0.6)); const dl = new THREE.DirectionalLight(0xffffff, 0.7); dl.position.set(1,-1,2); scene.add(dl);
// z up: map (x, y, z) -> three (x, z, -y)
const V = (x,y,z) => new THREE.Vector3(x, z, -y);
let groups = {}, zs = 1;
function line(pts, color, dashed, width){
  const g = new THREE.BufferGeometry().setFromPoints(pts);
  const m = dashed ? new THREE.LineDashedMaterial({color, dashSize:0.012, gapSize:0.008}) : new THREE.LineBasicMaterial({color});
  const l = new THREE.Line(g, m); if (dashed) l.computeLineDistances(); return l;
}
function tube(pts, color, r){
  const curve = new THREE.CatmullRomCurve3(pts); const geo = new THREE.TubeGeometry(curve, Math.max(20, pts.length*2), r, 6, false);
  return new THREE.Mesh(geo, new THREE.MeshLambertMaterial({color}));
}
function boxMesh(f, color){
  const [hx,hy,hz] = f.size; const geo = new THREE.BoxGeometry(2*hx, 2*hz*zs, 2*hy);
  const m = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({color, transparent:true, opacity:0.85}));
  m.position.copy(V(f.pos[0], f.pos[1], f.pos[2]*zs)); m.rotation.y = (f.yaw_deg||0)*Math.PI/180; return m;
}
function build(name){
  for (const k in groups) scene.remove(groups[k]); groups = {};
  const d = DATA[name]; document.getElementById('src').textContent = name + ': ' + d.source;
  const G = k => (groups[k] = new THREE.Group(), scene.add(groups[k]), groups[k]);
  const table = new THREE.Mesh(new THREE.PlaneGeometry(1.3, 0.9), new THREE.MeshLambertMaterial({color: dark?0x3a3d42:0xd9d4c7, side:THREE.DoubleSide}));
  table.rotation.x = -Math.PI/2; table.position.y = -0.0005; G('table').add(table);
  const reg = G('regions');
  for (const r in d.regions){ const p = d.regions[r]; const s = new THREE.Shape(p.map(q => new THREE.Vector2(q[0], q[1])));
    const m = new THREE.Mesh(new THREE.ShapeGeometry(s), new THREE.MeshBasicMaterial({color:0x2ca02c, transparent:true, opacity:0.18, side:THREE.DoubleSide}));
    m.rotation.x = -Math.PI/2; m.position.y = 0.0004; reg.add(m);
    reg.add(line(p.concat([p[0]]).map(q => V(q[0], q[1], 0.0006)), 0x2ca02c, false)); }
  const fx = G('fix');
  for (const f of d.fixtures){
    if (f.kind === 'box') fx.add(boxMesh(f, f.role === 'curb' ? 0x8c8c8c : 0x444444));
    else { const c = new THREE.Mesh(new THREE.CylinderGeometry(f.radius, f.radius, f.height*zs, 20), new THREE.MeshLambertMaterial({color:0x333333}));
      c.position.copy(V(f.pos[0], f.pos[1], f.height*zs/2)); fx.add(c); } }
  const ro = G('ropes'); const cols = {a:0x1f77b4, b:0xff7f0e, rope:0x1f77b4};
  for (const r in d.ropes){ const pts = d.ropes[r].map(q => V(q[0], q[1], q[2]*zs)); ro.add(tube(pts, cols[r]||0x1f77b4, 0.004));
    const e = new THREE.Mesh(new THREE.BoxGeometry(0.012,0.012,0.012), new THREE.MeshBasicMaterial({color:0x000000})); e.position.copy(pts[0]); ro.add(e); }
  const pl = G('plan'); for (const r in d.plan){ if (d.plan[r]) pl.add(line(d.plan[r].map(q => V(q[0], q[1], 0.001)), 0x2ca02c, true)); }
  const od = G('old'); for (const r in d.old){ od.add(line(d.old[r].map(q => V(q[0], q[1], 0.0012)), 0xd62728, true)); }
  const re = G('reach');
  for (const h in BASES){ const b = BASES[h]; for (const [rad, col] of [[0.585, 0x777777], [0.55, 0xaaaaaa]]){
      const pts = []; for (let i=0;i<=96;i++){ const a = i/96*2*Math.PI; pts.push(V(b[0]+rad*Math.cos(a), b[1]+rad*Math.sin(a), 0.0008)); }
      re.add(line(pts, col, rad < 0.56)); }
    const m = new THREE.Mesh(new THREE.ConeGeometry(0.02, 0.04, 12), new THREE.MeshLambertMaterial({color:0x222222})); m.position.copy(V(b[0], b[1], 0.02)); re.add(m); }
  for (const k of ['ropes','regions','fix','plan','old','reach']){ const el = document.getElementById('t_'+k); if (el) groups[k].visible = el.checked; }
}
// orbit controls (minimal): spherical camera around a target
let tgt = new THREE.Vector3(0, 0, 0), rad = 1.25, th = -0.9, ph = 0.95, drag = null;
function place(){ camera.position.set(tgt.x + rad*Math.sin(ph)*Math.sin(th), tgt.y + rad*Math.cos(ph), tgt.z + rad*Math.sin(ph)*Math.cos(th)); camera.lookAt(tgt); }
renderer.domElement.addEventListener('mousedown', e => { drag = {x:e.clientX, y:e.clientY, b:e.button}; });
window.addEventListener('mouseup', () => drag = null);
window.addEventListener('mousemove', e => { if (!drag) return; const dx = e.clientX-drag.x, dy = e.clientY-drag.y; drag.x = e.clientX; drag.y = e.clientY;
  if (drag.b === 2 || e.shiftKey){ const right = new THREE.Vector3().subVectors(camera.position, tgt).cross(camera.up).normalize();
    tgt.addScaledVector(right, dx*0.0015*rad); tgt.y += dy*0.0015*rad; }
  else { th -= dx*0.006; ph = Math.min(Math.max(0.05, ph - dy*0.006), 3.0); } place(); });
renderer.domElement.addEventListener('contextmenu', e => e.preventDefault());
renderer.domElement.addEventListener('wheel', e => { e.preventDefault(); rad = Math.min(5, Math.max(0.15, rad*(1+Math.sign(e.deltaY)*0.08))); place(); }, {passive:false});
let tch = null; renderer.domElement.addEventListener('touchstart', e => { tch = e.touches[0]; });
renderer.domElement.addEventListener('touchmove', e => { const t = e.touches[0]; if (tch){ th -= (t.clientX-tch.clientX)*0.006; ph = Math.min(Math.max(0.05, ph-(t.clientY-tch.clientY)*0.006), 3.0); place(); } tch = t; e.preventDefault(); }, {passive:false});
window.addEventListener('resize', () => { renderer.setSize(W(), H()); camera.aspect = W()/H(); camera.updateProjectionMatrix(); });
const sel = document.getElementById('snap'); for (const k in DATA){ const o = document.createElement('option'); o.value = k; o.textContent = k; sel.appendChild(o); }
sel.onchange = () => build(sel.value);
for (const k of ['ropes','regions','fix','plan','old','reach']){ const el = document.getElementById('t_'+k); if (el) el.onchange = () => { groups[k].visible = el.checked; }; }
document.getElementById('zs').oninput = e => { zs = +e.target.value; document.getElementById('zsv').textContent = zs; build(sel.value); };
build(sel.value); place();
(function loop(){ renderer.render(scene, camera); requestAnimationFrame(loop); })();
</script></body></html>
"""
open(os.path.join(HERE, "..", "viewer.html"), "w").write(html.replace("__DATA__", json.dumps(data)))
print("wrote viewer.html", os.path.getsize(os.path.join(HERE, "..", "viewer.html")))
