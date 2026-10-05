#!/usr/bin/env python3
"""Record helper incident notes, or explicitly seal a stopped/crashed native batch.

--recover stops only containers whose recorded per-job owner belongs to a dead lane.
It never reruns jobs, moves claims, or promotes a mirror gap to complete evidence.
"""
import argparse
import os
from pathlib import Path
from agent_batch_contract import read,save,validate,locked
from agent_batch_runtime import credentials,auth_secrets,live,command,Mirror,stop,utc
from agent_batch_delivery import seal,verify_tree

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--jobs',type=Path,required=True)
    p.add_argument('--assignment',type=Path,required=True); p.add_argument('--recover',action='store_true')
    p.add_argument('--notes-file',type=Path); a=p.parse_args()
    try:
        jobs=a.jobs.resolve(); plan=validate(read(a.assignment)); b=plan['batch']; env,auth=credentials(os.environ)
        if read(jobs/(b+'-plan.json'))!=plan: raise ValueError('batch differs from assignment')
        with locked(jobs/'.batch-locks'/b):
            metadata=read(jobs/(b+'-metadata.json'))
            for lane in metadata['lanes']:
                if lane['status']=='running':
                    if live(lane): raise ValueError('a lane is still running; wait for it')
                    if not a.recover: raise ValueError('dead lane requires explicit --recover')
                    lane.update(status='interrupted',finished_at=utc(),returncode=None)
                    stop(jobs,b,'dead lane recovered; original trial records preserved')
            if (jobs/(b+'-inventory.json')).exists(): verify_tree(jobs.parent,plan)
            private=jobs.parent/'.agent-batch-private'/b
            secrets=auth_secrets(env,auth)
            for history in private.glob('auth-history-*.json'): secrets.update(auth_secrets(env,auth,history))
            for spec in plan['jobs']:
                execution=jobs/(spec['job']+'-execution.json')
                if not execution.exists(): continue
                owner=read(execution)['owner']; active=command(['docker','ps','-q','--filter','label=topogym.batch.owner='+owner]).split()
                if active:
                    if not a.recover: raise ValueError('owned containers still running; use --recover only after lane stops')
                    command(['docker','stop','--time','10',*active],timeout=45)
                marker=jobs/(spec['job']+'-mirror.json')
                if not marker.exists() and a.recover:
                    dest=jobs.with_name('agents_mirror')/spec['job']
                    if dest.exists(): raise ValueError('partial mirror copy exists; preserve it for manual review')
                    Mirror(jobs,spec,plan,owner,private,env,resume=True).finish(secrets,allow_interrupted=True)
                    save(marker,dict(complete=False,recovered=True,owner=owner,finished_at=utc()))
            if a.notes_file: metadata['notes']=a.notes_file.read_text()
            metadata.update(status='finished',finished_at=utc()); save(jobs/(b+'-metadata.json'),metadata)
            report=seal(jobs,plan,secrets)
            print('Sealed; evaluation_complete='+str(report['evaluation_complete'])+'; delivery_complete='+str(report['delivery_complete']))
        return 0
    except (ValueError,OSError,KeyError) as e: p.exit(2,'Finalization blocked: '+str(e)+'\n')

if __name__=='__main__': raise SystemExit(main())
