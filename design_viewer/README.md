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

## 操作（像游戏一样，画面右上角也有按键提示）

| 操作 | 效果 |
|---|---|
| 左键按住零件拖动 | 移动零件（加 Shift：在水平面内移动） |
| 右键按住零件拖动 | 旋转零件 |
| **G** | 按住 / 放开选中的零件。拖着的时候按 G，松开鼠标后零件仍停在原处，相当于第二只手 |
| **R** | 放开所有被按住的零件 |
| 在空白处或固定件上拖动 | 视角：左键旋转，右键平移；滚轮缩放 |
| 空格 / Backspace | 暂停 / 回到初始状态 |

右上角的下拉框用来切换场景，`held` 一行显示当前被按住的零件。再次拖动被按住的零件时，会自动放开它。想看碰撞形状时，在左侧 Visibility Groups 里勾选 group 3。

## 怎么实现的

- **场景**：调用仓库里的任务生成器（只读，与 Genesis 用的是同一套代码），得到每个零件的网格、碰撞形状和初始位姿。
- **物理**：把这些零件放进 MuJoCo，在服务器的 CPU 上计算，**不是 Genesis**。所以接触、摩擦等细节和任务不同。立柱场景里的绳用一串胶囊段近似（段与段之间是球关节，没有弯曲弹性），任务里是 FEM 绳。
- **网页和交互**：MuJoCo 3.14 自带的 Web Viewer。浏览器只负责显示和鼠标；拖动时，MuJoCo 在鼠标和零件之间加一根弹簧力。`view.py` 只改了它的鼠标和按键映射，并加了按键提示。

## 文件

| 文件 | 作用 |
|---|---|
| `scenes.py` | 调用任务生成器，得到零件的网格和碰撞形状；结果缓存在 `.cache/`（git 忽略），生成器代码变了会自动重建 |
| `model.py` | 把场景转成 MuJoCo 模型；按住 / 放开零件 |
| `view.py` | 网页查看器：游戏式鼠标、G/R 快捷键、右上角按键提示 |
| `test_design_viewer.py` | 测试：`python -m pytest design_viewer -q`（CPU；第一次约 30 s） |
