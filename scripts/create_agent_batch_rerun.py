#!/usr/bin/env python3
"""Maintainer authorization: retry incomplete trials under <batch>-rerun only."""
import argparse
import copy
import json
from pathlib import Path
from agent_batch_contract import read,save,validate,digest,check_batch,TERMINAL,linked_rerun,match_assignment

def create(plan,report):
    if report['plan_sha256']!=plan['plan_sha256']: raise ValueError('report differs from assignment')
    selected=[dict(job=r['job'],task=r['task'],repetition=r['repetition']) for r in report['rows'] if r['status'] not in TERMINAL]
    if not selected: raise ValueError('no incomplete trials to authorize')
    if report['errors']: raise ValueError('resolve inconsistent records before authorizing reruns')
    child=copy.deepcopy(plan); child.pop('plan_sha256'); child['batch']=plan['batch']+'-rerun'
    child.pop('helper_selects_model',None); child.pop('assignment_sha256',None)
    child['rerun']=dict(batch=plan['batch'],plan_sha256=plan['plan_sha256'],trials=selected)
    child['tasks']=[t for t in plan['tasks'] if t['name'] in {r['task'] for r in selected}]
    child['task_bases']=list(dict.fromkeys(t['base'] for t in child['tasks']))
    child['jobs']=[dict(job=child['batch']+'-'+t['mode']+'-'+t['base'],task=t['name'],repetitions=sum(r['task']==t['name'] for r in selected)) for t in child['tasks']]
    child['trial_count']=len(selected)
    if child['upload']['type']=='hf': child['upload']['prefix']=f"helpers/{child['helper']}/{child['batch']}"
    child['plan_sha256']=digest(child); return linked_rerun(plan,child)

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--assignment',type=Path,required=True)
    p.add_argument('--jobs',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    try:
        if a.output.exists(): raise ValueError('preserve existing rerun authorization')
        plan=validate(read(a.assignment))
        plan=match_assignment(plan,read(a.jobs/(plan['batch']+'-plan.json')))
        child=create(plan,check_batch(a.jobs,plan)); save(a.output,child)
        print(json.dumps(dict(batch=child['batch'],trial_count=child['trial_count'],assignment=str(a.output)),indent=2))
    except (OSError,ValueError,KeyError) as e: p.exit(2,'Rerun authorization blocked: '+str(e)+'\n')

if __name__=='__main__': main()
