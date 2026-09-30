import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import argparse
from mw_runtime import replay
p=argparse.ArgumentParser();p.add_argument('--instance',required=True);p.add_argument('--trajectory',required=True);p.add_argument('--output',required=True);a=p.parse_args()
replay(a.instance,a.trajectory,a.output)
