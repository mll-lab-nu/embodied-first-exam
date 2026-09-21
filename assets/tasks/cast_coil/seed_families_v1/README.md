# Fixed Cast Coil family cores

Three predesigned cores from the checked 9 mm mechanism representatives:
`eccentric_turn`, `split_turn_offset`, `axial_screw_turn`.
`catalog.json` binds each file by SHA-256, family and mechanism parameter.

The sampler loads these files; it does not synthesize a new turning channel on
each episode. Family-specific outer profiles are exact subtractive box CSG,
followed by a coupled face/depth transform of geometry and relative motion.
The current supported profile additions are **0 or 1.5 mm**: the intermediate
0.75 mm cut produced a non-manifold corner on the axial core and is excluded.

These files are prototype solids, not verified commercial replicas. Historical
core checks and individual physical runs do not certify the entire random
parameter domain. Each generated candidate must pass its own checks.

See [generator and validation](../../../../docs/develop/tasks/cast_coil_seed_generator_zh.md).
