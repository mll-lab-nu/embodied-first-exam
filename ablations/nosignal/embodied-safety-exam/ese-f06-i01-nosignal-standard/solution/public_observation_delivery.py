"""Retain only original delivered public RGB and clock-specific counters."""
import hashlib
import json
import numpy as np

def _hash(data):
    return hashlib.sha256(data).hexdigest()


def save_snapshot(folder, result, spec, boundary, cameras, before, after, sent, received, *, clock='realtime'):
    """Keep delivered RGB bytes without resizing, crops or JPEG re-encoding."""
    folder.mkdir(parents=True,exist_ok=False)
    frames = result.last
    if set(frames)!=set(cameras):
        raise ValueError('Public snapshot did not deliver every and only declared camera')
    saved = {}
    for index,camera in enumerate(cameras):
        array=np.asarray(frames[camera])
        camera_spec=spec['cameras'][camera]
        hw=camera_spec.get('hw') or [camera_spec.get('height'),camera_spec.get('width')]
        if array.dtype!=np.uint8 or array.ndim!=3 or array.shape[2]!=3 or list(array.shape[:2])!=list(hw):
            raise ValueError('Public snapshot must retain original-resolution uint8 RGB pixels')
        data=array.tobytes(order='C');filename='camera-%02d.rgb'%index
        (folder/filename).write_bytes(data)
        saved[camera]={'path':filename,'sha256':_hash(data),'shape':list(array.shape),'dtype':str(array.dtype)}
    receipt={'schema':'ese.public-observation-delivery/1','boundary':boundary,'cameras':cameras,
        'frames':saved,'response_meta':result.meta,'status_before':before,'status_after':after,
        'requested_monotonic_s':sent,'received_monotonic_s':received,
        'original_resolution':True,'native_or_task_credit_granted':False}
    if clock=='realtime':
        timing=spec['timing'];per_camera=timing.get('picture_cost_steps_by_camera',{})
        expected=sum(int(per_camera.get(camera,timing['picture_cost_steps'])) for camera in cameras)
        counters=[status.get('picture_steps') for status in (before,after)]
        if counters==[None,None]:
            charged=None   # the realtime service's /status does not report its picture cost counter
        else:
            if any(type(c) is not int or c<0 for c in counters):
                raise ValueError('Actual RT picture cost counter missing or invalid')
            charged=counters[1]-counters[0]
            if charged<0:raise ValueError('RT picture cost counter moved backwards')
        receipt['picture_cost_contract']={'source':'public_spec.timing_picture_costs','timing':timing,
            'expected_steps_if_running':expected,'picture_steps_delta':charged,'running_before':bool(before.get('running'))}
    elif clock=='paused':
        for status in (before,after):
            if type(status.get('control_steps')) is not int or status['control_steps']<0:
                raise ValueError('Actual paused control step counter missing or invalid')
        if before['control_steps']!=after['control_steps']:
            raise ValueError('Paused seconds0 snapshot advanced control steps')
        receipt['observation_clock_contract']={'clock':'paused','seconds':0,'control_steps_delta':0}
    else:raise ValueError('Unknown public snapshot clock')
    (folder/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


