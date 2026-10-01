"""Textures PIL refuses to decode (DecompressionBombError: more than 178,956,970 pixels; two BlenderKit models embed a
16667 x 16668 PNG) make RoboWits' scene build crash. Only those images are downscaled, inside the GLB: the image bytes
are replaced and the binary chunk repacked, every other buffer view (geometry, the other textures) is copied unchanged.
  big_textures.py list <dir>            GLBs under <dir>/*/obj.glb with such a texture (one per line)
  big_textures.py fix <max_side> <glb>... downscale those textures to <max_side> px on the longer side, in place"""
import glob, io, sys
from PIL import Image
import pygltflib

LIMIT = 2 * Image.MAX_IMAGE_PIXELS   # PIL's DecompressionBombError threshold
Image.MAX_IMAGE_PIXELS = None


def images(g, blob):
    for im in g.images or []:
        if im.bufferView is not None:
            bv = g.bufferViews[im.bufferView]; o = bv.byteOffset or 0
            yield im, blob[o:o + bv.byteLength]


def too_big(data):
    w, h = Image.open(io.BytesIO(data)).size
    return w * h > LIMIT


def fix(path, side):
    g = pygltflib.GLTF2().load_binary(path); blob = g.binary_blob()
    assert all(bv.buffer == 0 for bv in g.bufferViews), f"{path}: more than one buffer"
    new = {}
    for im, data in images(g, blob):
        if too_big(data):
            img = Image.open(io.BytesIO(data)); s = side / max(img.size)
            img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
            fmt = "JPEG" if im.mimeType == "image/jpeg" else "PNG"
            out = io.BytesIO(); (img.convert("RGB") if fmt == "JPEG" else img).save(out, fmt, **({"quality": 95} if fmt == "JPEG" else {}))
            new[im.bufferView] = out.getvalue()
    parts, off = [], 0
    for i in sorted(range(len(g.bufferViews)), key=lambda i: g.bufferViews[i].byteOffset or 0):
        bv = g.bufferViews[i]; o = bv.byteOffset or 0
        data = new.get(i, blob[o:o + bv.byteLength])
        pad = (-off) % 4; parts.append(b"\0" * pad); off += pad   # 4-byte aligned views keep every accessor aligned
        bv.byteOffset, bv.byteLength = off, len(data); parts.append(data); off += len(data)
    g.buffers[0].byteLength = off
    g.set_binary_blob(b"".join(parts)); g.save_binary(path)
    print(f"fix: {path}: {len(new)} texture(s) downscaled to {side} px", flush=True)


if sys.argv[1] == "list":
    for f in sorted(glob.glob(f"{sys.argv[2]}/*/obj.glb")):
        g = pygltflib.GLTF2().load_binary(f)
        if any(too_big(d) for _, d in images(g, g.binary_blob())):
            print(f)
elif sys.argv[1] == "fix":
    for f in sys.argv[3:]:
        fix(f, int(sys.argv[2]))
