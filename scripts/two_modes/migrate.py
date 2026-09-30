"""Archive obsolete task layouts, update live references, preserve all result bytes."""
import json,re,shutil,tomllib
from pathlib import Path
from common import ROOT,ARCHIVE,REGISTRY,read,write

def rewrite(value,mapping):
 if isinstance(value,str):
  for old,new in mapping:
   if value==old or value.startswith(old+'/'):return new+value[len(old):]
  return value
 if isinstance(value,list):return [rewrite(v,mapping) for v in value]
 if isinstance(value,dict):return {k:rewrite(v,mapping) for k,v in value.items()}
 return value

def main():
 report=ROOT/'docs/validation/two-modes-v3';report.mkdir(parents=True,exist_ok=True)
 if (report/'migration.json').exists():raise SystemExit('Migration already recorded; not repeated')
 data=read(REGISTRY);moves={};aliases=[]
 for r in data['instances']:
  path=r['source']
  if path.startswith('tasks/'):
   moves[path]=str((ARCHIVE/path).relative_to(ROOT))
  aliases.append(dict(old_path=path,old_task_id=r['source_task_id'],unlimited=r['modes']['unlimited']['path'],limited=r['modes']['limited']['path'],instance_sha256=r['instance_sha256']))
 for old in ('limited_tasks/robocasa-60min-v2','unlimited_tasks/robocasa-60min-v2','limited_tasks/vlabench','limited_tasks/vlabench-60min'):
  if (ROOT/old).exists():
   if old=='limited_tasks/vlabench':
    for child in (ROOT/old).iterdir():
     if child.is_dir() and '60min-v3' not in child.name:
      rel=str(child.relative_to(ROOT));moves[rel]=str((ARCHIVE/rel).relative_to(ROOT))
   else:moves[old]=str((ARCHIVE/old).relative_to(ROOT))
 # Move bytes, not rewrite the task contents that historic checksums bind.
 for old,new in moves.items():
  src,dest=ROOT/old,ROOT/new
  if dest.exists():raise RuntimeError('Archive target already exists: '+new)
  dest.parent.mkdir(parents=True,exist_ok=True);shutil.move(src,dest)
 mapping=sorted(moves.items(),key=lambda x:-len(x[0]));data=rewrite(data,mapping);write(REGISTRY,data)
 write(ROOT/'suites/task-path-aliases.json',dict(description='Historical IDs are provenance aliases, not additional active tasks. Model result files are unchanged.',moves=moves,aliases=aliases))
 # Current suite manifests and human-readable repository docs keep live archive
 # links. Frozen jobs, validation evidence, task internals and offline exports are
 # immutable; their old paths are resolved through task-path-aliases.json.
 changed=[]
 for tree,suffixes in (('suites',{'.json'}),('docs',{'.md'}),('scripts',{'.py','.sh'})):
  for p in (ROOT/tree).rglob('*'):
   if not p.is_file() or p.suffix not in suffixes:continue
   rel=str(p.relative_to(ROOT))
   if rel in ('suites/two-modes.json','suites/task-path-aliases.json') or rel.startswith(('scripts/two_modes/','docs/validation/','docs/prompts/')):continue
   text=p.read_text();original=text
   # One pass with both boundaries: limited_tasks must not match within
   # unlimited_tasks, nor may an inserted archive path be rewritten again.
   replacements=dict(mapping)
   pattern=r'(?<![\w/.-])(?:'+ '|'.join(re.escape(old) for old in replacements)+r')(?=$|[\s/\"\x27`)#?])'
   text=re.sub(pattern,lambda match:replacements[match.group(0)],text)
   if text!=original:p.write_text(text);changed.append(rel)
 # Preserve the original dataset and register only the out-of-scope tasks left in tasks/.
 manifest=ROOT/'tasks/dataset.toml';shutil.copy2(manifest,ARCHIVE/'tasks/dataset.toml')
 d=tomllib.loads(manifest.read_text());keep=[t for t in d['tasks'] if (ROOT/'tasks'/t['name'].split('/')[-1]/'task.toml').exists()]
 from harbor.models.dataset.manifest import DatasetManifest
 model=DatasetManifest.from_toml_file(manifest)
 model.tasks=[t for t in model.tasks if (ROOT/'tasks'/t.name.split('/')[-1]/'task.toml').exists()]
 manifest.write_text(model.to_toml())
 write(report/'migration.json',dict(moves=moves,live_reference_files_updated=changed,historical_results_modified=False,aliases='suites/task-path-aliases.json'))
 print('Archived',len(moves),'paths; updated',len(changed),'live reference files; historical results untouched')

if __name__=='__main__':main()
