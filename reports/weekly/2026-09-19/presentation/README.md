# TopoGym · HTML presentation

打开 [index.html](index.html)。35 页（34 页主讲 + 1 页原进度图附录），无外部脚本或字体依赖。

主线：Motivation → Task space → 11 项任务及阶段 → 大画面 demos → Evaluation → Code agents / VLA / RL。

- 每个任务的原 demo 页保留两块大视频，紧接一页独立的腕部视角：5 个单臂任务各一块 wrist 大视频，6 个双臂任务并排展示 left wrist / right wrist。共 22 个视频页、39 路视频，画面旁无说明栏。
- 每块视频可独立播放、选择 0.25–4× 倍速及全屏；自定义全屏中保留视角和倍速控件。
- 同时播放、同步拖动进度；翻页暂停并释放旧视频，返回保留播放位置。
- 方向键翻页，Space 播放，F 全屏，N 讲者备注，O 目录。任务清单可点击直达 demo。
- 手机上的视频纵向排列，浏览器可直接打开文件；也可按完整目录托管为静态网站。
- [讲者备注](speaker-notes.md) 保留各实例的资格限制、来源和方案细节。

资料沿用 2026-09-19 周报及现有演示媒体。已完成进展与 proposed / under development 内容分别标注。原 2M pilot 没有严格硬预算；3M offline、难度 sweep、输入 A/B、segment clip 接口和三类 policy 对照是提案，没有虚构实验结果。局部录像、未成功尝试、辅助抓持和待复验状态在主画面保留简短标记。

构建：在完整 TopoGym 仓库中运行 python3 build.py；读取周报的进度、视频清单和 token audit，生成原生 HTML / SVG 与讲者备注。不会修改源视频、模拟器或旧版 PPT。media/ 与 posters/ 使用已有演示副本。

验收：Firefox 实测 35 页桌面 / 笔记本 / 手机布局、39 路视频的实际播放、进度跳转、倍速、视频全屏、演示全屏、目录与备注。新增 11 页的 17 路腕部视频逐个检查全屏中可用的倍速控件。39 路 MP4 的 SHA-256 与此前完整解码验证过的 H.264 副本一致。见 [validation.json](validation.json) 和 [预览](preview.jpg)。

浏览器验证脚本需要已开启 WebDriver BiDi 的本机 Firefox，默认端口 9237；Node 20 使用 node --experimental-websocket validate_browser.cjs，Node 22 可直接运行。验证结果默认写入 /tmp/topogym-clean-slides-check/。
