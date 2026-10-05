"""Trusted root-side final copy. Never execute or follow agent-provided files."""
import argparse
import json
import os
from pathlib import Path
import shutil
from agent_batch_contract import files, save
from secret_scan import scan_tree

def main():
    p=argparse.ArgumentParser(); p.add_argument('--job',required=True)
    p.add_argument('--uid',type=int,required=True); p.add_argument('--gid',type=int,required=True)
    a=p.parse_args(); out=Path('/out'); raw=Path('/raw'); job=Path('/job')
    if list(out.iterdir()): raise ValueError('mirror delivery already exists; preserve it')
    # All history, including .state and tamper events, is retained.
    for path in files(raw):
        rel=path.relative_to(raw)
        target=out/(Path(*rel.parts[1:]) if rel.parts[0]==a.job else Path('.mirror_metadata')/rel)
        target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(path,target)
    secrets={k:v.encode() for k,v in json.loads(Path('/secrets/scan.json').read_text()).items()}
    reports=[]
    for root in (job,out):
        reports.append(scan_tree(root,secrets,redact=True))
        if not scan_tree(root,secrets)['clean']: raise ValueError('residual credentials; delivery blocked')
        for path in [root,*root.rglob('*')]:
            if path.is_symlink(): raise ValueError('symlink in evidence')
            os.chown(path,a.uid,a.gid); os.chmod(path,0o700 if path.is_dir() else 0o600)
    save(out/'scan-report.json',dict(clean=True,reports=reports))
    os.chown(out/'scan-report.json',a.uid,a.gid)

if __name__=='__main__': main()
