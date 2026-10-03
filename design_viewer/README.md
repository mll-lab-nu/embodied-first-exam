# design_viewer：用鼠标拖动谜题零件

在浏览器里打开 Hedgehog、Horseshoe、Slotted Post Ring 的场景，用鼠标直接拖动、旋转零件，体会谜题怎么解。注册进 registry 的新变体会自动出现在场景列表里。

只用于理解谜题：结果不是可解性证据，也不是成功标签（原因见“怎么实现的”）。

## 启动

```bash
cd /home/pingyue/work/topogym/.claude/worktrees/topo        # worktree 根目录
conda activate topogym && export PYTHONNOUSERSITE=1
python -m design_viewer.view --scene hedgehog_in_cage_easy --port 18080
```

在 VS Code 的「端口」面板转发 18080，然后在浏览器打开 `http://localhost:18080/`。第一次打开要下载约 25 MB，页面会显示一会儿 “PARSING…”。不用时按 Ctrl+C 关掉：服务只绑定 127.0.0.1，但本机其他用户也能连上这个端口。

## 拖动零件

1. **双击**一个零件：它出现黄色轮廓，表示已选中。
2. **按住 Ctrl，再按住右键拖动**：零件跟着鼠标移动（同时按住 Shift，则只在水平面内移动）。
3. **按住 Ctrl，再按住左键拖动**：零件旋转。
4. 松开鼠标，零件就留在原处，受重力和碰撞的作用。

不按 Ctrl 时，鼠标只控制视角：左键拖动旋转视角，右键拖动平移，滚轮缩放。空格暂停；左侧 Reset 回到初始状态。

左上角 “TopoGym” 面板：

- `scene`：切换场景。
- `Pin / unpin selected`：把选中的零件固定在原地，相当于另一只手按住它，然后去拉别的零件。
- `Unpin all`：全部松开。

想看碰撞形状时，在左侧 Visibility Groups 里勾选 group 3。

## 怎么实现的

- **场景**：调用仓库里的任务生成器（只读，与 Genesis 用的是同一套代码），得到每个零件的网格、碰撞形状和初始位姿。
- **物理**：把这些零件放进 MuJoCo，在服务器的 CPU 上计算，**不是 Genesis**。所以接触、摩擦等细节和任务不同。立柱场景里的绳用 MuJoCo cable 近似，任务里是 FEM 绳。
- **网页和交互**：MuJoCo 3.14 自带的 Web Viewer。浏览器只负责显示和鼠标；拖动时，MuJoCo 在鼠标和零件之间加一根弹簧力。

## 文件

| 文件 | 作用 |
|---|---|
| `scenes.py` | 调用任务生成器，得到零件的网格和碰撞形状；结果缓存在 `.cache/`（git 忽略），生成器代码变了会自动重建 |
| `model.py` | 把场景转成 MuJoCo 模型；固定 / 松开零件 |
| `view.py` | 网页查看器和左上角面板 |
| `test_design_viewer.py` | 测试：`python -m pytest design_viewer -q`（CPU；第一次约 30 s） |
