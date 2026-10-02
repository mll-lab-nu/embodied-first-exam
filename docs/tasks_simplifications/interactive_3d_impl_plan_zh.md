# 交互式 3D 查看与拖拽工具：实施计划

日期：2026-10-02。用途：为三个任务的 `very_easy` / `easier` 设计提供直觉。读者：按本计划实现的 session。
状态：只做了可行性核查和 scratchpad 原型，**没有改动仓库代码**。下文数字均为本机实测，原型清单见附录。

## 0. 结论

- **推荐方案：** 使用 MuJoCo 3.14 自带的 experimental Web Viewer。浏览器端用 WASM/WebGL2 渲染，服务端在 CPU 上算物理。用户通过 VS Code 端口转发，在本地浏览器打开。场景用仓库生成器只读生成，再转成 MJCF。刺球的“这个朝向能否直拉出笼”“转多少度后能出”用 python-fcl 在精确网格上做运动学扫描，不依赖物理。
- **不用安装软件包，也不用 GPU。** 所需的 mujoco、coacd、python-fcl 都已在 topogym 环境中；原型进程峰值 RSS 约 200 MB。
- **唯一未验证的环节：** 浏览器端的鼠标交互。本机没有可用浏览器，所以第 0 步先做 30 分钟冒烟测试。若失败，经用户同意后改用方案 B。

## 1. 实测核查

### 1.1 环境

| 项 | 实测 | 结论 |
| --- | --- | --- |
| 显示 | `DISPLAY` 和 `WAYLAND_DISPLAY` 为空，`XDG_SESSION_TYPE=tty`，`SSH_CONNECTION=24.14.244.3 → 165.124.184.152:22`，存在 `VSCODE_IPC_HOOK_CLI`（VS Code Remote-SSH） | 这是远程会话，打不开桌面窗口 |
| X11 | sshd 配置了 `X11Forwarding yes`，但本会话没有转发。`/tmp/.X11-unix/X0` 属于本机 tty7 控制台登录（09-17 起） | 只有人在机房，或另开 `ssh -Y` 且本地有 X server 时才能用。GL 走 X 转发又慢又容易出问题，不作主方案 |
| 机器 | mll-4090-3：32 核，124 GB 内存（约 83 GB 可用）；GPU 被他人占用 | 全部在 CPU 上运行 |
| 端口 | 8011–8032、8791 等已被其他用户的服务占用（8791 上是别人的网页） | 显式指定端口，启动前先查 `ss -ltn \| grep :<port>` |
| Python | topogym 包没有安装进环境，只能从仓库根目录导入。在 `/tmp` 下运行时，游离的 `.py` 文件会遮蔽同名模块（实测报 `No module named 'nrd_dict'`） | 一律在 worktree 根目录执行 `python -m ...`，并设 `PYTHONNOUSERSITE=1` |

### 1.2 依赖（只检查，未安装）

| 包 | 状态 | 说明 |
| --- | --- | --- |
| mujoco 3.14.0 | 已装 | 包含 `mujoco.viewer`、`mujoco.experimental.studio`（Web Viewer：`web_client.wasm` 6.5 MB，WebGL2）和插件 `libelasticity.so`（cable）。主方案 |
| python-fcl 0.7.0.11 | 已装 | 精确网格的碰撞与扫描 |
| coacd | 已装 | 凹形笼体的凸分解（仅物理视图需要） |
| trimesh 5.1.0（不是 4.x）、manifold3d、shapely、scipy、rtree | 已装 | 生成器的依赖 |
| vtk 9.7.1、pyglet、PyOpenGL、glfw、plotly、node 20 | 已装 | 本方案不用 |
| viser | 未装 | 1.1.1 要求 `websockets<17`，而环境中是 17.1（mujoco 要求 ≥13，`requirements/difficulty-eval-runtime.lock` 锁定为 17.1）。装进 topogym 环境会降级 websockets，只能另建环境 |
| pyvista、vedo、open3d、trame、pyrender、vhacd、embreex、playwright | 未装 | 不需要 |
| 仓库自带的机器人 MJCF | `assets/robots/robotiq_2f85/2f85.xml`（Menagerie）、`assets/robots/aloha/aloha.xml` | 2F-85 已实测可以挂进场景 |

### 1.3 原型实测（`scratchpad/plan3d/`）

