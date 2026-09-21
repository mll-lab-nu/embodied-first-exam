# TopoGym 演示文稿

- **[新版研究讨论 HTML slides](../../reports/weekly/2026-09-19/presentation/index.html)**：35 页，按 motivation → task space → tasks / demos → evaluation → policies 重排；11 个任务各有原 demo 页和独立腕部页，双臂左右 wrist 并排、单臂 wrist 单独放大。39 路视频均支持倍速与全屏，另附讲者备注。详见 [新版说明](../../reports/weekly/2026-09-19/presentation/README.md)。下方为保留的旧版周报 PPT 与浏览器版。

- [2026-09-19 周报 PPTX](TopoGym_Weekly_2026-09-19.pptx)：20 页、16:9；内嵌 39 路完整 MP4；文字、四阶段进度图和 token 用量图可编辑。
- [浏览器演示版](TopoGym_Weekly_2026-09-19.html)：相同 20 页，支持同页三 / 四路视频一起播放、统一拖动进度条、全屏与方向键翻页。在浏览器打开 HTML 即可。
- [浏览器版完整压缩包](TopoGym_Weekly_2026-09-19_browser.zip)：转发到其他电脑时，完整解压后打开其中的 HTML；39 路视频一起携带，无需联网或 PowerPoint。也可保留目录结构托管到网站；目前交付本地可播放文件，未部署公网地址。
- [PDF 静态预览](TopoGym_Weekly_2026-09-19.pdf)：只显示视频封面，观看视频请打开 PPTX。
- [原始周报](../../reports/weekly/2026-09-19/weekly-report.md)：沿用工程 18:27 CDT、agent 18:24:55 CDT 的冻结快照。

正文分为任务进展、GPT-6 Astra 测试、reviewer 问题三个部分。11 个任务页的 39 路主要视频已真正嵌入 PPTX：单臂每项三路，双臂每项四路。使用桌面 PowerPoint 打开文件，进入放映模式，再点击视频画面播放；这些内嵌视频随 PPT 文件携带，不依赖仓库路径。逐视角独立播放，可使用播放器进度条查看全过程。IDE、PDF 或仅渲染幻灯片的预览器可能只显示封面。

Claws 主展示已改为 **A0 基础变体**：四路内嵌视频均为 158.6 秒；第五路近景与 B0/C0 保留为补充原片链接。A0 的理想预抓取辅助和非凸接触资格限制在页内注明，不能继承 B0/C0 的物理验收结果。

内嵌视频使用 H.264 / yuv420p，按最大宽度 960 像素压缩演示副本，逐文件核对完整解码、原帧数、帧率和时长。没有裁剪、加速或重跑物理，也没有改写原始归档。39 路中仍包含明确标注的局部 / 未完成尝试，不代表所有任务都已成功。页面底部另有 70 个原片及其他版本的外链，这些补充链接需要相应仓库目录；加上内嵌视频，覆盖原周报的全部 73 个视频。

[媒体准备脚本](prepare_weekly_2026_09_19_media.py) 使用 FFmpeg 生成演示副本并验证；随后运行 [构建脚本](build_weekly_2026_09_19.py)，使用 `python-pptx` 和 Pillow 嵌入视频、封面及可编辑图表。验证结果见 [validation.json](TopoGym_Weekly_2026-09-19.validation.json)，页码、内嵌媒体与补充链接见 [manifest.json](TopoGym_Weekly_2026-09-19.manifest.json)。验证范围为 MP4 解码、PPTX 媒体关系 / 点击播放配置及 LibreOffice 静态渲染；本环境未运行桌面 PowerPoint。

浏览器版由 [构建脚本](build_weekly_2026_09_19_web.py) 根据 PPT 渲染与同一批视频生成，页面背景为静态图、视频为原生 HTML 播放器。使用底部“一起播放”同步查看本页视角；页面中原有原片 / 验证记录文字属于静态背景，完整外链仍在 PPT 和周报里。可播放版本均明确保留原来的未完成状态与辅助抓持说明。

Firefox 浏览器实测已逐项覆盖 11 页、39 路视频：播放时钟推进、解码帧输出、统一跳转至中点、翻页释放旧视频全部通过。PPT 已检查内嵌媒体哈希与点击播放配置；桌面 PowerPoint 播放尚未在本机实测。PDF 从构建脚本另存的 `.weekly_2026_09_19/static_preview.pptx` 渲染，避免重复携带视频文件。
