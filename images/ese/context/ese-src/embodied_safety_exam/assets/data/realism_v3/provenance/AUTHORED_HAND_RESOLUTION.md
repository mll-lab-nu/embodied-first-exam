Hand skin packing now preserves the actual source diffuse resolution. The write
limit is raised only to the current hand image's existing size, then restored;
other pack textures keep their existing policy. Images are never enlarged.

The six current hand variants use 2048x2048 MakeHuman source images. They had been
reduced to 1024x1024. A private compute-node rebuild verified, for all six variants,
that OBJ bytes including positions, faces, UVs and normals were identical, and
that the full-resolution pixels exactly equaled the source image multiplied by
its glTF color factor. Downsampling the rebuilt image reproduced the old pack
pixel for pixel, confirming color and orientation.

The paired compiled scenes preserved all geometry, cameras, material properties
and physical data. Their snapshot images also passed the exact downsample check;
261 physical arrays and 50 passive simulation steps matched. The 960px, 48-sample
PBR comparison shows a subtle texture-detail change. This restores existing image
data; it does not supply the missing authored skin normal or roughness maps.

`repair_skin_resolution.py` creates a fresh private pilot and performs the pack
checks. `review_skin_resolution.py` validates a compiled scene pair. Both run on
Slurm compute nodes. Review artifacts are under
`historical-source://asset-build/geometry_agent/skin/`: the final default pack
check is `hand_authored_default/validation.json`, the scene check is
`hand_pair_validation.json`, and the paired images are `hand_1k/pbr.png` and
`hand_2k/pbr.png`.
