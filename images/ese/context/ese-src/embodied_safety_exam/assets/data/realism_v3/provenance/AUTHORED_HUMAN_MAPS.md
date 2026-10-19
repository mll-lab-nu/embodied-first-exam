The MakeHuman clothing GLBs already contain authored tangent-space normal maps.
The OBJ pack conversion kept their UVs and diffuse images but discarded those
non-color maps. `human_pbr_maps.py` restores normal maps for shirts, trousers and
shoes only when the source material is unique and the pack retained its UVs.

Each accepted map is extracted from the exact generated GLB used by the pack.
Every compiled UV must match a source material UV within 1.2e-6; this detects an
incorrect V orientation. The image receives the same vertical row flip as the
snapshot diffuse image. Its green channel remains unchanged under the glTF +Y
normal convention. Source and exported image hashes, material identity, transform
and UV check results are recorded in the scene's material metadata.

The 2026-10-15 compute-node review restored the existing 4096x4096
`female_casualsuit02_normal.png` map on `a4_standing`. All 3,195 compiled shirt and
trouser UVs matched the source exactly. The embedded GLB image hash matched the
system asset, and the exported pixels equaled its exact vertical flip. Geometry,
camera and physics data in the paired scenes were identical; 261 physical arrays
and 50 passive simulation steps matched. The paired 960px, 48-sample images show
a subtle material change at full-body framing. This restoration does not repair
pose, support contact or anatomical detail.

The 45-variant source audit found that the hand/face skin materials used here
contain diffuse images but no authored skin normal or roughness images. The code
does not invent skin microstructure or apply a clothing atlas to skin or to the
synthetic sleeve. A separate private review restores the hand's actual 2048px
diffuse image, which had been reduced to 1024px during packing.

Run the audit, extraction and paired review on Slurm compute nodes. The review
artifacts are under `historical-source://asset-build/geometry_agent/skin/`:
`audit.json`, `person_maps/validation.json`, `person_maps/with_maps.png` and
`person_maps/without_maps.png`. The existing source pack provenance retains the
MakeHuman system assets' licensing and source records.
