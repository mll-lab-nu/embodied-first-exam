"""Rebuild the three pinned simulator environments; source/assets are hash checked."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser();p.add_argument('suite',choices=['metaworldplus','robocasa365','robocasa-gr1','all']);a=p.parse_args();locks=json.loads((HERE/'upstream-lock.json').read_text())
def run(*args,**kw):subprocess.run(list(map(str,args)),check=True,**kw)
for suite in (['metaworldplus','robocasa365','robocasa-gr1'] if a.suite=='all' else [a.suite]):
 key='metaworld' if suite=='metaworldplus' else suite;dest=ROOT/'.cache/robot24'/key;lock=locks[key]
 if not dest.exists():
  run('git','clone',lock['remote'],dest);run('git','-C',dest,'checkout','--detach',lock['commit'])
 head=subprocess.check_output(['git','-C',str(dest),'rev-parse','HEAD'],text=True).strip()
 if head!=lock['commit']:raise RuntimeError(f'{dest}: expected commit {lock["commit"]}, got {head}; checkout the pinned commit explicitly')
 base=f'ghcr.io/jameskrw/rcb-{suite}'
 run('docker','build','-t',base+(':0.1.0' if suite=='metaworldplus' else '-runtime:0.1.0'),ROOT/'images'/suite)
 if suite!='metaworldplus':
  mode='365' if suite=='robocasa365' else 'gr1'
  run(sys.executable,HERE/'download_assets.py','--suite',mode,cwd=ROOT)
  if suite=='robocasa-gr1':run(sys.executable,HERE/'download_assets.py','--suite','gr1-legacy',cwd=ROOT)
  run('docker','build','-t',base+':0.1.0','-f',ROOT/'images'/suite/'Dockerfile.assets',dest/'robocasa/models')
  if suite=='robocasa-gr1':run('docker','build','-t',base+':0.1.1','-f',ROOT/'images'/suite/'Dockerfile.controller',ROOT/'images'/suite)
