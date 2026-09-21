const fs = require("fs");
const path = require("path");
const url = process.argv[2] || "file:///home/jianwen/topogym/reports/weekly/2026-09-19/presentation/index.html";
const out = process.argv[3] || "/tmp/topogym-clean-slides-check";
fs.mkdirSync(out,{recursive:true});
const ws = new WebSocket("ws://127.0.0.1:9237/session");
let id=0; const pending=new Map();
ws.addEventListener("message",e=>{
 const r=JSON.parse(e.data);
 if(r.id&&pending.has(r.id)){const p=pending.get(r.id);pending.delete(r.id);r.type==="error"?p.reject(Error(JSON.stringify(r))):p.resolve(r.result);}
});
function send(method,params={}){return new Promise((resolve,reject)=>{const k=++id;pending.set(k,{resolve,reject});ws.send(JSON.stringify({id:k,method,params}));});}
const timer=setTimeout(()=>{console.error("Timeout");process.exit(1)},240000);
(async()=>{
 await new Promise((resolve,reject)=>{ws.addEventListener("open",resolve,{once:true});ws.addEventListener("error",reject,{once:true});});
 await send("session.new",{capabilities:{alwaysMatch:{}}});
 const tree=await send("browsingContext.getTree");
 const ctx=tree.contexts[0].context;
 const evaluate=async expression=>{
  const r=await send("script.evaluate",{expression,target:{context:ctx},awaitPromise:true});
  if(r.type==="exception")throw Error(JSON.stringify(r));
  return r.result.value;
 };
 const read=async expression=>JSON.parse(await evaluate("JSON.stringify("+expression+")"));
 await send("browsingContext.setViewport",{context:ctx,viewport:{width:1600,height:1000},devicePixelRatio:1});
 await send("browsingContext.navigate",{context:ctx,url,wait:"complete"});
 await evaluate("document.fonts.ready.then(()=>true)");
 const ids=await read("[...document.querySelectorAll('.slide')].map(s=>s.id)");
 const checks={url,browser:"Firefox",desktop:[],media:[],mobile:[],laptop:[],wristFullscreen:[]};
 for(const slide of ids){
  await evaluate("location.hash="+JSON.stringify(slide));
  await new Promise(r=>setTimeout(r,130));
  const layout=await read("(()=>{const s=document.querySelector('.slide:not([hidden])'),r=s.getBoundingClientRect(),f=s.querySelector('.slide-folio').getBoundingClientRect();return {id:s.id,width:r.width,height:r.height,overflow:[...s.querySelectorAll('.slide-content *')].filter(e=>{if(e.closest('svg')||e.tagName==='VIDEO')return false;const b=e.getBoundingClientRect();return b.width&&b.height&&(b.bottom>f.top+2||b.right>r.right+2||b.left<r.left-2)}).map(e=>({tag:e.tagName,cls:e.className,text:e.textContent.slice(0,60)})),videos:s.querySelectorAll('video').length};})()");
  if(layout.id!==slide||layout.overflow.length)throw Error(JSON.stringify(layout));
  checks.desktop.push(layout);
  const shot=await send("browsingContext.captureScreenshot",{context:ctx,format:{type:"image/png"}});
  fs.writeFileSync(path.join(out,slide+".png"),Buffer.from(shot.data,"base64"));
  if(layout.videos){
   const result=JSON.parse(await evaluate("(async()=>{const s=document.querySelector('.slide:not([hidden])');const vs=[...s.querySelectorAll('video')];await Promise.all(vs.map(v=>Number.isFinite(v.duration)?Promise.resolve():new Promise((r,j)=>{v.addEventListener('loadedmetadata',r,{once:true});v.addEventListener('error',j,{once:true});setTimeout(()=>j(Error('metadata timeout')),12000)})));s.querySelector('.pair-play').click();await new Promise(r=>setTimeout(r,750));const playback=vs.map(v=>({src:v.getAttribute('src'),time:v.currentTime,paused:v.paused,frames:v.getVideoPlaybackQuality().totalVideoFrames,error:v.error?.message||null}));s.querySelector('.pair-play').click();const speed=s.querySelector('.speed-select');speed.value='2';speed.dispatchEvent(new Event('change'));const rate=vs[0].playbackRate;const seek=s.querySelector('.pair-seek');seek.value=500;seek.dispatchEvent(new Event('input'));await new Promise(r=>setTimeout(r,200));const seekOk=vs.every(v=>Math.abs(v.currentTime-v.duration/2)<.12);return JSON.stringify({id:s.id,playback,rate,seekOk});})()"));
   checks.media.push(result);
   if(result.playback.some(v=>v.paused||v.time<.2||v.frames<1||v.error)||result.rate!==2||!result.seekOk)throw Error(JSON.stringify(result));
   console.log("PLAY "+slide);
  }
 }
 const played = new Set(checks.media.flatMap(r => r.playback.map(v => v.src)));
 if(played.size!==39)throw Error('Expected 39 distinct videos, got '+played.size);
 checks.mediaPlaybackVerified=played.size;
 for(const slide of ids.filter(id=>id.endsWith('-wrist'))){
  await evaluate('location.hash='+JSON.stringify(slide));
  await new Promise(r=>setTimeout(r,120));
  const cameraCheck=await read("(()=>{const g=document.querySelector('.slide:not([hidden]) .demo-grid');return {expected:g.dataset.cameras.split(','),actual:[...g.querySelectorAll('.view-select')].map(s=>s.value)}})()");
  if(JSON.stringify(cameraCheck.expected)!==JSON.stringify(cameraCheck.actual))throw Error(JSON.stringify(cameraCheck));
  for(let pane=0;pane<cameraCheck.expected.length;pane++){
   const point=await read("(()=>{const b=document.querySelectorAll('.slide:not([hidden]) .video-fullscreen')["+pane+"].getBoundingClientRect();return {x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)}})()");
   await send('input.performActions',{context:ctx,actions:[{type:'pointer',id:'mouse',parameters:{pointerType:'mouse'},actions:[{type:'pointerMove',x:point.x,y:point.y,origin:'viewport'},{type:'pointerDown',button:0},{type:'pointerUp',button:0}]}]});
   await new Promise(r=>setTimeout(r,180));
   const full=await read("(()=>{const c=document.fullscreenElement,q=c?.querySelector('.speed-select');if(q){q.value='4';q.dispatchEvent(new Event('change'))}return {active:c?.className,camera:c?.querySelector('.view-select')?.value,speedVisible:!!q?.getBoundingClientRect().height,rate:c?.querySelector('video')?.playbackRate}})()");
   if(full.active!=='video-card'||!full.speedVisible||full.rate!==4||full.camera!==cameraCheck.expected[pane])throw Error(JSON.stringify(full));
   checks.wristFullscreen.push({slide,...full});
   await evaluate('document.exitFullscreen().then(()=>true)');
   await new Promise(r=>setTimeout(r,100));
  }
 }
 // Single-view fullscreen, retained speed controls, and complete-deck fullscreen.
 // Programmatic clicks lack trusted activation. Use BiDi pointer activation for fullscreen.
 const point=await read("(()=>{const b=document.querySelector('.slide:not([hidden]) .video-fullscreen').getBoundingClientRect();return {x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)}})()");
 await send("input.performActions",{context:ctx,actions:[{type:"pointer",id:"mouse",parameters:{pointerType:"mouse"},actions:[{type:"pointerMove",x:point.x,y:point.y,origin:"viewport"},{type:"pointerDown",button:0},{type:"pointerUp",button:0}]}]});
 await new Promise(r=>setTimeout(r,500));
 checks.videoFullscreen=await read("({active:document.fullscreenElement?.className||null,speedVisible:!!document.fullscreenElement?.querySelector('.speed-select')?.getBoundingClientRect().height})");
 if(await evaluate("!!document.fullscreenElement"))await evaluate("document.exitFullscreen().then(()=>true)");
 await evaluate("document.getElementById('notes-button').click()");
 checks.notes=await read("({open:document.getElementById('notes').open,text:document.getElementById('notes-body').textContent.length})");
 await evaluate("document.getElementById('notes').close();document.getElementById('overview-button').click()");
 checks.overview=await read("({open:document.getElementById('overview').open,entries:document.getElementById('overview-list').children.length})");
 await evaluate("document.getElementById('overview').close()");
 const p=await read("(()=>{const b=document.getElementById('fullscreen-button').getBoundingClientRect();return {x:Math.round(b.x+b.width/2),y:Math.round(b.y+b.height/2)}})()");
 await send("input.performActions",{context:ctx,actions:[{type:"pointer",id:"mouse",parameters:{pointerType:"mouse"},actions:[{type:"pointerMove",x:p.x,y:p.y,origin:"viewport"},{type:"pointerDown",button:0},{type:"pointerUp",button:0}]}]});
 await new Promise(r=>setTimeout(r,400));
 checks.deckFullscreen=await evaluate("document.fullscreenElement?.tagName");
 if(await evaluate("!!document.fullscreenElement"))await evaluate("document.exitFullscreen().then(()=>true)");
 await send("browsingContext.setViewport",{context:ctx,viewport:{width:390,height:844},devicePixelRatio:1});
 for(const slide of ids){
  await evaluate("location.hash="+JSON.stringify(slide));
  await new Promise(r=>setTimeout(r,80));
  checks.mobile.push(await read("({id:document.querySelector('.slide:not([hidden])').id,scrollWidth:document.documentElement.scrollWidth,viewport:innerWidth})"));
  if(["motivation","demo-coil","demo-coil-wrist","demo-hedgehog-wrist","task-space","pipeline"].includes(slide)){
   const shot=await send("browsingContext.captureScreenshot",{context:ctx,format:{type:"image/png"}});
   fs.writeFileSync(path.join(out,"mobile-"+slide+".png"),Buffer.from(shot.data,"base64"));
  }
 }
 await send("browsingContext.setViewport",{context:ctx,viewport:{width:1366,height:768},devicePixelRatio:1});
 for(const slide of ids){
  await evaluate('location.hash='+JSON.stringify(slide));await new Promise(r=>setTimeout(r,70));
  const layout=await read("(()=>{const s=document.querySelector('.slide:not([hidden])'),f=s.querySelector('.slide-folio').getBoundingClientRect();return {id:s.id,overflow:[...s.querySelectorAll('.slide-content > *')].filter(e=>e.getBoundingClientRect().bottom>f.top+2).map(e=>e.className)}})()");
  if(layout.overflow.length)throw Error(JSON.stringify(layout));
  checks.laptop.push(layout);
 }
 if(checks.mobile.some(c=>c.scrollWidth>c.viewport+2))throw Error('Mobile overflow');
 await send("browsingContext.setViewport",{context:ctx,viewport:{width:1600,height:1000},devicePixelRatio:1});
 await evaluate("location.hash='motivation'");
 fs.writeFileSync(path.join(out,"validation.json"),JSON.stringify(checks,null,2)+"\n");
 console.log(JSON.stringify({slides:checks.desktop.length,playbackChecks:checks.media.length,desktopOverflow:checks.desktop.filter(c=>c.overflow.length),mobileOverflow:checks.mobile.filter(c=>c.scrollWidth>c.viewport+2),videoFullscreen:checks.videoFullscreen,deckFullscreen:checks.deckFullscreen,notes:checks.notes,overview:checks.overview}));
 await send("session.end");ws.close();clearTimeout(timer);
})().catch(async e=>{console.error(e);await send("session.end").catch(()=>{});ws.close();clearTimeout(timer);process.exit(1);});
