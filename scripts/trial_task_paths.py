"""Resolve local or imported Harbor task packages without rewriting evidence."""
from pathlib import Path
import json
import hashlib

def original_task(trial):
    trial=Path(trial).resolve()
    for root in trial.parents:
        if (root/'receipt.json').is_file() and (root/'local-task-map.json').is_file():
            from agent_batch_contract import read, package, validate, linked_rerun
            receipt=read(root/'receipt.json'); mapping=read(root/'local-task-map.json')
            b=receipt['report']['batch']; plan=validate(read(root/'agents'/(b+'-plan.json')))
            if mapping['plan_sha256']!=plan['plan_sha256'] or receipt['plan_sha256']!=plan['plan_sha256']:
                raise ValueError('Imported native task map identity changed')
            plans=[plan]
            for report in receipt['report'].get('rerun_reports',[]):
                child=linked_rerun(plan,read(root/'agents'/(report['batch']+'-plan.json')))
                if child['plan_sha256'] not in receipt.get('rerun_plan_sha256',[]): raise ValueError('Unapproved imported rerun')
                plans.append(child)
            expected=next((t for p in plans for t in p['tasks'] if trial.parent.name==p['batch']+'-'+t['mode']+'-'+t['base']),None)
            if expected is None or trial.parent.parent != root/'agents': raise ValueError('Trial outside imported batch')
            target=Path(mapping['tasks'][expected['name']])
            return package(target.parent.parent,expected)
        if not (root/'BUNDLE.json').is_file(): continue
        from helper_bundle import safe_path, file_id
        index=json.loads((root/'delivery/path-map.json').read_text())
        matches=[e for e in index['entries'] if e['trial']==trial.relative_to(root).as_posix()]
        if len(matches)!=1 or not matches[0]['task']:
            raise ValueError('Imported trial has no uniquely bound task package')
        entry=matches[0]; task=safe_path(root,entry['task'])
        for rel,identity in entry['task_files'].items():
            path=safe_path(root,rel)
            if not path.is_relative_to(task) or not path.is_file() or file_id(path)!=identity:
                raise ValueError('Imported task package identity changed')
        return task
    result=json.loads((trial/'result.json').read_text())
    value=(result.get('task_id') or {}).get('path')
    if not value and (trial/'config.json').is_file():
        value=(json.loads((trial/'config.json').read_text()).get('task') or {}).get('path')
    if not value or not Path(value).is_absolute(): raise ValueError('Trial has no recorded task path that is unambiguous and absolute')
    return Path(value)
