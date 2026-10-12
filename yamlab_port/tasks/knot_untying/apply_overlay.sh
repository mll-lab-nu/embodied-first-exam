#!/bin/bash
# (on vast) add the registration lines to our yamlab copy, idempotently. Overlay files are rsynced by sync.sh.
Y=/workspace/yamlab_port/runs/knot_untying/yamlab/yamlab
grep -q knot_untying_manager_cfg $Y/envs/tasks/__init__.py || printf 'from .knot_untying_manager_cfg import *\nfrom .knot_untying_manager import *\n' >> $Y/envs/tasks/__init__.py
grep -q KnotUntying $Y/envs/robot_registry.py || sed -i 's/^    "HangMugOnTree-Mimic-v0": "yam",/    "HangMugOnTree-Mimic-v0": "yam",\n    "KnotUntying-VeryEasy-v0": "yam",\n    "KnotUntying-Easier-v0": "yam",/' $Y/envs/robot_registry.py
grep -q KnotUntying-Easy-v0 $Y/envs/robot_registry.py || sed -i 's/^    "KnotUntying-Easier-v0": "yam",/    "KnotUntying-Easier-v0": "yam",\n    "KnotUntying-Easy-v0": "yam",\n    "KnotUntying-Medium-v0": "yam",/' $Y/envs/robot_registry.py
grep -n "knot\|Knot" $Y/envs/tasks/__init__.py $Y/envs/robot_registry.py
