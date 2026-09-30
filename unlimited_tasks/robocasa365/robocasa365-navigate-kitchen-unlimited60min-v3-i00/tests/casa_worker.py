import runpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from casa_runtime import InvalidTrajectory,replay
import argparse
p=argparse.ArgumentParser();p.add_argument('--instance',required=True);p.add_argument('--trajectory',required=True);p.add_argument('--output',required=True);a=p.parse_args()
try:replay(a.instance,a.trajectory,a.output)
except InvalidTrajectory:
 import traceback
 traceback.print_exc();sys.exit(2)
