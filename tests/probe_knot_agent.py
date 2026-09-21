"""Opt-in CUDA FEM protocol smoke: home hold and tiny arm motion, not untying."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from topogym.agent_bridge.client import Client


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=args.output.resolve(); root.mkdir(parents=True,exist_ok=False)
    package=root/'solver'
    subprocess.run([sys.executable,'-m','topogym.agent_bridge.local','--task','knot_untying',
        '--backend','cuda','--output',str(root/'episode'),'--package',str(package),'--no-allow-internet'],check=True)
    client=Client(json.loads((package/'bridge_config.json').read_text())['url'])
    try:
        state=client.state()
        assert state['state']=='ready' and state['tick']==0
        previous=client.request('/artifacts/initial/manifest.json')['frames'][0]
        assert len(previous['cameras'])==4
        assert set(state['observation'])=={'robot','camera_poses','grasp_assistance'}
        try:
            client.submit('env.step({"left":{"qpos":[0]}})',expected_segment=1,request_id='invalid')
            raise AssertionError('Invalid action accepted')
        except ValueError:
            assert client.state()['tick']==0
        codes=['env.step({}, steps=2)',
            'q=obs["robot"]["left"]["arm_qpos"]\nenv.step({"left":{"qpos":[q[0]+0.0003,q[1],q[2],q[3],q[4],q[5]]}},steps=2)',
            'env.step({"left":{"gripper":0.037}},steps=2)']
        for i,code in enumerate(codes,1):
            result=client.submit(code,expected_segment=i,request_id=f'probe{i}')
            assert result==client.submit(code,expected_segment=i,request_id=f'probe{i}')
            assert result['state']=='ready',client.state()['reason']
            m=client.request('/artifacts/'+result['manifest'])
            assert len(m['frames'])==3 and all(len(f['cameras'])==4 for f in m['frames'])
            first=m['frames'][0]
            assert first['tick']==previous['tick'] and first['observation']==previous['observation']
            assert [v['sha256'] for v in first['cameras'].values()]==[v['sha256'] for v in previous['cameras'].values()]
            previous=m['frames'][-1]
        assert previous['observation']['robot']['left']['arm_qpos']!=state['observation']['robot']['left']['arm_qpos']
        report=dict(scope='6 control ticks / 24 IPC substeps, no grasp or untying',passed=True,ticks=6,seconds=.03,
            checks=['four initial views','no private state','invalid action no motion','idempotency','segment continuity','joint response'],
            source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [
                Path('topogym/tasks/knot_untying/agent_adapter.py'),Path('topogym/agent_bridge/fem_robot_adapter.py'),
                Path('topogym/world/genesis_ipc_vertex_constraints.py')]})
        (root/'probe_report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    finally:
        client.request('/v1/shutdown',dict(reason='Operator protocol probe complete; no untying attempted'))


if __name__=='__main__':
    main()
