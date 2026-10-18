"""Pinned public Skydio appearance; a separate render model, never a dynamics replacement."""
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET
COMMIT = 'd7b481bac63d3d600ab404ee74f7474c5efe8a67'
PROFILE = 'skydio-x2/1'
FILES = {'assets/X2_lowpoly.obj': '4d6df3d7b26676a6ade8cbc320599961321ac3e3c52474d7c98dd7adc8152411', 'assets/X2_lowpoly_texture_SpinningProps_1024.png': '24153733dd01f9ddd37a3c79fad5e24ac876228812e3a8e95f60ccd8cedb66e1', 'LICENSE': 'd42cae9a0f292b7a713597ba26e1e1e23d50df906c488f0d36fd3538af200bc1', 'README.md': '7b1b354ffdd2e9f243b211cc6ea9b5dab17614a13fc567378ded2b7676c13394'}

def asset_directory():
    return Path(os.environ.get('NEURALFLY_VISUAL_ASSETS', str(Path(os.environ.get('CONTROL_ASSETS', '/opt/control-assets')) / 'skydio_x2')))

def load_assets(folder):
    result = {}
    for name, expected in FILES.items():
        data = (Path(folder) / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Skydio visual asset checksum mismatch: ' + name)
        result[name] = data
    return result

def render_model(folder=None):
    import mujoco
    try:
        from .control_public.fly import xml
    except ImportError:
        from control_public.fly import xml
    assets = load_assets(asset_directory() if folder is None else folder)
    root = ET.fromstring(xml())
    root.set('model', 'Skydio visual only; Neural Fly surrogate dynamics')
    asset = ET.SubElement(root, 'asset')
    ET.SubElement(asset, 'mesh', name='skydio', file='assets/X2_lowpoly.obj', scale='0.01 0.01 0.01')
    ET.SubElement(asset, 'texture', name='skydio_texture', type='2d', file='assets/X2_lowpoly_texture_SpinningProps_1024.png')
    ET.SubElement(asset, 'material', name='skydio_material', texture='skydio_texture', specular='0.35', shininess='0.3')
    ET.SubElement(asset, 'texture', name='sky', type='skybox', builtin='gradient', rgb1='0.64 0.73 0.82', rgb2='0.93 0.94 0.94', width='128', height='768')
    world = root.find('worldbody')
    floor = world.find('geom')
    floor.set('rgba', '0.63 0.64 0.65 1')
    floor.set('size', '0 0 0.1')
    body = world.find('body')
    for geom in list(body.findall('geom')):
        body.remove(geom)
    ET.SubElement(body, 'geom', name='skydio_visual', type='mesh', mesh='skydio', material='skydio_material', quat='0 0 1 1', contype='0', conaffinity='0', group='2')
    return mujoco.MjModel.from_xml_string(ET.tostring(root, encoding='unicode'), assets=assets)
