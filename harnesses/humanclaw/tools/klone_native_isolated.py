#!/usr/bin/python3
"""Run native agents with only runtime, per-run home and workspace mounted."""
import os
from pathlib import Path
import sys

root=Path('/gscratch/stf/hengyil6/native-harnesses/20261015')
os.environ['LD_LIBRARY_PATH']=str(root/'lib')
harness=sys.argv[1]
args=sys.argv[2:]
codex=root/'codex/package/vendor/x86_64-unknown-linux-musl/bin/codex'
node=root/'node-v26.0.0-linux-x64/bin/node'
pi=root/'pi'
command=([str(codex)] if harness=='codex' else [str(node),'--import',(pi/'packages/coding-agent/src/experimental/source-resolver.ts').as_uri(),str(pi/'packages/coding-agent/src/cli.ts')])
if args==['--version']:
    os.execv(command[0],command+args)
home=Path(os.environ['HOME']).resolve()
workspace=Path.cwd().resolve()
if home.name!='home' or workspace.name!='workspace' or home.parent!=workspace.parent or home.parent.name!='native':
    raise SystemExit('Native launcher requires a dedicated run/native/{home,workspace}.')
bwrap=[str(root/'bubblewrap/usr/bin/bwrap'),'--unshare-all','--share-net','--die-with-parent','--new-session']
# Klone's /gscratch is a symlink. Preserve that alias inside the empty root.
scratch=Path('/gscratch')
if scratch.is_symlink(): bwrap+=['--symlink',os.readlink(scratch),str(scratch)]
for path in ('/usr','/bin','/lib','/lib64'):
    if Path(path).is_symlink(): bwrap+=['--symlink',os.readlink(path),path]
    elif Path(path).exists(): bwrap+=['--ro-bind',path,path]
for path in ('/etc/ssl','/etc/pki','/etc/resolv.conf','/etc/hosts','/etc/nsswitch.conf','/etc/passwd','/etc/group','/etc/ld.so.cache'):
    if Path(path).exists(): bwrap+=['--ro-bind',path,path]
bwrap+=['--proc','/proc','--dev','/dev','--tmpfs','/tmp',
        '--ro-bind',str(root),str(root.resolve()),'--bind',str(home),str(home),'--bind',str(workspace),str(workspace),
        '--chdir',str(workspace),'--setenv','TMPDIR','/tmp',
        '--setenv','LD_LIBRARY_PATH',str(root/'lib')]
# Pi's session archive is a sibling of home/workspace, and contains only this run.
for index,arg in enumerate(args[:-1]):
    if arg=='--session-dir':
        session=Path(args[index+1]).resolve()
        if session!=home.parent/'sessions': raise SystemExit('Session path must belong to this run.')
        session.mkdir(exist_ok=True)
        bwrap+=['--bind',str(session),str(session)]
if args==['--isolation-check']:
    command=['/bin/sh','-c',
             'test ! -e /gscratch/stf/hengyil6/HumanCLAW/.env && '
             'test ! -e /gscratch/stf/hengyil6/data && '
             'test ! -e /gscratch/stf/hengyil6/native-experiments && '
             'test ! -e /gscratch/stf/hengyil6/experiments && '
             'test -z "${AZURE_OPENAI_API_KEY+x}" && '
             'test -d "$HOME" && test -w . && '
             'printf "private_credentials_and_benchmark_paths_hidden; workspace_writable\\n"']
else:
    command+=args
os.execv(bwrap[0],bwrap+['--']+command)
