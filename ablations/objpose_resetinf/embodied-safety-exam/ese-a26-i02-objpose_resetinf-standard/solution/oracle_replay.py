"""Synchronous public paused reference; schema2 retains authored snapshots.

The initial and normal submitted cameras keep the existing all-public policy.
Only frozen authored opportunities add explicit seconds0 observations.
"""
import json
import os
from pathlib import Path
import time

import numpy as np
from rcb_client import EpisodeOver, Robot
import public_observation_plan as O
from public_observation_delivery import save_snapshot

HTTP_POLICY = {'cameras':'all_public','initial_observe':True,'video':'none','interpolate':'hold'}


def run_reference(document, arrays, robot, output=None, *, monotonic=time.monotonic):
    spec=robot.spec();plan=document['plan'];version2=document.get('schema')==O.SCHEMA
    if version2:
        O.validate(document,list(spec['cameras']),clock='paused')
        ends={}
        for item in plan:
            if 'rows' in item:ends[item['type']]=item['rows'][1]
        if set(ends)!=set(arrays) or any(len(arrays[typ])!=end for typ,end in ends.items()):
            raise ValueError('Public paused plan must cover every frozen array row exactly once')
        if document.get('http_policy')!=HTTP_POLICY:
            raise ValueError('Public paused schema2 must retain its normal all-public HTTP policy')
        if output is None:raise ValueError('Schema2 requires an observation delivery artifact directory')
        output=Path(output);output.mkdir(parents=True,exist_ok=False)
    elif document.get('schema') not in (None,'ese.public-control-plan/1') or any(
            item.get('type')=='observe' for item in plan):
        raise ValueError('Unversioned snapshots cannot change legacy paused semantics')
    if document.get('candidate_identity') or version2:
        if document.get('http_policy')!=HTTP_POLICY:
            raise ValueError('New candidate oracle lacks its frozen HTTP observation policy')
        cameras=sorted(spec['cameras'])
        robot.get_obs(cameras=cameras,seconds=0.,video='none')
    else:cameras=[sorted(spec['cameras'])[0]]
    dt=spec['control_dt'];per=max(1,int(round(spec['max_chunk_s']/dt)))
    deliveries=[];last=None
    try:
        for index,item in enumerate(plan):
            typ=item['type']
            if typ=='observe':
                for batch,cams in enumerate(item['camera_batches']):
                    before=robot.status()
                    if before.get('done'):break
                    sent=monotonic()
                    result=robot.get_obs(cameras=cams,seconds=0,video='none',include_depth=False)
                    received=monotonic();after=robot.status()
                    deliveries.append(save_snapshot(output/('%04d-%02d'%(index,batch)),result,spec,
                        item['boundary'],cams,before,after,sent,received,clock='paused'))
                continue
            dim=int(spec['action_types'][typ]['dim'])
            if 'rows' in item:
                a,b=item['rows']
                for k in range(a,b,per):
                    last=robot.submit(typ,arrays[typ][k:min(k+per,b)],dt=dt,interpolate='hold',
                                      video='none',cameras=cameras)
                    if last.done or last.meta.get('blocked'):break
            else:
                last=robot.submit(typ,np.asarray(item['row'],dtype=np.float64).reshape(1,dim),dt=dt,
                    interpolate='hold',video='none',cameras=cameras,note=item.get('text') or '')
            # Historical schema1 stops this blocked chunk, then still emits later report/end calls.
            if last is not None and (last.done or (version2 and last.meta.get('blocked'))):break
    except EpisodeOver:
        pass
    status=robot.status()
    if version2:
        (output/'DELIVERY_RECEIPT.json').write_text(json.dumps({'schema':'ese.public-observation-run/1',
            'clock':'paused','public_plan_sha256':O.canonical(document),
            'observation_policy':document['observation_policy'],
            'snapshot_batches_delivered':len(deliveries),'final_status':status,
            'native_or_task_credit_granted':False},indent=2)+'\n')
    return status


def main():
    with open('/solution/oracle.json') as stream:document=json.load(stream)
    arrays=dict(np.load('/solution/oracle.npz',allow_pickle=False)) if os.path.exists('/solution/oracle.npz') else {}
    print(run_reference(document,arrays,Robot(),'/app/output/public_observations'),flush=True)


if __name__=='__main__':
    main()
