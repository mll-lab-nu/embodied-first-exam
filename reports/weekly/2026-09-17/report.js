"use strict";
const videos = [...document.querySelectorAll("video")];
document.querySelector("#pause-all").addEventListener("click", () => videos.forEach(v => v.pause()));
document.querySelector("#speed").addEventListener("change", e => {
  videos.forEach(v => { v.playbackRate = Number(e.target.value); });
});
document.querySelector("#filter").addEventListener("input", e => {
  const query = e.target.value.trim().toLocaleLowerCase();
  document.querySelectorAll(".task").forEach(section => {
    section.hidden = !section.dataset.search.toLocaleLowerCase().includes(query);
    if (section.hidden) section.querySelectorAll("video").forEach(v => v.pause());
  });
});
document.querySelectorAll('a[href^="#"]').forEach(a => a.addEventListener("click", () => {
  const target = document.getElementById(a.hash.slice(1));
  if (target && target.closest(".task")) {
    document.querySelector("#filter").value = "";
    document.querySelectorAll(".task").forEach(s => { s.hidden = false; });
  }
}));
document.querySelectorAll("select.camera").forEach(select => {
  select.addEventListener("change", () => {
    const video = select.closest("article").querySelector("video");
    const time = video.currentTime;
    const playing = !video.paused;
    const rate = video.playbackRate;
    video.pause();
    video.addEventListener("loadedmetadata", () => {
      video.currentTime = Math.min(time, Math.max(0, video.duration - 0.01));
      video.playbackRate = rate;
      if (playing) video.play().catch(() => {});
    }, {once: true});
    video.src = select.value;
    video.load();
  });
});
