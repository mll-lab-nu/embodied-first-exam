#!/bin/bash
# INSIDE the eai-robolab container: build the same Python stack as vast (isaacsim 5.1.0 pip + Isaac Lab
# f4aa17f source + torch 2.7.0 cu128 + lerobot v2.0 + pins) as /data/venv_vast, so ws replays match vast.
set -eux
cd /data
export UV_CACHE_DIR=/data/cache/uv
[ -d venv_vast ] || uv venv --seed --python 3.11 venv_vast
. venv_vast/bin/activate
uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
uv pip install "isaacsim[all,extscache]==5.1.0" --extra-index-url https://pypi.nvidia.com --index-strategy unsafe-best-match
[ -d deps/IsaacLab ] || git clone -q https://github.com/isaac-sim/IsaacLab.git deps/IsaacLab
(cd deps/IsaacLab && git checkout -q f4aa17f87e2e5db5484f0b5974918573e8918ce2 && TERM=xterm OMNI_KIT_ACCEPT_EULA=YES bash -c 'yes Yes | ./isaaclab.sh --install none')
uv pip install /work/lerobot "pyarrow==18.1.0" "datasets==3.6.0" imageio imageio-ffmpeg
uv pip install torch==2.7.0 torchvision==0.22.0 --index-url https://download.pytorch.org/whl/cu128
python -c "import torch, numpy; print('torch', torch.__version__, torch.cuda.is_available(), numpy.__version__)"
uv pip freeze > /data/venv_vast_freeze.txt
echo VASTSTACK_DONE
