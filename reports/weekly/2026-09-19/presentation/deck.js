"use strict";
(() => {
  const data = JSON.parse(document.getElementById("deck-data").textContent);
  const $ = id => document.getElementById(id);
  const slides = data.slides.map(s => $(s.id));
  const labels = {cam_high:"高位",cam_low:"低位",cam_left_wrist:"左腕",cam_right_wrist:"右腕",agentview:"全景",front_oblique:"斜前",wrist:"腕部"};
  const rates = [0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4];
  const state = new Map();
  let index = -1, cards = [], together = false, syncing = false, statusTimer;
  function tell(message) {
    $("app-status").textContent = message;
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => { $("app-status").textContent = ""; }, 4500);
  }
  function stamp(value) {
    const n = Number.isFinite(value) ? Math.max(0,value) : 0;
    return Math.floor(n/60)+":"+String(Math.floor(n%60)).padStart(2,"0");
  }
  function active() { return slides[index]; }
  function updatePlayButton() {
    const button = active()?.querySelector(".pair-play");
    if (button) {
      const playing = cards.some(c => !c.video.paused);
      button.textContent = cards.length === 1 ? (playing ? "暂停" : "播放") : (playing ? "全部暂停" : "同时播放");
    }
  }
  function pauseAll() {
    together = false;
    cards.forEach(c => c.video.pause());
    updatePlayButton();
  }
  function setTime(video, time) {
    if (Number.isFinite(video.duration)) video.currentTime = Math.min(Math.max(time, 0), video.duration);
  }
  function release() {
    if (index < 0) return;
    state.set(index, cards.map(c => ({camera:c.camera, time:c.video.currentTime, rate:c.video.playbackRate})));
    pauseAll();
    cards.forEach(c => {
      c.controller?.abort();
      c.video.removeAttribute("src");
      c.video.load();
    });
    active().querySelector(".demo-grid")?.replaceChildren();
    cards = [];
  }
  async function full(element) {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (element.requestFullscreen) await element.requestFullscreen();
      else {
        const video = element.querySelector("video");
        if (video?.webkitEnterFullscreen) video.webkitEnterFullscreen();
        else tell("请使用浏览器菜单进入全屏。");
      }
    } catch (_) { tell("请使用浏览器菜单进入全屏。"); }
  }
  function loadCamera(card, camera, time = 0, playing = false) {
    card.controller?.abort();
    card.controller = new AbortController();
    const {signal} = card.controller;
    const movie = data.media[card.group].find(m => m.camera === camera);
    card.camera = camera;
    card.video.pause();
    card.video.poster = movie.poster;
    card.video.setAttribute("aria-label", data.slides[index].title+" · "+(labels[camera] || camera));
    card.video.addEventListener("loadedmetadata", () => {
      setTime(card.video, time);
      card.video.playbackRate = Number(card.speed.value);
      if (playing && card.element.isConnected) {
        card.video.play().catch(() => { if (!signal.aborted) tell("点击视频播放按钮继续。"); });
      }
    }, {once:true, signal});
    card.video.src = movie.src;
    card.view.value = camera;
    card.video.load();
  }
  function makeCard(group, camera, pane, saved) {
    const element = document.createElement("div");
    element.className = "video-card";
    const shell = document.createElement("div");
    shell.className = "video-shell";
    const video = document.createElement("video");
    video.controls = true; video.muted = true; video.playsInline = true; video.preload = "metadata";
    shell.append(video);
    const toolbar = document.createElement("div");
    toolbar.className = "video-toolbar";
    const view = document.createElement("select");
    view.className = "view-select";
    view.setAttribute("aria-label", "画面 "+(pane+1)+" 选择视角");
    data.media[group].forEach(m => view.add(new Option(labels[m.camera] || m.camera, m.camera)));
    const speedLabel = document.createElement("span");
    speedLabel.textContent = "倍速"; speedLabel.className = "speed-label";
    const speed = document.createElement("select");
    speed.className = "speed-select";
    speed.setAttribute("aria-label", "画面 "+(pane+1)+" 播放速度");
    rates.forEach(r => speed.add(new Option(r+"×", String(r))));
    speed.value = String(saved?.rate || 1);
    const fullscreen = document.createElement("button");
    fullscreen.textContent = "⛶ 全屏"; fullscreen.className = "video-fullscreen";
    fullscreen.setAttribute("aria-label", "画面 "+(pane+1)+" 视频全屏");
    const card = {element, video, view, speed, group, camera, controller:null};
    toolbar.append(view, speedLabel, speed, fullscreen);
    element.append(shell, toolbar);
    fullscreen.onclick = () => full(element);
    video.addEventListener("dblclick", () => full(element));
    video.addEventListener("error", () => {
      if (video.getAttribute("src")) {
        const error = active()?.querySelector(".media-error");
        if (error) error.textContent = "视频未加载，请确认 media 目录完整。";
      }
    });
    video.addEventListener("play", updatePlayButton);
    video.addEventListener("pause", updatePlayButton);
    video.addEventListener("ended", updatePlayButton);
    view.onchange = () => {
      const at = video.currentTime;
      const wasPlaying = !video.paused;
      together = false;
      loadCamera(card, view.value, at, wasPlaying);
    };
    speed.onchange = () => {
      const value = Number(speed.value);
      if (together) cards.forEach(c => { c.speed.value = String(value); c.video.playbackRate = value; });
      else video.playbackRate = value;
    };
    video.addEventListener("ratechange", () => {
      if (rates.includes(video.playbackRate)) speed.value = String(video.playbackRate);
      if (together && !syncing) {
        syncing = true;
        cards.forEach(c => { c.video.playbackRate = video.playbackRate; c.speed.value = String(video.playbackRate); });
        syncing = false;
      }
    });
    loadCamera(card, saved?.camera || camera, saved?.time || 0);
    return card;
  }
  async function togglePair() {
    if (!cards.length) return;
    if (cards.some(c => !c.video.paused)) { pauseAll(); return; }
    const currentCards = [...cards];
    const lead = cards[0].video;
    const time = lead.ended ? 0 : lead.currentTime;
    together = true;
    syncing = true;
    cards.forEach(c => {
      setTime(c.video, time);
      c.video.playbackRate = lead.playbackRate;
      c.speed.value = String(lead.playbackRate);
    });
    syncing = false;
    const results = await Promise.allSettled(currentCards.map(c => c.video.play()));
    if (currentCards[0] !== cards[0]) return;
    if (results.some(r => r.status === "rejected")) {
      pauseAll(); tell("请点击各视频的播放按钮，或重试同时播放。");
    }
    updatePlayButton();
  }
  function show(next, updateHash = true) {
    next = Math.max(0, Math.min(slides.length-1, Number(next) || 0));
    if (next === index) return;
    if (index >= 0 && active().contains(document.activeElement)) document.activeElement.blur();
    release();
    index = next;
    slides.forEach((s,i) => { s.hidden = i !== index; s.inert = i !== index; });
    const grid = active().querySelector(".demo-grid");
    if (grid) {
      const saved = state.get(index);
      grid.dataset.cameras.split(",").forEach((cam,pane) => {
        const card = makeCard(grid.dataset.group, cam, pane, saved?.[pane]);
        grid.append(card.element); cards.push(card);
      });
      updatePlayButton();
      active().querySelector(".pair-play").onclick = togglePair;
      active().querySelector(".pair-reset").onclick = () => { pauseAll(); cards.forEach(c => setTime(c.video,0)); };
      active().querySelector(".pair-seek").oninput = e => {
        const d = cards[0]?.video.duration;
        if (Number.isFinite(d)) cards.forEach(c => setTime(c.video, d*Number(e.target.value)/1000));
      };
    }
    $("page-number").textContent = String(index+1).padStart(2,"0")+" / "+slides.length;
    $("chapter-label").textContent = data.slides[index].chapter;
    $("previous").disabled = index === 0;
    $("next").disabled = index === slides.length-1;
    $("progress-fill").style.width = (index+1)/slides.length*100+"%";
    document.querySelectorAll("nav a").forEach(a => {
      a.classList.toggle("active", a.dataset.section === data.slides[index].chapter.slice(0,2));
      if (a.classList.contains("active")) a.setAttribute("aria-current","location"); else a.removeAttribute("aria-current");
    });
    [...$("overview-list").children].forEach((b,i) => {
      if(i === index) b.setAttribute("aria-current","page"); else b.removeAttribute("aria-current");
    });
    document.title = "TopoGym · "+data.slides[index].title;
    if (updateHash) history.replaceState(null, "", "#"+data.slides[index].id);
    window.scrollTo({top:0,behavior:"instant"});
  }
  function hashIndex() {
    const hash = location.hash.slice(1);
    const old = hash.match(/^slide=(\d+)$/);
    return old ? Number(old[1])-1 : Math.max(0, data.slides.findIndex(s => s.id === hash));
  }
  const chapters = [["01","Motivation","motivation"],["02","Task space","task-space"],["03","Tasks & demos","tasks-rigid"],["04","Evaluation","pilot"],["05","Policies","policies"],["06","Next","next"]];
  chapters.forEach(([section,label,id]) => {
    const a = document.createElement("a"); a.href = "#"+id; a.textContent = label; a.dataset.section = section;
    document.querySelector("nav").append(a);
  });
  data.slides.forEach((s,i) => {
    const button = document.createElement("button");
    const number = document.createElement("span"); number.textContent = String(i+1).padStart(2,"0");
    button.append(number, document.createTextNode(s.title));
    button.onclick = () => { $("overview").close(); show(i); };
    $("overview-list").append(button);
  });
  $("previous").onclick = () => show(index-1);
  $("next").onclick = () => show(index+1);
  $("overview-button").onclick = () => { pauseAll(); $("overview").showModal(); };
  $("notes-button").onclick = () => {
    pauseAll();
    $("notes-title").textContent = data.slides[index].title;
    $("notes-body").textContent = data.slides[index].notes;
    $("notes").showModal();
  };
  $("fullscreen-button").onclick = () => full(document.documentElement);
  document.querySelectorAll(".dialog-close").forEach(b => { b.onclick = () => b.closest("dialog").close(); });
  document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", e => {
    if(e.target === dialog) {
      const r = dialog.getBoundingClientRect();
      if (e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom) dialog.close();
    }
  }));
  document.addEventListener("click", e => {
    const a = e.target.closest('a[href^="#"]');
    if (!a) return;
    const next = data.slides.findIndex(s => s.id === a.hash.slice(1));
    if (next >= 0) { e.preventDefault(); show(next); }
  });
  window.addEventListener("hashchange", () => show(hashIndex(), false));
  document.addEventListener("visibilitychange", () => { if(document.hidden) pauseAll(); });
  document.addEventListener("keydown", e => {
    if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector("dialog[open]")) return;
    if (["INPUT","SELECT","TEXTAREA","VIDEO"].includes(e.target.tagName) || e.target.isContentEditable) return;
    if (document.fullscreenElement?.classList.contains("video-card")) return;
    if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); show(index+1); }
    else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); show(index-1); }
    else if (e.key === "Home") { e.preventDefault(); show(0); }
    else if (e.key === "End") { e.preventDefault(); show(slides.length-1); }
    else if (e.code === "Space" && !["BUTTON","A"].includes(e.target.tagName)) { e.preventDefault(); togglePair(); }
    else if (e.key.toLowerCase() === "n") { e.preventDefault(); $("notes-button").click(); }
    else if (e.key.toLowerCase() === "o") { e.preventDefault(); $("overview-button").click(); }
    else if (e.key.toLowerCase() === "f") { e.preventDefault(); $("fullscreen-button").click(); }
  });
  setInterval(() => {
    if (!cards.length) return;
    const lead = cards[0].video;
    const duration = Number.isFinite(lead.duration) ? lead.duration : data.media[cards[0].group][0].duration;
    const seek = active().querySelector(".pair-seek");
    if (document.activeElement !== seek) seek.value = duration ? lead.currentTime/duration*1000 : 0;
    active().querySelector(".pair-time").textContent = stamp(lead.currentTime)+" / "+stamp(duration);
    if (together && !lead.paused && !lead.seeking) {
      cards.slice(1).forEach(c => {
        if (c.video.readyState >= 3 && !c.video.seeking && Math.abs(c.video.currentTime-lead.currentTime) > .25) setTime(c.video,lead.currentTime);
      });
    }
    if (together && cards.every(c => c.video.ended)) pauseAll();
  }, 200);
  show(hashIndex());
})();