| 原型 | 结果 |
| --- | --- |
| `export_glb.py` | 9 个场景的 GLB 共 4.1 MB：刺球每个 0.12–0.17 MB，马蹄环 0.53 MB，立柱 0.72 MB。马蹄环、立柱构建 ≤0.5 s |
| `profile_hedgehog.py` | hedgehog easy：笼体有 718 个凸碰撞件；`build_assets` 耗时 24.7 s，其中 `choose_initial_pose` 占 24.2 s，**必须缓存** |
| `fcl_probe.py` / `exit_probe.py` | BVH collide 每次 0.007–0.15 ms，distance 每次 0.07–0.77 ms。扫 160 个方向的直拉耗时 0.1–0.3 s；绕 x/y/z 各 ±90°（步长 15°）的旋转扫描 ≤3 s。现有三档从初始位姿出发：直拉出口 0/160，单次绕世界轴旋转也打不开出口（与这三档“需要更多操作”的设计一致） |
| `positive_control.py` / `verify_exit.py` | 正对照：easy 模板 `window_widths` 从 20 改为 28（实际 60→84 mm）后，出口从 0 变为 43/160。改用视觉网格、0.5 mm 步长复核，结果相同。平均每次查询 8 µs（34 万次用时 2.9 s） |
| `mj_probe.py` | 刺球在 MuJoCo 中：easy 730 个 geom，每步 0.058 ms（dt 2 ms，34 倍实时）；medium 用 CoACD 分解（44 块），每步 0.029 ms（68 倍）。用焊接的“手”把球拖向墙：被挡住（滞后 49–58 mm），穿透 ≤2.8 mm |
| `mj_gripper.py` | 通过 MjSpec 挂上 2F-85 可行（20 个 body，85 个 geom），每步 0.10–0.16 ms（13–21 倍）。从窗口中心方位进入时不碰笼；从立柱方位（45°）进入时每一步都接触，在径向 164 mm 处被挡住 |
| `mj_horseshoe.py` | 三档均为 5 个自由体、417 个 geom（环用胶囊段，马蹄带用凸件），dt 1 ms 时每步 0.082–0.090 ms（11–12 倍）。2 s 静置漂移 ≤0.2 mm。1 s 内把目标环上提 15 cm，整组被带起，4 条链的 linking 不变（没有穿透） |
| `mj_slotted.py` / `mj_options.py` / `mj_timer.py` | cable 用 64 个顶点（每段 12.5 mm，总长 0.788 m）：2 s 内稳定、无 NaN，绳仍然只穿槽一次（x=1.2 mm，槽半宽 14 mm），回程在右侧立柱外（x=90 mm）。dt 1 ms 时每步 1.8–2.2 ms（0.5 倍实时）；dt 2 ms 加 pyramidal 时每步 1.87 ms（1.07 倍）。77% 的时间花在约束求解（每步 2.2 ms 中占 1.68 ms）；100 个接触中有 64 个是环与底座 |
| `mj_web.py` | Web Viewer 无窗口运行，绑定 127.0.0.1:18791：`/` 返回 200（“MuJoCo Web Viewer”），`/model` 返回 200（2.1 MB），`/web_client.wasm` 返回 200。45 s 内模拟时间 45 s；sync 调用 980 万次，即**忙等** |
| `coacd_sweep.py` | medium 笼体：threshold 0.05 / 0.03 / 0.02 分别得到 44 / 65 / 78 块，各用 4–5 s，最大鼓包 5.3 / 2.8 / 2.1 mm |

### 1.4 顺带发现（不在本工具范围内修，需告知用户）

