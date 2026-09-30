#!/usr/bin/env bash
# Applies only to versioned RoboCasa unlimited derivatives; historical tasks are immutable.
set -euo pipefail
python3 - "$1" <<'PY'
import ast,json,pathlib,sys,tomllib
p=pathlib.Path(sys.argv[1]);cfg=tomllib.loads((p/'task.toml').read_text())
if cfg.get('metadata',{}).get('experiment_mode')not in ('unlimited-60min-v2','unlimited-60min-v3'):sys.exit(0)
if cfg.get('metadata',{}).get('simulator')!='robocasa':sys.exit(0)
def require(ok,msg):
 if not ok:raise ValueError(str(p)+': '+msg)
require(cfg['agent']['timeout_sec']==3600,'agent timeout must be 3600')
require((p/'environment/instance.npz').read_bytes()==(p/'tests/instance.npz').read_bytes(),'agent/verifier instance mismatch')
if (p/'environment/action_spec.json').exists():
 def reject(x):raise ValueError('non-standard JSON '+x)
 d=json.loads((p/'environment/action_spec.json').read_text(),parse_constant=reject);n=d['action_dim']
 require(sorted(i for lo,hi in d['action_parts'].values() for i in range(lo,hi))==list(range(n)),'incomplete/overlapping action parts')
 require(len(d['channels'])==n,'missing channel descriptions')
 if n==24:
  require(d['lower']==[-10.]*12+[-3.]*12 and d['upper']==[10.]*12+[3.]*12,'wrong effective GR1 bounds')
 else:require(d['action_parts']['hybrid_mode']==[n-1,n],'wrong hybrid mode index')
for part in ('environment','tests'):
 for f in (p/part).glob('casa*.py'):
  text=f.read_text();ast.parse(text)
  for bad in ('self.resets>=40','self.total_steps>=16000','len(self.actions)>=MAX_CONTROLS','len(a)<=MAX_CONTROLS','<= MAX_ACTIONS','>= MAX_ACTIONS'):
   require(bad not in text,'wrapper exploration cap: '+bad)
PY
