# Task 12 reference reconstruction

Source: [Puzzle guy — Remove the ring from the puzzle](https://www.youtube.com/shorts/yZv8eUWIF-8).
Reviewed actions and uncertainties are recorded in [source.json](source.json).

The maintained sources are the task generator and `configs/slotted_post_ring_preview.yaml`.
Generated OBJ/GLB meshes, cord centerline, reports and hashes are placed in the run's
`assets/` directory. Texture maps reuse the existing CLASSIC wood assets; they are
embedded in each generated GLB, so archived meshes do not depend on the texture path.

This version is a static visual reconstruction. It contains true mesh holes but no
deformable cord solver, active task collision geometry or terminal constraints.
All task objects are frozen, and its preview never advances simulation time.
