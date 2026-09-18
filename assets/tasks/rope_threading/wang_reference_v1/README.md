# 绳穿三环：Wang 公开初态

来源：[演示](https://qinengwang-aiden.github.io/demos/constraint_demos/?demo=threading)、
[方法](https://qinengwang-aiden.github.io/demos/constraint_demos/methods.html)。
公开页面的项目许可副本保留在 `LICENSE`；本目录不包含其他任务的第三方谜题几何。

`reference.json` 从公开 `geometry.json`、`manifest.json` 与 `phase-000.bin` 第一帧提取；
记录三个来源的 URL 和 SHA-256，并校验下载二进制及所用数组的哈希。
其中 81 个节点按原始绳子材料方向排列。三环的有向法线沿用项目参数卡的约定，
用公开胶囊端点检查所在平面和半径。没有下载或使用后续执行轨迹。

`model/` 是可离线使用的 OBJ、GLB、中心线和参数清单。
单位为米，Z 轴向上；桌面顶面为 z=0：原坐标整体增加 `[0, 0, 0.0009]`。
GLB 仅包含任务物体，完整实验室与机器人由场景构建器加载。
支架接环侧面，三个底座底面与桌面齐平；不要把整个环做凸包，否则会封住通孔。

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.prepare_assets
.venv-gs121-nyx/bin/python -m demos.environment_bootstrap.rope_threading
```

重新提取公开参考数据（自行下载上述三个文件后）：

```bash
.venv-gs121-nyx/bin/python -m topogym.tasks.rope_threading.reference \
  --geometry /path/to/geometry.json --manifest /path/to/manifest.json \
  --phase /path/to/phase-000.bin
```

当前环碰撞是闭合非凸三角网格；相对原 64 段胶囊并集的保守离散误差界约 0.142 mm。
绳子迁入 FEM+IPC，原 80 段中心线细分为 320 段，两端封口但不固定，材料参考态为直绳。
端面采用平封口，原胶囊绳采用半球端；这是明确的后端建模差异。
资产与首帧建模完成不代表已完成机器人穿环。
