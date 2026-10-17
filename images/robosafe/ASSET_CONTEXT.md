The context generator removes only the byte-identical package copy of
`assets/third_party`. It checks both complete trees before removal and seals
every relative path, size and SHA256. The image restores the package tree at
`robosafebench/assets/data/third_party` after the existing pinned public MuJoCo
Menagerie fetch and before wheel installation. Both installed asset locations,
including Spot, retain their original files and bytes. Fonts, bigym2 resources
and license notices remain in the single committed root copy.

The development source audit found 282 duplicate files totaling 190,189,625
bytes, including 53,407,810 bytes of Spot files already available from the
pinned Menagerie source. These are context savings, not removal of a robot or
an installed rendering asset. The staged and restored manifests must be checked
again for the final source pin and image; this change alone grants no image or
task admission.

The complete tracked v3 material pack is vendored in the native package snapshot
for offline reproduction: 688 files totaling 392,002,816 bytes, each bound by
the context manifest and its original asset manifest/license. No new public host
is selected and no CPU PBR pipeline runs in the benchmark. Refresh the committed
context only from the pinned RoboSafeBench source in `source.env`; an old context
and a new source pin must not be built together.

The complete native Python package is retained, including server, CLI, harness
and diagnostics modules. No API or model process is started by including these
files. The final context must not be pruned into a package that differs from
the complete canonical package whose source and installed files are audited.

`verify_material_pack.py` accepts a local/downloaded tar plus independently
pinned tar and manifest SHA256 values. It verifies every member before installing
into an absent destination. It chooses no remote URL or public destination.

The installed runtime uses an empty `ROBOSAFEBENCH_THIRD_PARTY` override and
`ROBOSAFEBENCH_ASSET_PROFILE=realism_v3`. The native package must resolve its
third-party files inside `robosafebench/assets/data/third_party`; the build checks
that path and the visual profile before its native smoke check.