1. **hard 初始位姿穿透。** 按 `HedgehogInCageHardTask.initial_ball_pose` 放置（数值与 medium 的类属性相同）后，球核（r=27 mm，中心在半径 34 mm 处）外缘到 61 mm，而笼内壁在 58.5 mm。凸件对凸件检查和视觉网格检查都判为相交，深度约 2.9 mm（碰撞件 104–107），抬高 16 mm 内仍然相交。Genesis 用的是同一批凸件，t=0 时球可能被弹开，需要在 Genesis 中确认。dev/jianwen 的 `docs/develop/tasks/hedgehog_in_cage_zh.md` 已记录同一问题（“hard 当前默认初态的球核与笼壁碰撞网格相交”），尚未修改默认初态。
2. **medium 资源目录有残留文件。** `build_waisted_cage` 解包 oblique_gate 资源包（含 328 个 `cage_collision_*.obj`）后，只重写了 `cage_collision_000.obj`。读碰撞件**必须按 `cage.urdf` 里的列表**，不能用 glob。
3. **`fcl.continuousCollide` 在 BVH 上不可靠。** easy 和 medium 都把直线向上的路径报成无碰撞，而 easy 顶部的孔太小，medium 顶部是封闭的。改用离散扫描，步长 ≤1.5 mm，小于最薄特征（刺 Ø10.8 mm，墙厚 8–9 mm）。
4. **MjSpec 的 weld 默认数据全为 0**（torquescale=0），实测焊接不起作用。必须显式传 `data=[0,0,0, 0,0,0, 1,0,0,0, 1]`。
5. **官方 Web Viewer 默认绑定 `::`**，即所有网卡，而本机有公网 IP。必须包一层，强制绑定 127.0.0.1（见 4.3）。

## 2. 方案取舍

| 方案 | 结论 | 依据 |
| --- | --- | --- |
| **A** MuJoCo Web Viewer，仓库生成器→MJCF，加 FCL 检查 | **推荐** | 不用安装；远程浏览器可用；自带选中、拖动（力扰动）、旋转、暂停和重力等物理选项；实测速度足够（刺球 13–68 倍，马蹄环 11 倍实时）；可以直接挂仓库自带的 2F-85 |
| B viser 网页 3D，加 FCL 自写“碰撞阻挡拖拽” | 备选（A 的冒烟测试失败时） | 需要单独建 conda 环境（原因见 1.2）。拖拽阻挡和多体被动运动都要自己写，代码量约为 A 的 2–3 倍 |
| C 静态 three.js 页面（claude.ai artifact 或本地 http.server） | 只作阶段 1 之后的可选“分享版” | GLB 共 4.1 MB，可以发布；但碰撞和物理要在 JS 里重写（three-mesh-bvh / Rapier），不能调用 Python 生成器，和 Python 检查逻辑重复 |
| D 桌面窗口：`mujoco.viewer`、pyvista、Open3D | 否 | 没有 DISPLAY；pyvista/open3d 未装；X 转发需另开 `ssh -Y`，GL 性能差。人在机房时可用 `view.py --native`（4.3） |
| E 在 Genesis 中交互 | 否 | 需要 GPU（已被占用），且 Genesis 没有现成的交互拖拽 |
| F trame / pyvista 远程 | 否 | 未安装，依赖多，也没有物理 |

## 3. 代码位置，以及与仓库规则的关系

```
scripts/design_viewer/          # 不放进 topogym/ 包；运行时代码不导入它
  __init__.py
  scenes.py          # 仓库生成器 → 场景描述（只读调用）+ 缓存
  mjcf.py            # 场景描述 → MjSpec；凸分解、夹爪/手、cable；--probe 自检
  view.py            # Web Viewer 启动器（回环绑定）+ 终端命令 + 状态行
  hedgehog_check.py  # FCL 运动学检查 CLI（直拉、单次旋转、出笼判定）
  status.py          # 阶段 3：马蹄环 linking、立柱穿绳判定
runs/design_viewer/...          # 缓存、位姿、检查报告（git 忽略）
```

| 规则（AGENTS.md / CLAUDE.md） | 本工具的做法 |
| --- | --- |
| “Genesis 唯一物理途径”；09-23 用户授权删除直接使用 MuJoCo 的实现 | 只作设计辅助：不进 simulator/rollout/评分链路，结果**不能**作为可解性证据、qualification 或成功标签。能否把 MuJoCo 代码放回仓库，由用户确认（未决 1） |
| 一次性脚本放仓库外；可复用的实现归入任务或共享模块 | 6 个新变体都会反复用到，默认放 `scripts/design_viewer/`。若用户不同意，把整个目录原样放到仓库外（如 `~/work/topogym_design_viewer/`），在 worktree 根目录用 `PYTHONPATH=.` 运行，不需改代码 |
| 并行会话边界：另一会话负责 `tasks/`、`assets/geometry/` 和材质 | 只读调用 `task_definition`、生成器和资源。设计候选用工具内的参数覆盖，不 patch 生成器 |
| 活动代码不导入 `legacy/` | 不导入 |
| demo 视频规则 | 工具不产出正式 demo。屏幕录像不放 `demos/`，也不算机器人执行 |
| 正在开发的任务不清理（Slotted Post Ring 受保护） | 只读其生成器 |
| 入口登记 | 在 `scripts/README.md` 新增一小节“设计辅助”，写入口和“非物理证据”声明 |

