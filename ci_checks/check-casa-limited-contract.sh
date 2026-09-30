#!/usr/bin/env bash
# Static boundary checks complement actual Docker/network/forged-score probes.
set -euo pipefail
python3 - "$1" <<'PY'
import ast, json, pathlib, sys, tomllib
p=pathlib.Path(sys.argv[1]);cfg=tomllib.loads((p/'task.toml').read_text())
if cfg.get('metadata',{}).get('experiment_mode')not in ('limited-60min-v2','limited-60min-v3'):sys.exit(0)
if cfg.get('metadata',{}).get('simulator')!='robocasa':sys.exit(0)
def require(value,message):
 if not value:raise ValueError(str(p)+': '+message)
require(cfg['agent']['timeout_sec']==3600,'agent must have 60 minutes')
require(cfg['environment']['network_mode']=='allowlist' and set(cfg['environment']['allowed_hosts'])=={'sim','codex-egress'},'native Harbor egress control required')
require(cfg['verifier']['environment_mode']=='separate','verifier must be separate')
require(cfg['verifier']['environment']['network_mode']=='no-network','verifier network')
require(any(a.get('service')=='sim' and a['source']=='/recorded/' for a in cfg['artifacts'] if isinstance(a,dict)),'sidecar artifacts')
require(cfg['verifier']['collect'][0]['service']=='sim','seal must run privately in sim')
env=p/'environment';private=env/'server'
for name in ('instance.npz','backend.py','backend.json','public_spec.json'):
 require((private/name).read_bytes()==(p/'tests'/name).read_bytes(),'online/replay differ: '+name)
require('_check_success(' not in (private/'backend.py').read_text(),'sidecar must reuse native Session results; extra predicate calls change timers')
client=ast.parse((env/'client/limited_client.py').read_text())
public={n.name for n in client.body if isinstance(n,ast.FunctionDef) and not n.name.startswith('_')}
require(public=={'spec','observe','step','status'},'unexpected public client method')
docker=(env/'Dockerfile').read_text()
require([x for x in docker.splitlines() if x.startswith(('COPY','ADD'))]==['COPY client/ /app/'],'main copies private contents')
require(set(x.name for x in (env/'client').iterdir())=={'limited_client.py','API.md'},'unexpected main client files')
ignore=(env/'.dockerignore').read_text()
require(ignore.startswith('*\n') and '!server' not in ignore,'private build context not excluded')
compose=(env/'docker-compose.yaml').read_text()
for forbidden in ('docker.sock','privileged: true','network_mode: host','pid: host','volumes:'):
 require(forbidden not in compose,'unsafe compose field '+forbidden)
require('internal: true' in compose and 'no-new-privileges:true' in compose and 'cap_drop:' in compose,'missing isolation')
spec=json.loads((private/'public_spec.json').read_text(),parse_constant=lambda x: (_ for _ in ()).throw(ValueError(x)))
require(set(spec)<= {'action_shape','action_lower','action_upper','channels','action_parts','action_frame','control_hz','hybrid_mode','hand_semantics','gripper_semantics','arm_output_scale','action_semantics'},'unexpected public spec fields')
dim=spec['action_shape'][0]
require(len(spec['action_lower'])==len(spec['action_upper'])==dim,'invalid bounds')
require(all(a<b for a,b in zip(spec['action_lower'],spec['action_upper'])),'invalid ranges')
for f in list(private.glob('*.py'))+list((p/'tests').glob('*.py')):ast.parse(f.read_text())
PY
