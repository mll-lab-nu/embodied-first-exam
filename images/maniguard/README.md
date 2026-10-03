# eai-maniguard: ManiGuard on BEHAVIOR-1K 3.7.2 / Isaac Sim 4.5

`eai-maniguard:0.1.0` (`VERSION`) runs ManiGuard's evaluator on exactly the stack ManiGuard pins: its `behavior-1k`
submodule is BEHAVIOR-1K tag **v3.7.2** (`88454bd04f75`), installed the way that release's `setup.sh` installs it. It is
NOT the BEHAVIOR-1K 3.9.2 stack of `eai-behavior` (Isaac Sim 5.1): ManiGuard's frozen scenes are 3.7.2 snapshots, its
runtime patches target 3.7.2, and upstream abandoned its own port to a newer Isaac.

| | |
|---|---|
| Base | `nvidia/cuda:12.4.1-base-ubuntu22.04` by digest (`sha256:0f6bfcbf…`, 91.8 MB compressed) |
| System | Ubuntu 22.04 packages from the archive snapshot of 2026-10-01 (Isaac Sim's X / Vulkan / EGL libraries); NVIDIA Vulkan and EGL loader entries |
| Python | Miniforge 26.7.2-0 (sha256-checked), conda env `behavior`: Python 3.10.21 (conda-forge) |
| PyTorch | torch 2.6.0, torchvision 0.21.0, torchaudio 2.6.0, CUDA 12.4 wheels (setup.sh's default) |
| BEHAVIOR-1K | v3.7.2 sparse checkout (`OmniGibson/`, `bddl3/`), editable installs: OmniGibson 3.7.2, bddl 3.7.0 (no extras) |
| Isaac Sim | the 26 `4.5.0.0` wheels setup.sh installs (`omniverse_kit-106.5.0.162521` + `isaacsim_*`), each checked against `isaacsim-4.5.0.0.sha256`; setup.sh's websockets fix and `cffi==1.17.1` |
| conda-forge | PyAV 16.0.1 (setup.sh's `--eval` step), Spot 2.16 (ManiGuard's LTL monitor; "do NOT pip install spot") |
| ManiGuard | `NU-IDEAS-Lab/ManiGuard@a1b6444b3`, only `maniguard-keep.txt` (the evaluator's import closure, 37 modules, + `configs/eval/`), on the env's path via `maniguard.pth` |
| Data | none; `/data` is the read-only mount of `$RCB_MANIGUARD_DATA` (`OMNIGIBSON_DATA_PATH=/data`) |
| Caches | Kit's caches and OmniGibson's appdata under `/cache` (a task mounts a volume of its trial there) |

## What is left out, and why
BEHAVIOR-1K's `setup.sh` as ManiGuard's install guide runs it adds `--joylo --eval --primitives`. Nothing in ManiGuard's
evaluator imports them (checked over the evaluator's whole import closure, also function-level imports): cuRobo and OMPL
(`--primitives`, ManiGuard's data generator plans with them), JoyLo (teleoperation), and `--eval`'s lerobot, open3d, hydra
and torch-cluster (BEHAVIOR's challenge evaluator). PyAV, the one `--eval` package the closure imports, is installed. Leaving
them out keeps the simulator stack identical (Isaac Sim, OmniGibson, bddl, torch, numpy < 2) and the image smaller.

ManiGuard's data generator, its scripted skeletons, grasp annotations, policy servers and SFT code are not copied: they
encode or point to reference solutions, which must not be in reach of an agent (PROTOCOL §2.7).

## Locks
The first tested build writes `/opt/locks/{dpkg,conda,pip}.lock` in the image; they are committed here as `dpkg.lock`,
`conda.lock` and `pip.lock`, after which a build fails unless it installs exactly those sets (as `eai-behavior`'s
`dpkg.lock`). Until then the pins are the ones in the Dockerfile.

## Check a build
```bash
img=ghcr.io/embodied-agent-interface-v2-internal/eai-maniguard:$(cat images/maniguard/VERSION)
docker run --rm $img python -c "import omnigibson, maniguard.eval.benchmark; print(omnigibson.__version__)"     # 3.7.2
for l in dpkg conda pip; do docker run --rm $img cat /opt/locks/$l.lock | diff - images/maniguard/$l.lock; done      # once committed
# a frozen instance loads with the long-finger robot and to its recorded state hash (GPU, the data root):
docker run --rm --gpus all --shm-size 8g -v "$RCB_MANIGUARD_DATA:/data:ro" -v $PWD/scripts/maniguard:/m:ro $img \
  python /m/shared/rcb_maniguard.py make-instance --task jar_transport/task_0014 --instance /m/instances/jar_transport/task_0014 --out /tmp/i.json
```

## Not published: build it (`BUILD_ONLY`)
NVIDIA Isaac Sim inside (no redistribution). `BUILD_ONLY` has the build command, what the builder accepts, the data it needs
and the host requirements.
