#!/bin/bash
# Inside the container: add missing pure-python deps of yamlab/lerobot to /data/pylib (--no-deps), one at a time.
declare -A MAP=( [jsonlines]=jsonlines [einops]=einops [imageio]="imageio[ffmpeg]" [av]=av [draccus]="draccus==0.10.0" [termcolor]=termcolor [deepdiff]=deepdiff [omegaconf]=omegaconf [zarr]=zarr [h5py]=h5py [pymunk]=pymunk [diffusers]=diffusers [wandb]=wandb [rerun]=rerun-sdk [cv2]=opencv-python-headless [torchcodec]=torchcodec [yaml]=pyyaml [toml]=toml [hydra]=hydra-core [mergedeep]=mergedeep [typing_inspect]=typing-inspect [mypy_extensions]=mypy-extensions [pyrallis]=pyrallis [portal]=portal [open3d]=open3d [orderly_set]=orderly-set )
for i in $(seq 1 25); do
  M=$(PYTHONPATH=/data/pylib:/work/yamlab python -c "
import importlib
for m in ['lerobot.common.datasets.lerobot_dataset','yamlab.configs','yamlab.utils.recorders']:
    try: importlib.import_module(m)
    except ModuleNotFoundError as e: print(e.name.split('.')[0]); break
    except Exception as e: print('ERR', repr(e)[:200]); break
" 2>/dev/null | tail -1)
  [ -z "$M" ] && { echo IMPORTS_OK; break; }
  case "$M" in ERR*) echo "$M"; break;; esac
  P=${MAP[$M]:-$M}; echo "installing $P for $M"
  uv pip install --python /opt/robolab/.venv/bin/python --target /data/pylib --no-deps "$P" 2>&1 | tail -1
done
