"""Public-camera reference for either seat; no simulator or hidden ball state."""
import base64,json,os,time,urllib.request,urllib.error
from pathlib import Path
import wc_player as W
BASE=os.environ.get('SIM_URL','http://sim:8000')+'/'+os.environ['SEAT']
def call(ep,body=None):
    req=urllib.request.Request(BASE+'/'+ep,data=None if body is None else json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=180) as r:return json.load(r)
    except urllib.error.HTTPError as e:return json.load(e)
for _ in range(180):
    try:spec=call('spec');break
    except OSError:time.sleep(1)
else:raise RuntimeError('server did not start')
period=spec['timing']['period_s'];P=W.Player([W.Cam(c) for c in spec['cameras']])
Path('/app/output').mkdir(exist_ok=True,parents=True)
with open('/app/output/reference.jsonl','w',buffering=1) as log:
    call('start',{})
    while True:
        before=time.monotonic();s=call('status')
        if s.get('done'):break
        if s.get('phase')=='review':call('ready',dict(why='reference: review recorded',plan='fit next live flight'));continue
        if s.get('phase')!='running':time.sleep(.1);continue
        if not s.get('ball_in_play') or s.get('ball_state')!='coming to you':
            call('wait',dict(dt=.04));continue
        o=call('observe',{})
        if 'error' in o:continue
        ob=o['now'];ob['view_steps']=o['observation']['view_steps']
        img=W.decode(base64.b64decode(o['observation']['image_png_b64']))
        P.update(ob,img,ob['step'])
        # Reserve one boundary and recent planning time in the end-to-end estimate.
        act=P.decide(lambda:ob['step']+(time.monotonic()-before+.03)/period+1)
        if act:
            result=call('act',dict(type='act',**act));log.write(json.dumps(dict(step=ob['step'],act=act,result=result))+'\n')
        time.sleep(max(.005,period))
    print(json.dumps(s))