所有命令的公共前缀：

```bash
conda activate topogym
export PYTHONNOUSERSITE=1
cd /home/pingyue/work/topogym/.claude/worktrees/topo
```

## 4. 阶段 1：9 个现有场景可旋转查看（新增 6 个变体注册后自动出现）

### 4.0 冒烟测试（0.5 h，先做）

- 运行原型：`python /home/pingyue/work/topogym_design_viewer/prototypes_20261002/mj_web.py /home/pingyue/work/topogym_design_viewer/prototypes_20261002/mjcf/medium/scene.xml 18080 900`。若不能运行，先写 4.3 中最小版的 `view.py`。
- 在 VS Code 的“端口”面板转发 18080，然后在浏览器打开 `http://localhost:18080/`。
- 逐项检查：页面能加载；左键拖动旋转视角，滚轮缩放；**左键双击**选中刺球；**Ctrl+右键拖动**平移（加 Shift 为水平平移）；**Ctrl+左键拖动**旋转；空格暂停；能在 UI 里关重力；延迟主观可接受；用 `top` 看进程 CPU。macOS 上 Ctrl+点击会被当成右键，要专门试一下。
- 把结果记在本文末尾的“冒烟记录”。失败时停下来问用户是否改用方案 B。

### 4.1 `scenes.py`（0.5 d）

- 数据结构：`Scene(name, bodies, extras)`。每个 Body 包含：`name`、`fixed`、`pos/quat_wxyz`（桌面 z=0）、`visual`（trimesh）、`collision`（凸网格、胶囊、球、圆柱的列表）、`color`、`mass/inertia`。
- **hedgehog：** 调 `task_definition(...)(None, seed=0).build_assets(folder)`，得到视觉网格和 `report["initial_pose"]`。碰撞件按 `cage.urdf` / `hedgehog.urdf` 的 `<collision>` 列表读取（见 1.4 第 2 条），质量取 URDF 的 `<inertial>`。底座是一个 `mount_width×mount_width×mount_height` 的盒子，笼体原点的 z 为 `pad − cage_bottom`（与 `common.py` 中的 `declare` 一致）。medium 只有一个凹形碰撞件，标记为需要分解。
- **horseshoe：** 用 `HorseshoeAssembly(template=read_json(task.template_resource), scale)` 加上 `read_json(task.layout_resource)["poses"]`，body 原点取 `body.visual.center_mass`。碰撞：每个环用 `loop.points()` 和 `wire_radius` 拼成一圈胶囊，马蹄带用 `body.convex`。`assembly.loops/edges` 存进 extras，供阶段 3 使用。
- **slotted：** 调 `make_meshes(SlottedPostLayout(**task.config["geometry"]))`。底座和立柱固定；环、珠子、端盘先**全部固定，只供查看**，绳只作视觉，物理在阶段 3 再开。跳过 stop knot（与 `common.py` 一致）。
- **缓存：** key = sha256(variation_id、seed、`task.config` 的 JSON、任务模块、common.py、几何生成器源码字节、资源包字节)。写到 `runs/design_viewer/cache/<variation_id>/<key>/`。
- **新变体：** 注册后，`task_definition(task_id, f"{task_id}_very_easy")` 直接可用。注册前有两种方式：`--candidate pkg.module:function`（函数返回一个 Scene），或 hedgehog 专用的 `--template-set key=value`（覆盖经典模板，例如 `window_widths=28`）。
- **验证：** `python -m scripts.design_viewer.scenes --list` 输出 9 行，每行含 bodies、faces、碰撞件数和构建耗时。预期：hedgehog easy 718 / medium 1（凹）/ hard 611 个碰撞件；horseshoe 每档 5 个自由体；slotted 每档 8 个部件加绳。第二次运行 easy 的耗时应 <1 s（命中缓存）。加 `--export-glb` 时，文件大小应与 1.3 一致。

### 4.2 `mjcf.py`（0.5 d）

