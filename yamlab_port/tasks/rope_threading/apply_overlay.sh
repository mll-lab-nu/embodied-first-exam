#!/bin/bash
# (on vast) add the registration lines to our yamlab copy, idempotently. Overlay files are rsynced by sync.sh.
Y=/workspace/yamlab_port/runs/rope_threading/yamlab/yamlab
grep -q rope_threading_manager_cfg $Y/envs/tasks/__init__.py || printf 'from .rope_threading_manager_cfg import *\nfrom .rope_threading_manager import *\n' >> $Y/envs/tasks/__init__.py
grep -q RopeThreading $Y/envs/robot_registry.py || sed -i 's/^    "HangMugOnTree-Mimic-v0": "yam",/    "HangMugOnTree-Mimic-v0": "yam",\n    "RopeThreading-Easy-v0": "yam",\n    "RopeThreading-Medium-v0": "yam",/' $Y/envs/robot_registry.py
grep -n "rope_threading\|RopeThreading" $Y/envs/tasks/__init__.py $Y/envs/robot_registry.py
