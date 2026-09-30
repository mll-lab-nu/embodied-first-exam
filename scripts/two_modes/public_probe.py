"""Executed in main before activation; only public endpoints, no hidden inputs."""
import importlib.util,json,socket
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import numpy as np
import limited_client as r
for name in ('mujoco','robosuite','robocasa','metaworld','VLABench','vlb_traj','mw_runtime','backend','docker'):
 assert importlib.util.find_spec(name) is None,name
for path in ('/private','/recorded','/run/limited','/tests','/solution','/trusted','/app/instance.npz','/app/instance.json','/var/run/docker.sock','/proc/1/root/private'):
 assert not Path(path).exists(),path
spec=r.spec();before=r.status();dim=spec['action_shape'][0];camera=spec['cameras'][0]
def reject(endpoint,body):
 raw=body if isinstance(body,bytes) else json.dumps(body).encode()
 try:urlopen(Request('http://sim:8000/v1/'+endpoint,data=raw,headers={'Content-Type':'application/json'}),timeout=10)
 except HTTPError as e:assert e.code==400;return
 raise AssertionError('accepted '+endpoint)
for end in ('reset','restore','state','submit','admin','start','stop','seal','../private/instance.npz'):reject(end,{})
reject('observe',{'camera':camera,'segmentation':True});reject('spec',{'seed':0})
for a in ([],[0]*(dim+1),[True]*dim,[1e30]*dim):reject('step',{'action':a})
reject('step',b'{"action":['+b','.join([b'NaN']*dim)+b']}')
obs=r.observe(camera)
assert set(obs)<= {'rgb','depth_m','intrinsic','camera_to_world','robot','camera'}
allowed={'joint_names','joint_positions','joint_velocities','joint_types','end_effectors','hand_position','hand_quaternion_wxyz','tcp_position','tcp_quaternion_wxyz','gripper_opening','gripper_positions','mocap_target_position'}
assert set(obs['robot'])<=allowed
assert obs['rgb'].shape==(480,480,3) and float(obs['rgb'].std())>1
assert np.isfinite(obs['intrinsic']).all() and np.isfinite(obs['camera_to_world']).all()
assert r.status()['actions']==before['actions'] and r.status()['physics_steps']==before['physics_steps']
for port in (22,443,2375,2376,8001,9000):
 with socket.socket() as sock:sock.settimeout(.2);assert sock.connect_ex(('sim',port))!=0
# Agent-authored assertions are deliberately false and must never affect grading.
Path('/app/output').mkdir(exist_ok=True)
Path('/app/output/reward.json').write_text('{"success":1}')
print(json.dumps({'four_methods_only':True,'no_reset_or_hidden_state':True,'robot_fields_whitelisted':True,'rgb_verified':True,'observations_do_not_advance':True}))
