"""Independent private replay, including the exact failed final control."""
import argparse
import json
from pathlib import Path
import sys
import traceback
import numpy as np
sys.path[:0]=[str(Path(__file__).parent),'/trusted','/opt/VLABench','/opt/rrt-algorithms']
from vlb_traj import Session, load_archive, physics_state, canonical, SCHEMA, UPSTREAM
from runtime import count_physics


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',default='/recorded/trajectory.npz')
    p.add_argument('--instance',default='/tests/instance.json')
    p.add_argument('--result',required=True)
    p.add_argument('--video')
    args=p.parse_args()
    result={'success':False,'physics_steps':0,'error_type':None,'completed_controls':0}
    writer=None
    with Session(args.instance,budget_path=None) as s:
        counter=count_physics(s)
        data=load_archive(args.input)
        metadata=json.loads(str(data['metadata']))
        for k,v in dict(schema=SCHEMA,upstream_commit=UPSTREAM,instance_sha=s.instance_sha,native_task=s.spec['native_task'],
                        control_dt=s.dt,n_substeps=s.substeps,dtype='float64',action_semantics='absolute_actuator_position_targets').items():
            if metadata.get(k)!=v: raise ValueError('Invalid archive metadata '+k)
        actions=data['actions']
        if actions.shape!=(len(actions),9) or actions.dtype!=np.float64: raise ValueError('Invalid actions')
        if len(actions): s._validate(actions)
        if not np.array_equal(data['times'],np.arange(len(actions))*s.dt): raise ValueError('Invalid times')
        result.update(n_actions=len(actions),initial_state_sha=s.initial_hash,frames=0)
        if args.video:
            import imageio.v2 as imageio
            writer=imageio.get_writer(args.video,fps=round(1/s.dt))
        try:
            for i,action in enumerate(actions):
                if s.done: raise ValueError('Action after native termination')
                s._step(action)
                status=s.status()  # Exactly the online per-control predicate query.
                result['success']=bool(status['success'])
                if writer:
                    writer.append_data(s._env.render(camera_id=2,width=640,height=480))
                    result['frames']+=1
                if status['success'] and i+1<len(actions): raise ValueError('Action after success')
            result.update(s.status())
        except Exception as exc:
            result.update(error_type=type(exc).__name__,error=str(exc),success=False)
            traceback.print_exc()
        finally:
            if writer: writer.close()
            result['physics_steps']=counter['steps']
            result['completed_controls']=s.sim_steps
            Path(args.result).write_text(canonical(result)+'\n')
            np.savez_compressed(args.result+'.state.npz',integration=physics_state(s._env))


if __name__=='__main__': main()
