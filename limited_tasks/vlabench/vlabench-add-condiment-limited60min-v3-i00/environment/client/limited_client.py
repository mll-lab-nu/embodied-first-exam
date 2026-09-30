"""Public single-episode API. No state/IK/reset/submit or management endpoint."""
import base64
import io
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
import numpy as np


def _call(path,body):
    request=Request('http://sim:8000/v1/'+path,data=json.dumps(body,allow_nan=False).encode(),
                    headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=90) as response: return json.load(response)


def spec(): return _call('spec',{})


def observe(camera=2):
    value=_call('observe',{'camera':camera})
    with np.load(io.BytesIO(base64.b64decode(value['npz_base64'])),allow_pickle=False) as obs:
        result={**{k:obs[k] for k in obs.files},'robot':value['robot']}
    # Public RGB only. Host Terminus vision bridge reads these main-container images.
    from PIL import Image
    folder=Path('/app/output'); folder.mkdir(exist_ok=True)
    temp=folder/f'limited-view-{camera}.tmp'
    Image.fromarray(result['rgb']).save(temp,format='JPEG',quality=90)
    temp.replace(folder/f'limited-view-{camera}.jpg')
    (folder/f'limited-view-{camera}.json').write_text(json.dumps({'camera':camera,'observed_at':time.time()}))
    return result


def step(action): return _call('step',{'action':np.asarray(action).tolist()})


def status(): return _call('status',{})
