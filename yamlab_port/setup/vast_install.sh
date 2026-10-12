#!/bin/bash
# Native (docker-free) YAMLab install on the vast box, all under /workspace/yamlab_port.
# Mirrors yamlab/install.sh (Option B) with a uv venv instead of conda and no sudo/apt.
set -eux
R=/workspace/yamlab_port
cd $R
export UV_CACHE_DIR=$R/.uv_cache PIP_CACHE_DIR=$R/.pip_cache
[ -d yamlab ] || git clone https://github.com/ARISE-Initiative/yamlab yamlab
(cd yamlab && git checkout ec0455d2b4ce35f21fc126418ea5e74ac567133d)
[ -d venv ] || uv venv --seed --python /.uv/python_install/cpython-3.11-linux-x86_64-gnu/bin/python3.11 venv
. venv/bin/activate
uv pip install --upgrade pip
uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install -e yamlab
mkdir -p deps
[ -d deps/lerobot ] || GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/RogerDAI1217/lerobot.git deps/lerobot
(cd deps/lerobot && git checkout lerobotv2.0 && uv pip install -e .)
uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match
[ -d deps/IsaacLab ] || git clone https://github.com/isaac-sim/IsaacLab.git deps/IsaacLab
cd deps/IsaacLab && git checkout f4aa17f87e2e5db5484f0b5974918573e8918ce2
export OMNI_KIT_ACCEPT_EULA=YES TERM=xterm
yes Yes | ./isaaclab.sh --install none
cd $R
uv pip install -e yamlab/joylo || true
uv pip install coacd pymeshlab usd-core open3d portal || true
# pins found by the smoke test (Isaac needs numpy 1.26; newer pyarrow/datasets need numpy 2 / newer hub)
uv pip install "pyarrow==18.1.0" "datasets==3.6.0"
# user-space system libs + env.sh: run vast_syslibs.sh after this script
# re-pin torch in case a dependency moved it
uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
python -c "import torch; print('torch', torch.__version__, torch.cuda.is_available())"
echo INSTALL_DONE
