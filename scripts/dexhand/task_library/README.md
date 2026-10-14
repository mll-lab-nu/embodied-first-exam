# DexHand task library

Each logical task owns one folder. Both Harbor modes are generated from the same task specification and scene.

```text
task_library/
  index.json
  essential_cube_layer/
  essential_held_joystick/
  essential_cube_reorient/
  essential_rotary_gait/
  essential_pen_regrasp/
  essential_two_object/
```

Every task folder contains the same entry points:

| File | Ownership and purpose |
|---|---|
| `task.json` | Frozen initialization, ordered goals, native safety bounds and contact holds |
| `scene.py` | That task's physical scene, reset and feature extraction |
| `assets/manifest.json` | Provenance and an explicit `runtime_files` list |
| `assets/` | Licensed object meshes, collision hulls, textures and attribution |
| `render.json` | Camera, presentation material overrides and framing |
| `README.md` | Task explanation and documented modeling approximations |

Shared hand mechanics, grading and replay remain in `../shared/`. The runtime selects the registered task-owned scene;
the generator copies scene modules and declared object assets into self-contained Harbor directories. The generated
privileged and standard twins are outputs under the repository `tasks/`, not additional authoring sources.

The ordered `index.json` registers scene modules and whether objects are free. Add a new task folder and register it here;
shared runtime code does not need a task-specific branch. Authors can edit separate folders in parallel.

Meshes and textures must have a redistribution license and a SHA-256 manifest. Keep downloaded upstream references and
training/checkpoint code outside this library. Generated copies must contain every asset needed offline.
Asset checksums describe the original authoring files. During runtime packaging, the generator removes only trimesh's
automatic code-URL banner from the first OBJ comment line; vertices, faces, normals, UVs and separate artist credits
remain byte-identical. This keeps converter metadata out of distributed agent files without changing frozen assets
or the geometry used for a film.

Use `python3 scripts/dexhand/sync_essential_catalog.py --check` to verify the frozen catalog and
`python3 scripts/dexhand/generate.py --check` to verify generated task copies.

```bash
python3 scripts/dexhand/library.py --check
python3 scripts/dexhand/library.py --json
python3 scripts/dexhand/sync_essential_catalog.py
python3 scripts/dexhand/generate.py --refresh-manifest
```

For parallel work, assign complete task folders to separate authors. Keep shared changes with one integrator and
register new IDs in `index.json` after resolving scene/module naming. Freeze each folder before recording final
evidence. A new mesh changes the contact problem: derive and independently replay successful hand targets rather than
reusing an old video or updating its metadata. High-quality films use `../presentation/` and exact native pose samples;
the evaluated simulation and fast observations continue to use the pinned MuJoCo runtime.

`generate.py --only-family <id> --refresh-manifest` updates one family's two modes and preserves other authors' generated
directories. Run the catalog synchronization before it; both modes always receive the same frozen task entry.
