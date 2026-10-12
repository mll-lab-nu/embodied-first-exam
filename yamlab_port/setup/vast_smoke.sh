#!/bin/bash
# Smoke test: headless YAMLab PutPotOnCooktop eval benchmark (2 envs, no cameras) on vast.
set -eux
R=/workspace/yamlab_port
. $R/env.sh
cd $R
[ -d yamlab_datasets/tasks_data/PutPotOnCooktop/objects ] || python yamlab/scripts/download_data.py --task PutPotOnCooktop --parts objects --local-dir $R/yamlab_datasets
O=$R/yamlab_datasets/tasks_data/PutPotOnCooktop/objects
ls $O; find $O -maxdepth 2 | head -20
POT=$(find $O -mindepth 2 -maxdepth 2 -type d | grep -i pot | head -1)
COOK=$(find $O -mindepth 2 -maxdepth 2 -type d | grep -i cook | head -1)
cd yamlab
export PYTHONPATH=$R/yamlab
python -c "import yamlab; print('YAMLAB_FROM', yamlab.__file__)"
time python scripts/benchmark_eval_throughput.py --task PutPotOnCooktop-v0 --asset pot=$POT --asset cooktop=$COOK --num_envs 2 --observation_modalities rgb,proprioception --camera_width 320 --camera_height 240 --image_downsample_factor 1 --enable_cameras --headless
echo SMOKE_DONE
