# Orbits reference initial state

Source: [SiamMandalay — Orbits solution](https://www.youtube.com/watch?v=B-EB9Q-JqXA).
The set has **four** rings and five posts; the user's 九连环 label refers to the
puzzle family, not the number of rings in this particular video.

[source.json](source.json) records inspected timestamps, apparatus topology,
authored dimensions, terminal assumptions and uncertainty. Sources are maintained
in `topogym/tasks/orbits/` and `configs/orbits_preview.yaml`. Generated watertight
OBJ meshes, textured GLBs, cord centerline, dimensions, validation and hashes live
under the run's `assets/` directory. GLBs embed the reused wood textures.

This is a frozen initial-scene reconstruction. It has no active cord dynamics,
contact or terminal attachment constraints and must not be presented as a solved
physical environment. Preview videos advance cameras only, with zero physics steps.
