# Horseshoe Ring physical family library v2

This is a generator input library, independent of demo directories and dataset writers.

- `library.json`: three designed approach families, one fixed classic-circle prototype, conditional proposal limits and admission rules.
- `paired_anchors.json`: concrete parameters and provenance for one complete 2 ms gravity/contact success per family. F1/F2 use small similarity changes; F3 uses original dimensions. The original template and initializer remain in `../tutorial_solvable_v3/`.
- `route_references.json`: normalized FK of each designed entry corridor, quantitative separation and a same-camera visual review. The adaptive wrist-alignment segment is separate from the family signature.

A new request chooses a family, samples around that family's paired anchor using the shared `VariantRng`, solves initialization/fold IK, then performs and verifies physical execution. All geometry dimensions scale together. Color is render-only. These bounded neighborhoods are proposals, not continuous physical solvability certificates; failed candidates must be rejected, with a finite retry limit and unchanged family.

The parent `source_directory` fields are provenance only. Generation reads the packaged templates/initializer and this library; it never loads plans or assets from those historical run directories. Runtime outputs belong to the caller. No HTML, videos or H5 files are produced by the parameter sampler.

Non-circular rings, waisted and broad-U shoes are deferred: their old geometric witnesses do not certify physical robot execution. The legacy `family_space_v1` nine-slot plan is not promoted into nine physical variants.

See [the generator contract and validation](../../../../docs/develop/tasks/horseshoe_ring_variant_generator_zh.md).
