"""Trusted actuator replay of every limited control in a fresh native simulator."""
import argparse
import json
from pathlib import Path
import sys
import traceback
import numpy as np
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from backend import Backend
from archive import load_npz
SCHEMA='rcb-casa-limited-actuators-v2'

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',required=True);p.add_argument('--result',required=True);p.add_argument('--video');a=p.parse_args()
    b=Backend(HERE,replaying=True)
    writer=renderer=None
    if a.video:
        import imageio.v2 as iio
        import mujoco
        renderer=mujoco.Renderer(b.model,480,480)
        writer=iio.get_writer(a.video,fps=b.env.control_freq/10,codec='libx264')
        renderer.update_scene(b.data,camera=b.cameras[0]);writer.append_data(renderer.render())
    result=dict(success=False,initial_success=b.initial_success,initial_state_sha=b.initial_sha,instance_sha=b.instance_sha,
                completed_controls=0,physics_steps=0,first_success_index=None,invalid_trajectory=False,error_type=None)
    try:
        z=load_npz(a.input,max_bytes=64_000_000)
        if set(z)!={'actions','actuator_controls','offsets','completed','instance_sha','schema'} or str(z['schema'])!=SCHEMA or str(z['instance_sha'])!=b.instance_sha:raise ValueError('wrong instance/schema')
        actions=z['actions'];controls=z['actuator_controls'];offsets=z['offsets'];completed=z['completed']
        if actions.dtype!=np.float64 or actions.ndim!=2 or actions.shape[1]!=b.dim or len(actions)>b.cap:raise ValueError('invalid actions')
        if controls.dtype!=np.float64 or controls.ndim!=2 or controls.shape[1]!=b.model.nu or not np.isfinite(controls).all():raise ValueError('invalid actuator trace')
        if offsets.dtype!=np.int64 or offsets.shape!=(len(actions)+1,) or offsets[0]!=0 or offsets[-1]!=len(controls) or np.any(np.diff(offsets)<0) or np.any(np.diff(offsets)>b.nsub):raise ValueError('invalid offsets')
        if completed.dtype!=np.bool_ or completed.shape!=(len(actions),):raise ValueError('invalid completion flags')
        limited=b.model.actuator_ctrllimited.astype(bool)
        if np.any(controls[:,limited]<b.model.actuator_ctrlrange[limited,0]) or np.any(controls[:,limited]>b.model.actuator_ctrlrange[limited,1]):raise ValueError('actuator limits')
        for i,action in enumerate(actions):
            if result['first_success_index'] is not None:raise ValueError('actions after success')
            b.validate(action.tolist());before=float(b.data.time)
            try:info=b.step(action,controls[offsets[i]:offsets[i+1]])
            finally:
                result['physics_steps']+=len(b.frame);result['completed_controls']=b.completed
            if not completed[i]:raise ValueError('online incomplete control replayed as completed')
            if info['success']:result['first_success_index']=i
            if writer and (i+1)%10==0:
                renderer.update_scene(b.data,camera=b.cameras[0]);writer.append_data(renderer.render())
        result.update(success=b.result()['success'])
    except Exception as exc:
        result.update(error_type=type(exc).__name__,error=str(exc),success=False)
        traceback.print_exc()
    finally:
        result['state_sha']=b.hash()
        np.savez_compressed(a.result+'.state.npz',integration=b.state())
        Path(a.result).write_text(json.dumps(result,indent=2)+'\n')
        if writer:writer.close();renderer.close()
        b.close()
if __name__=='__main__':main()
