"""Publish current mode suites, keeping prior registrations as immutable history."""
from pathlib import Path
import shutil,json,collections
from common import ROOT,ARCHIVE,REGISTRY,read,write

def main():
 data=read(REGISTRY);history=ARCHIVE/'suites';history.mkdir(exist_ok=True)
 for b in ('vlabench','metaworldplus','robocasa','robocasa365','robocasa-gr1'):
  p=ROOT/'suites'/f'{b}.json'
  if p.exists() and not (history/p.name).exists():shutil.copy2(p,history/p.name)
  write(p,dict(name=b,protocol=data['protocol'],default_mode='unlimited',registration='Canonical instances; acceptance belongs to this revision only.',tasks=[dict(task_id=r['modes']['unlimited']['task_id'],path=r['modes']['unlimited']['path'],family=r['family'],environment_id=r['environment_id'],seed=r['seed'],instance_sha256=r['instance_sha256'],historical_source=r['source'],modes={m:{k:v for k,v in x.items() if k!='fingerprints'} for m,x in r['modes'].items()}) for r in data['instances'] if r['benchmark']==b]))
 # Preserve coverage as native-family coverage, not double the families for modes.
 path=ROOT/'suites/coverage.json'
 if not (history/path.name).exists():shutil.copy2(path,history/path.name)
 coverage=read(path);mapping={r['source']:r['modes']['unlimited']['path'] for r in data['instances'] if not r['modes']['unlimited']['blocked_reason']}
 accepted={r['modes']['unlimited']['path'] for r in data['instances'] if '/tasks/' in r['source']}
 for r in coverage['tasks']:
  r['historical_paths']=r.get('historical_paths',r['paths'])
  r['paths']=[mapping.get(p,p) for p in r['historical_paths']]
  r['accepted_source_instances']=sum(p in accepted for p in r['paths'])
 write(path,coverage)
 # Per-family original source acceptance is distinct from canonical revision admission.
 print('Updated five suites; original registrations archived; coverage remains native-family based.')
if __name__=='__main__':main()
