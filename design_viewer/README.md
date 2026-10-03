# design_viewer：用鼠标拖动谜题零件

在浏览器里打开 Hedgehog、Horseshoe、Slotted Post Ring 的场景，用鼠标直接拖动、旋转零件，看清谜题怎么解。

**它不是什么**：物理用的是 MuJoCo 近似，不是 simulator 使用的 Genesis。这里看到的结果不能作为可解性证据，也不能作为成功标签。

## 启动

在仓库根目录、装好 TopoGym 依赖的 Python 环境里运行。除 TopoGym 本身的依赖外，还需要：

- `mujoco` ≥ 3.14：要用到它自带的 Web Viewer `mujoco.experimental.studio`，在 3.14.0 上测试过；
- `coacd`：只有含凹形碰撞件的场景（如 hedgehog medium）会用到。

```bash
python -m design_viewer.view --scene hedgehog_in_cage_easy --port 18080
```

然后在浏览器打开 `http://localhost:18080/`。在远程机器上运行时，先把端口转发到本地，例如 `ssh -L 18080:localhost:18080 <远程主机>`，或者用 VS Code 的端口转发。第一次打开要下载约 25 MB，会先显示一会儿 “PARSING…”。用完在终端按 Ctrl+C 关掉。

- 同一时间只能有一个浏览器页面控制，其他页面显示 SPECTATING。出现 SPECTATING 时，关掉其他 18080 页面即可。
- 服务只监听本机，但本机的其他用户也能连上这个端口。

## 操作（画面右上角有同样的按键提示）

| 操作 | 效果 |
|---|---|
| 左键按住零件拖动 | 移动零件；加 Shift 只在水平面内移动 |
| 右键按住零件拖动 | 旋转零件 |
| **G** | 按住 / 放开当前零件：拖着零件按 G，松开鼠标后零件停在原处，相当于第二只手 |
| **R** | 放开所有被按住的零件 |
| 在空白处或固定件上拖动、滚轮 | 转动视角（左键旋转，右键平移），滚轮缩放 |
| 空格 / Backspace | 暂停 / 回到初始状态 |

鼠标拉力最多 30 N。零件被卡住时会停在原处，不会被甩飞或拉穿其他零件。

## 场景从哪里来

右上角下拉框列出三个任务在 registry 里所有已接入的变体，包括 `very_easy` 和 `easier`。新变体注册后，这里会自动出现。

场景几何由任务代码生成：刺球调用 `build_assets`，马蹄环调用 `template()` 和 `rest_poses()`，立柱调用 `make_layout()`。查看器只读调用这些代码，不修改任务。零件名称、固定还是可动、初始位姿都与任务的 `declare()` 一致，有测试检查。

结果缓存在 `design_viewer/.cache/`（git 忽略）。任务代码改动后，缓存会自动重建。

## 怎么实现的

- **场景**：上述任务代码给出每个零件的网格、碰撞形状和初始位姿，与 Genesis 使用的相同。
- **物理**：MuJoCo 在 CPU 上计算。立柱的 FEM 绳近似成一串胶囊段，段与段之间是球关节，两端保留任务里的绳结。
- **网页**：MuJoCo 3.14 自带的 Web Viewer。`view.py` 只替换了鼠标和按键的映射，并加了按键提示。

| 文件 | 作用 |
|---|---|
| `scenes.py` | 任务代码 → 零件网格和碰撞形状（带缓存） |
| `model.py` | 零件 → MuJoCo 模型；按住 / 放开零件 |
| `view.py` | 网页查看器、鼠标和按键 |
| `test_design_viewer.py` | 测试 |

## 测试

```bash
python -m pytest design_viewer -q   # 在仓库根目录运行；CPU；约 2 分钟
```

测试检查以下内容：

- 场景与任务的 `declare()` 一致；
- 开局没有穿透；
- 鼠标能拖动、旋转零件，G 能按住零件；
- 立柱场景：珠子留在绳上；猛拉环不会穿过绳；只有 very_easy 的环能被直接提出。
