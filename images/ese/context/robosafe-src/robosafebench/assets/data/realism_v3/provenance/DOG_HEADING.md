# Standing dog heading correction

The original dog and its head site face +x. The standing scanned mesh instead
faces -x: the highest 15% of displayed vertices (ears/head in this pose) have
mean x=-0.314612 m while the unchanged head site is x=+0.285 m. Same-camera top
and front views independently confirm this semantic mismatch.

`dog_heading.apply(stage)` changes only the standing dog's visual placement:
180 degrees of yaw about the actual drawn mesh bounding-box centre. It does not
rewrite OBJ positions/normals/UVs/faces, PNG pixels, source packs, colliders, or
sites. The pivot preserves all displayed bounds, within 2.5e-8 m after MuJoCo's
float conversion. The head-height vertex subset is then x=+0.312344 m, correctly
on the same side as the original head site. Fur choices select this same mesh.

The lying mesh already faces +x (head-height subset x=+0.304926 m), so it remains
unchanged. This is a deliberately pose-specific correction: the two variants
have different original rotations and must not both be blindly rotated.

`prepare.py` applies the helper after compound fixes for a fresh run. For an
already prepared owned candidate, on a compute node:

```sh
python scripts/realism_cpu/dog_heading.py --pilot /path/to/owned/pilot_final
```

An optional `--clone-to /fresh/private/pilot` makes an isolated trial first.
Applying the helper twice is idempotent. The previous frozen catalogue stages
must not be edited.

Both poses pass all 261 checked physical arrays, including all 11 physical
geoms and original sites/cameras/options. A 50-step passive replay has exactly
zero qpos and qvel difference for both. An independent reviewer accepted the
same-camera front/top heading correction and the unchanged lying direction.
Artifacts are in `geometry_agent/dog_heading/{before,after,standing,lying}`;
`validation.json` additionally checks source-pack file hashes.

This validates heading semantics and preservation of physical behaviour. It
does not establish a close anatomical fit to every conservative collider or
photographic appearance. The lying rig deformation, texture seams, and missing
original collar colour remain visible limitations.