- 用 MjSpec 构建。视觉 geom 设 `group=1, contype=0, conaffinity=0`（凹形网格可以直接作视觉；只用 rgba 纯色，不带 GLB 纹理）。碰撞 geom 放在 `group=3`，默认隐藏，可以在 UI 里打开，检查近似程度。
- 桌面为平面，z=0。刚体场景 dt=2 ms，马蹄环 dt=1 ms；`integrator=implicitfast`；摩擦 0.3（与任务材料一致），`condim=3`；挂夹爪时 `impratio=10`（与 2F-85 一致，可消除 attach 冲突警告）。
- 凹形件用 CoACD 分解，`threshold=0.02`（medium 实测 78 块，最大鼓包 2.1 mm）。分解结果缓存，鼓包数值写进场景报告。
- `--probe settle|push|lift_ring` 自检。逐场景输出：编译耗时、ngeom、每步耗时、t=0 最大穿透、1 s 漂移。
- **验证：** `python -m scripts.design_viewer.mjcf --all --probe settle --seconds 1`。预期：刺球每步约 0.03–0.06 ms；马蹄环每步约 0.08–0.09 ms，漂移 ≤0.5 mm；**hard 报告 t=0 穿透约 2.9 mm**（已知问题，见 1.4 第 1 条），其余场景 t=0 穿透 ≤0.2 mm。

### 4.3 `view.py`（0.5 d）

- 关键包装。下面的写法已实测（若不包装，默认绑定所有网卡）：

```python
from mujoco.experimental.studio import launch_passive, messages, parser, step_control, viewer_app
from mujoco.experimental.studio import viewer_protocol as vp
from mujoco.experimental.studio.web import web_server
_bind = web_server.bind_public_socket
web_server.bind_public_socket = lambda host, port=0: _bind("127.0.0.1", port)
# data = parser.parse(path) 返回的是 MjData；model = data.model
with launch_passive.launch_passive(vp.ViewerConfig(gfx="web", http_port=port),
        viewer_plugins=[viewer_app.ViewerApp()], sim_plugins=[step_control.StepControl()]) as h:
    h.send_to_viewer(messages.ModelEvent(model=model, path=path))
    while h.is_running():
        model, data = h.sync(model, data); time.sleep(0.002)  # 实测不 sleep 会单核忙等
```

- 命令行：`python -m scripts.design_viewer.view --task hedgehog_in_cage --variant easy --port 18080`。`--native` 在有 DISPLAY 时改用 `mujoco.viewer.launch_passive`，场景代码相同。
- 终端命令（在 stdin 线程里读入，放进队列，由 sim 循环处理）：`l` 列出场景；`v <variant>` 切换场景（发送 ModelEvent 后浏览器自动刷新，日志里已出现 “Model changed: the browser page reloads automatically.”）；`k` 重置；`q` 退出。暂停状态由浏览器 UI 控制，sim 端改不了，所以说明里写“按空格暂停”。
- 启动横幅中的 “Remote: http://mll-4090-3:…” 是固定文案，不代表实际绑定的地址，忽略即可。
- **验证：** `ss -ltn | grep :18080` 只显示 `127.0.0.1:18080`；`curl -s localhost:18080/ | grep -o '<title>[^<]*'` 输出 `MuJoCo Web Viewer`；`curl -o /dev/null -w '%{http_code}' localhost:18080/model` 输出 200；加 sleep 后 `top` 显示占用不到 0.5 个核。在浏览器里用 `v` 逐个切换 9 个场景，确认都正常。

### 4.4 收尾（0.25 d）

- 在 `scripts/README.md` 登记入口。用 `--candidate` 写一个示例：hedgehog easy，窗口宽 28，确认能显示。

## 5. 阶段 2：刺球交互求解

### 5.1 夹爪体积与抓持（0.5 d）

- 加 `--gripper robotiq`：建一个自由 body `wrist`（`gravcomp=1`，自由关节加阻尼，松手后会停住），用 `wrist.add_frame().attach_body(spec_2f85.worldbody.first_body(), "g_", "")` 挂上 `assets/robots/robotiq_2f85/2f85.xml`（已实测）。
- **用力扰动驱动 wrist，不用 mocap。** 读代码可知，浏览器端只把 `xfrc_applied` 回传给 sim（`viewer_utils.apply_perturb`）；浏览器端改 mocap 位姿很可能不会生效。反过来，sim 端改 mocap 或 `eq_active` 会随状态广播到浏览器。
- 抓持有两种方式。一是用 UI 的执行器滑条（0–255）合拢手指：控件修改走 StateEvent 回传，需在冒烟测试中确认。二是在终端输入 `g`：按当前相对位姿把球焊到 wrist，对应任务中 `contact_weld_v1` 的辅助抓持概念。实现方法是在 sim 端写 `model.eq_data`（relpose，torquescale=1），再设 `data.eq_active`。
- 另有 `--no-gripper` 模式，可以直接拖球。
- **验证：** `python -m scripts.design_viewer.mjcf --task hedgehog_in_cage --variant medium --gripper robotiq --probe push --azimuth 0|45` 应复现原型结果：0° 时夹爪与笼的接触为 0 步；45° 时每一步都接触，在径向约 164 mm 处被挡住。

