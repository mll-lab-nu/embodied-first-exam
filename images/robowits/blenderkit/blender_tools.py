"""Blender helper for the image build (blender --background --python blender_tools.py -- scale <factor> <src> <dst>):
uniformly scale a model about its centre (which preprocessing put at the origin), exporting with the same glTF
settings as RoboWits' assets/blender_preprocess.py."""
import sys
import bpy

EXPORT = dict(export_format="GLB", use_visible=True, export_apply=True, export_materials="EXPORT",
              export_draco_mesh_compression_enable=False)

args = sys.argv[sys.argv.index("--") + 1:]
assert args[0] == "scale", args
k, src, dst = float(args[1]), args[2], args[3]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
for o in bpy.context.scene.objects:
    if o.parent is None:
        o.scale = (o.scale[0] * k, o.scale[1] * k, o.scale[2] * k); o.location = (o.location[0] * k, o.location[1] * k, o.location[2] * k)
bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bpy.ops.export_scene.gltf(filepath=dst, **EXPORT)
print(f"scale: {src} x{k} -> {dst}", flush=True)
