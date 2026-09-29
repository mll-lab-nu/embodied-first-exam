# Benchmark 实例配置

仅保存公开任务目标和固定 simulator 输入，不存凭据、模型参数或 runner 预算网关。

```bash
.venv-harbor/bin/python -m topogym.benchmark export \
  --instance-file configs/benchmark/cube_pick_place.yaml \
  --mode both --output runs/harbor_cube_25ms
```

文件可以是一个实例或实例列表。每项必须有 name、instruction、simulator；simulator 固定 seed，使用 JOINT_ABS、history_storage=disk、max_physics_steps=null。其他 SimulatorConfig 参数正常生效；不要填宿主绝对 asset_root/work_dir。

该 cube 配置保留旧方块实验的 25 ms 物理步、40 个 solver substeps、decimation 1，只更换 benchmark 接口/预算/深度设置。默认 catalog 导出采用库默认 2.5 ms、4 substeps、decimation 10；这两种配置不能混报为同一实例。13 项正式 family 和变体默认从 registry 枚举。