### 5.2 `hedgehog_check.py`（1 d）

- **几何：** 笼体用 FCL BVH，碰撞件精确（凹形也可以，不需要 CoACD）；球用其碰撞件的 BVH。可选夹爪：从保存的位姿中读出 wrist 和手指的 qpos，经 MuJoCo forward 得到 2F-85 碰撞 geom，转成球坐标系下的 FCL 凸件，与球刚性连在一起。可选腕部代理：Ø80 mm×150 mm 圆柱，沿接近方向（未决 3）。
- **查询：**
  - `straight`：160 个 Fibonacci 方向（仰角 −12°…90°）。另加 `lift_then_pull`：先抬高 h（0–80 mm，步长 2 mm），再沿 72 个水平方位拉出。离散步长 1.5 mm。
  - `rotate`：有夹爪时，绕接近轴、指间轴和掌法向旋转；无夹爪时绕世界 x/y/z。θ 取 −180°…180°，步长 5°；旋转过程每 2° 检查一次碰撞；可以在若干抬高高度上旋转；转完后再跑一次 `straight`。输出能打开出口的最小 |θ| 和对应的出口方向。
  - `exit`：球（以及夹爪）的所有顶点都在笼体凸包外扩 5 mm 的范围以外，判为出笼。
- **标签：** 夹爪在初始抓持下即有出口，判 `very_easy_ok`；初始朝向没有出口，但存在 |θ|≤θmax 且旋转路径无碰撞的出口，判 `easier_ok`；若一个 easier 候选本身已有直拉出口，要报警。起始位姿若与笼相交，直接报告“start in collision”加穿透深度，不再继续扫描（hard 就会出现这种情况）。
- **输出：** 一行摘要，加 `runs/design_viewer/hedgehog_in_cage/<name>/check_<time>.json`。
- **验证**（需与原型一致）：
  - `--variant easy|medium` 只检查球：直拉 0/160；绕 x/y/z 各 ±90°（步长 15°）都打不开出口。
  - `--variant hard`：报告 start in collision，约 2.9 mm。
  - `--template-set window_widths=28`：43/160（`choose_initial_pose` 用固定 seed 17，结果应完全相同）。`window_widths=20`：0/160。
  - 耗时：每次查询约 8 µs；`straight` 0.1–0.3 s；完整的 `rotate` 预计 3–15 s。

### 5.3 接入 viewer（0.5 d）

- `c`：从 sim 的 `data` 读出当前球、wrist 和手指的位姿，运行 5.2 的 `straight`（`c+` 时同时跑 `rotate`），在终端打印摘要。把一个只作显示的 mocap 箭头放到最佳出口方向（由 sim 端写入，浏览器能看到）。
- 状态行每 0.5 s 刷新一次：`inside / partly out / OUT`（5.2 的 exit 判定）、夹爪与笼的接触数、`data.contact.dist` 的最大穿透。
- `s <name>` / `o <name>`：把 qpos、`eq_active`、weld 的 relpose 和 ctrl 保存到 `runs/design_viewer/poses/<scene>/<name>.json`，或从中读回。这些文件可以作为 5.2 的 `--pose` 输入。
- **验证：** 在 medium 中把夹爪伸进窗口抓球后，`c` 的结果应与 `hedgehog_check --pose <保存的文件>` 一致；`s` 后再 `o`，位姿误差 <1e-6。

### 5.4 新变体设计循环（0.5 d）

- 参数扫描：`python -m scripts.design_viewer.hedgehog_check --sweep window_widths=20:36:2 --grasp default`，输出参数与 very_easy/easier 标签的对照表。`--grasp default` 表示夹爪水平穿过最近的窗口夹球核。
- 选好的候选用 `view.py --candidate` 实际拖一遍。正式变体按 `two_levels_below_easy_plan_20261001_zh.md` 实现，本工具不写入任务源码。

