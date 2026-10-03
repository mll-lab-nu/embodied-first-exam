# design_viewer：用鼠标拖动谜题零件

在浏览器里打开 Hedgehog、Horseshoe、Slotted Post Ring 的场景，直接用鼠标拖动、旋转零件，体会谜题怎么解。场景由仓库的任务生成器（只读）生成，注册进 registry 的新变体会自动出现在场景列表里。

只用于理解谜题：这里的 MuJoCo 不是 simulator 的物理（simulator 只用 Genesis），看到的结果不是可解性证据，也不是成功标签。立柱场景里的绳用 MuJoCo cable 近似，与任务里的 FEM 绳不同。

## 启动

```bash
cd /home/pingyue/work/topogym/.claude/worktrees/topo        # worktree 根目录
conda activate topogym && export PYTHONNOUSERSITE=1
python -m design_viewer.view --scene hedgehog_in_cage_easy --port 18080
```

在 VS Code 的「端口」面板转发 18080，然后在浏览器打开 `http://localhost:18080/`。第一次打开要下载约 25 MB，页面会显示一会儿 “PARSING…”。服务只绑定 127.0.0.1，但本机其他用户也能连上这个端口；不用时按 Ctrl+C 关掉。

## 操作

| 操作 | 效果 |
|---|---|
| 双击零件 | 选中 |
| Ctrl + 右键拖动 | 拉动选中的零件（加 Shift：在水平面内拉） |
| Ctrl + 左键拖动 | 旋转选中的零件 |
| 左键拖动 / 右键拖动 / 滚轮 | 旋转视角 / 平移视角 / 缩放 |
| 空格；左侧 Reset | 暂停；回到初始状态 |
| 面板 “TopoGym” | 切换场景；把选中的零件固定在原地（相当于另一只手按住它），再拉别的零件 |

想看碰撞形状时，在左侧 Visibility Groups 里勾选 group 3。

## 文件

| 文件 | 作用 |
|---|---|
| `scenes.py` | 调用任务生成器，得到每个零件的显示网格和碰撞形状；结果缓存在 `.cache/`（git 忽略），生成器代码变了会自动重建 |
| `model.py` | 把场景转成 MuJoCo 模型；固定 / 取消固定零件 |
| `view.py` | 网页查看器和面板 |
| `test_design_viewer.py` | `python -m pytest design_viewer -q`（CPU；第一次约 30 s） |
