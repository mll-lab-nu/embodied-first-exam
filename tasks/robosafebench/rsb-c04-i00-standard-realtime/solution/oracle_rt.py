"""Stream the frozen public RT reference, including versioned authored snapshots.

Schema1 keeps its original no-picture policy. Schema2 drains the queue at each
explicit snapshot, requests exactly its frozen camera batches, and retains the
pixels actually delivered. No initial or extra checker pictures are added.
"""
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np

from rcb_client import EpisodeOver, Robot
import public_observation_plan as O


from public_observation_delivery import save_snapshot


def run_reference(document, arrays, robot, output=None, *, sleep=time.sleep, monotonic=time.monotonic):
    spec=robot.spec();dt=spec['control_dt'];per=max(1,int(round(spec['max_chunk_s']/dt)))
    version2=document.get('schema')==O.SCHEMA
    if version2:
        O.validate(document,list(spec['cameras']),clock='realtime')
        ends={}
        for item in document['plan']:
            if 'rows' in item:ends[item['type']]=item['rows'][1]
        if set(ends)!=set(arrays) or any(len(arrays[typ])!=end for typ,end in ends.items()):
            raise ValueError('Public plan must cover every frozen motion array row exactly once')
        if output is None:
            raise ValueError('Schema2 requires an observation delivery artifact directory')
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
        maximum=spec.get('timing',{}).get('max_cameras_while_running')
        if type(maximum) is not int or maximum<max(map(len,O.batches(spec['cameras']))):
            raise ValueError('Actual public RT camera limit differs from frozen snapshot batches')
    else:
        if document.get('schema') not in (None,'rsb.public-control-plan/1') or any(
                item.get('type')=='observe' for item in document['plan']):
            raise ValueError('An unversioned snapshot must not change legacy RT semantics')
    budget=spec.get('budget',{}).get('wall_clock_s',1800)
    deadline=monotonic()+max(1,float(budget))+60

    def wait(cond):
        while True:
            status=robot.status()
            if status.get('status')=='exited':
                raise EpisodeOver('episode finished')
            if status.get('done') or cond(status):
                return status
            if monotonic()>deadline:
                raise TimeoutError('Public RT reference exceeded its finite episode budget')
            sleep(.05)

    status={};deliveries=[]
    try:
        for item_index,item in enumerate(document['plan']):
            typ=item['type']
            if typ=='observe':
                status=wait(lambda value:value['planned_steps']==0)
                if status.get('done'):
                    break
                for batch_index,cameras in enumerate(item['camera_batches']):
                    before=robot.status()
                    if before.get('planned_steps')!=0:
                        raise ValueError('Snapshot would cross an undrained motion boundary')
                    sent=monotonic()
                    result=robot.get_obs(cameras=cameras,seconds=0,video='none',include_depth=False)
                    received=monotonic();status=robot.status()
                    deliveries.append(save_snapshot(output/('%04d-%02d'%(item_index,batch_index)),result,spec,
                        item['boundary'],cameras,before,status,sent,received))
                    if status.get('done'):
                        break
            else:
                dim=int(spec['action_types'][typ]['dim'])
                if 'rows' in item:
                    a,b=item['rows']
                    for k in range(a,b,per):
                        status=wait(lambda value:value['planned_steps']<=per)
                        if status.get('done'):
                            break
                        at=status['control_steps']+status['planned_steps'] if status.get('running') and status['planned_steps'] else None
                        result=robot.submit(typ,arrays[typ][k:min(k+per,b)],dt=dt,interpolate='hold',at=at,
                                            cameras=[],video='none')
                        if result.meta.get('late_steps'):
                            print('late rows:',result.meta['late_steps'],flush=True)
                else:
                    status=wait(lambda value:value['planned_steps']==0)
                    if not status.get('done'):
                        robot.submit(typ,np.asarray(item['row'],dtype=np.float64).reshape(1,dim),dt=dt,
                            interpolate='hold',cameras=[],video='none',note=item.get('text') or '')
                        status=wait(lambda value:value['planned_steps']==0)
            if status.get('done'):
                break
        if not status.get('done'):
            status=wait(lambda value:value['planned_steps']==0)
    except EpisodeOver:
        status=robot.status()
    if version2:
        (output/'DELIVERY_RECEIPT.json').write_text(json.dumps({'schema':'rsb.public-observation-run/1',
            'public_plan_sha256':O.canonical(document),'observation_policy':document['observation_policy'],
            'snapshot_batches_delivered':len(deliveries),'final_status':status,
            'native_or_task_credit_granted':False},indent=2)+'\n')
    return status


def main():
    with open('/solution/oracle.json') as stream:
        document=json.load(stream)
    arrays=dict(np.load('/solution/oracle.npz',allow_pickle=False)) if os.path.exists('/solution/oracle.npz') else {}
    status=run_reference(document,arrays,Robot(),'/app/output/public_observations')
    print(status,flush=True)


if __name__=='__main__':
    main()