## 6. 阶段 3：马蹄环与长孔立柱

### 6.1 马蹄环（1 d）

- 场景沿用 4.1，dt 1 ms，5 个自由体。增加两只“手”：自由 body，`gravcomp=1` 加阻尼，形状用小球或指块。终端命令 `g L <body>` / `g R <body>` 按当前相对位姿焊接，`r L|R` 松开。松开后手原地停住，所以可以一只手“按住”马蹄，另一只手去拖。
- `status.py`：直接复用仓库的 `Loop.linking`（与 `common.py` 中 `evaluate_goal_region` 相同）。4 条链的 linking 应保持 ±1；同时计算目标环与各环的 linking。取下判定：环与所有环的 linking 都为 0，且与其他物体的最小距离 >10 mm。
- **验证：** `python -m scripts.design_viewer.mjcf --task horseshoe_ring --all-tiers --probe lift_ring` 应复现原型：2 s 漂移 ≤0.2 mm；上提 15 cm 时整组被带起；linking 不变。然后在浏览器里试着把环取下来。
- **难点：** 多体互扣完全依赖接触求解。力扰动一次只能选一个物体，所以双手操作要靠焊接流程。接触参数与 Genesis 不同，卡住或滑脱的阈值不能直接搬过去用。ALOHA 是否够得着不在本工具范围内。

### 6.2 长孔立柱（1.5–2 d）

- **绳：** 用 MuJoCo cable（`composite type="cable"`，插件 `mujoco.elasticity.cable`）。顶点由 `centerline(layout)` 重采样得到；两端用 `connect` 连到端盘，对应 Genesis 中绳端与端盘的永久连接。
- **刚体：** 珠子用 12 个扇区凸包，保留孔道（孔半径 4.5 mm，绳半径 3.5 mm；凸包弦高约 0.34 mm）。立柱：CoACD threshold 0.03 实测 8 块、1.3 s，但要像 `coacd_sweep.py` 那样检查长孔被鼓包缩窄了多少；不合格就改用解析分块（两侧立柱条、上下两块、圆端几块）。环用胶囊圈，从 32 段减到 16–24 段，以减少环与底座的接触（实测 100 个接触里占 64 个）。
- **调参目标：** 至少 1 倍实时。可调的有：顶点数 40–64、dt 2 ms、pyramidal（实测 N=64、dt 2 ms 时为 1.07 倍）。bend/twist 刚度只求定性合理。
- **状态：** 统计 cable 折线穿过环所在圆盘的带符号次数，以及立柱中心线是否穿过该圆盘。两者都为 0，且环在立柱包围盒之外，判为“环已脱出”。
- **验证：** `--probe settle` 应满足：无 NaN；环和端盘漂移在数 mm 以内；绳在槽内（|x|<14 mm）恰好穿过 y=0 一次，在右侧立柱外（x>40 mm）再穿过一次。原型实测为 1.2 mm 和 90.4 mm。

### 6.3 不建议做

- 调 cable 参数去拟合 Genesis 的 FEM/IPC（v13 材料、soft50）；用工具结果判断绳的摩擦或夹持能否成功；在没有接触的情况下用运动学方式拖绳的控制点。
- 自写 JS 前端（除非方案 A 的冒烟测试失败）。
- 整条 Panda / ALOHA 手臂加 IK 拖拽：这部分交给 Genesis 和 `topogym/planning/`。
- 把 MuJoCo 结果写进 `solvability_proof/`、qualification 或 `demos/`。
- 在 viewer 里暂停后拖动位姿：读代码可知，暂停时的位姿编辑只改浏览器端，不会回传 sim。

## 7. 风险与限制

