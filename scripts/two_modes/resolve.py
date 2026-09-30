"""Resolve an old task path/ID without rewriting historical result files."""
import argparse
from common import ROOT,read,resolve
p=argparse.ArgumentParser();p.add_argument('old');p.add_argument('--mode',choices=['limited','unlimited','historical'],default='historical');a=p.parse_args()
if a.mode=='historical':
 try:print(resolve(a.old));raise SystemExit()
 except FileNotFoundError:pass
mapping=read(ROOT/'suites/task-path-aliases.json')
for r in mapping['aliases']:
 if a.old in (r['old_path'],r['old_task_id'],r['old_path'].split('/')[-1]):
  print(resolve(r['old_path']) if a.mode=='historical' else ROOT/r[a.mode]);break
else:raise SystemExit('Unknown historical task')
