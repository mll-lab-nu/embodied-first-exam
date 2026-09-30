"""Public single-episode Meta-World client: spec(), observe(camera), step(action), status().

There is no reset, state, submit or management endpoint. The simulator is not
installed in this container; all physics and scoring evidence stay in the sidecar.
"""
import base64
import io
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
import numpy as np


def _call(path, body):
    request = Request('http://sim:8000/v1/' + path, data=json.dumps(body, allow_nan=False).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=90) as response:
        return json.load(response)


def spec():
    return _call('spec', {})


def observe(camera='corner'):
    value = _call('observe', {'camera': camera})
    with np.load(io.BytesIO(base64.b64decode(value['npz_base64'])), allow_pickle=False) as obs:
        result = {**{k: obs[k] for k in obs.files}, 'robot': value['robot']}
    # Public RGB only, for Codex's native image viewer.
    from PIL import Image
    folder = Path('/app/output'); folder.mkdir(exist_ok=True)
    temp = folder / f'limited-view-{camera}.tmp'
    Image.fromarray(result['rgb']).save(temp, format='JPEG', quality=92)
    temp.replace(folder / f'limited-view-{camera}.jpg')
    (folder / f'limited-view-{camera}.json').write_text(json.dumps({'camera': camera, 'observed_at': time.time()}))
    return result


def step(action):
    # No client-side clipping or reshaping; the service validates and records.
    return _call('step', {'action': np.asarray(action, dtype=np.float64).tolist()})


def status():
    return _call('status', {})