| 风险 | 影响 | 处置 |
| --- | --- | --- |
| 交互物理与 Genesis 不等价：软接触（拖进墙时穿透 ≤2.8 mm）、凸分解鼓包（≤2.1 mm）、求解器和摩擦实现不同；cable 不等于 FEM | 结论只能当直觉和设计草图 | 每份报告都写明“非物理证据”。最终以 Genesis 加机器人真实执行验证，各类验证结果分开记录 |
| FCL 检查只是几何：不含夹爪动力学、IK 和可达性 | 可能高估可行性 | 加入夹爪体积和可选腕部代理；最终仍需 IK 和执行验证 |
| Web Viewer 处于 experimental 阶段 | mujoco 升级后 API 可能变化 | 只依赖 `launch_passive`、`ViewerHandle`、`messages` 和 `web_server.bind_public_socket`；报告里记录 mujoco 3.14.0 |
| 浏览器端未在本机测过；macOS 上 Ctrl+点击会变右键 | 拖拽可能用不了 | 按 4.0 冒烟测试；失败则改用方案 B |
| 同一时间只有一个浏览器能控制 | 多人不能同时操作 | 其他人只能旁观（spectator） |
| 安全 | 默认会暴露到公网 | 强制绑定回环地址；不要用官方 CLI 直接启动 |
| CPU 忙等、端口冲突 | 抢占共享机器的资源 | 循环中 sleep；显式指定端口并先检查 |
| hedgehog easy 构建需要 25 s | 切换场景慢 | 缓存 |
| hard 初始穿透 | 开局时球会被弹开 | 工具只报告，不修；交给用户或负责几何的会话 |

## 8. 未决问题（需用户决定）

1. 能否把 MuJoCo 代码放在 `scripts/design_viewer/`？这涉及“Genesis 唯一物理途径”和 09-23 删除 MuJoCo 实现的授权。若不行，就放到仓库外。
2. 冒烟测试失败时，是否同意方案 B（新建一个装 viser 的 conda 环境）？
3. 夹爪体积是否要包括 Panda 腕部或法兰代理？默认只算 2F-85。
4. easier 中“转一下”的定义：允许绕哪些轴转、最大转多少度？默认接近轴 roll ±180°，指间轴 ±90°。
5. hard 初始穿透是否交给负责几何的会话处理？
6. 阶段 1 完成后，是否发布 claude.ai artifact 分享版（GLB 共 4.1 MB）？

## 附录：原型清单

目录：`/home/pingyue/work/topogym_design_viewer/prototypes_20261002/`（仓库外，从原会话 scratchpad 复制而来，场景文件中的网格路径已改到这里）。**只照搬其中的逻辑，不要导入它们**。

`export_glb.py`、`profile_hedgehog.py`、`fcl_probe.py`（`load()`：按 URDF 列表读碰撞件）、`exit_probe.py`、`positive_control.py`、`verify_exit.py`、`hard_overlap.py`、`hard_core.py`、`mj_probe.py`、`mj_gripper.py`、`mj_horseshoe.py`、`mj_slotted.py`、`mj_options.py`、`mj_timer.py`、`mj_web.py`、`coacd_fidelity.py`、`coacd_sweep.py`；生成的 MJCF 在 `mjcf/`（GLB 未复制，可用 `export_glb.py` 重新生成）。另有 CPU 渲染脚本 `render_tiers.py`（说明页三档渲染图的来源）。

## 冒烟记录（执行 4.0 后填写）

- 日期 / 浏览器 / 本地操作系统：2026-10-02；本机 Firefox 156（snap），运行在私有 Xvfb :87 上，WebGL2 用 llvmpipe 软件渲染，由 geckodriver（W3C WebDriver）驱动。headless 模式下拿不到 WebGL。用户本地浏览器经 VS Code 端口转发、以及 macOS 上 Ctrl+点击的情况，尚未测试。
- 加载、旋转、选中、Ctrl+拖动、旋转扰动、暂停、关重力：页面、模型和 TopoGym 面板能加载；面板按钮、场景下拉切换（页面自动重载）、双击选中（面板显示 `selected: g_base` / `target_ring`）、Ctrl+右键拖动夹爪和马蹄环都有效；FCL 结果在浏览器中显示为绿色箭头。WebDriver 测试时要先移动鼠标、再原地双击，否则这次移动会被当成拖动、改变视角。暂停和关重力未单独测试。
- 延迟和 CPU：hedgehog medium 空闲时 0.07 核（OpenBLAS 限为 1 个线程；不限时 11 个线程空转，共 1.35 核）。slotted 连上浏览器后约 1.0 核（cable 按实时速度计算）。`/model` 大小：hedgehog 15–17 MB，horseshoe 7 MB，slotted 10 MB。
- 结论（继续 A / 改用 B）：继续 A。实现见 `scripts/design_viewer/`，入口登记在 `scripts/README.md` 的“设计辅助”一节。
