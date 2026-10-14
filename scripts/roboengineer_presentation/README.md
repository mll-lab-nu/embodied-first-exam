# Offline PR presentation renders

This operator tool re-renders eight existing reference-controller demonstrations in Blender. It does not change the benchmark, train a controller, run a coding agent, or replace the observations delivered to an agent. Keep all exported poses, geometry, private records and render intermediates outside task packages and outside Git.

The eight objectives are Neural Fly, Neural Landing, AnyCar multi-surface tracking, G1 terrain walking, and Go2 attitude / weave / forward jump / yaw jump. The selected G1 case succeeds, but both G1 held-out banks remain partially solved. The three unsolved Go2 reference attempts retain their original failed motion and are labeled accordingly.

## Pipeline

1. `capture.py` reads archived drone trajectories and replays the frozen car, G1 and Go2 policies in CPU MuJoCo 3.5.0. The latter six replays must match the original state hash, metrics and feedback exactly. It samples states at 25 Hz, exports the compiled visible meshes, UVs and per-geometry transforms, and verifies uniform timestamps. AnyCar's reset/settling pre-roll is discarded when simulation time resets. Forward kinematics for the export runs only after the physics rollout finishes.
2. `render_blender.py` loads these numeric exports in Blender 4.5.3 LTS. It applies the recorded transforms directly, without running Blender physics or interpolating/retargeting motion. Cycles uses one OptiX GPU, 32 samples and GPU denoising. The new studio, PBR materials, lights, depth of field, camera paths and public target markers are presentation changes. Source obstacle and terrain geometry is retained. Drone geometry comes from the existing Skydio visual profile and the existing procedural Neural Landing model; this is not a change in aerodynamic calibration. Skydio's existing rotor-blur disk meshes receive a translucent presentation material; their vertices and transforms remain unchanged.
3. `deliver.py` adds explicit provenance/outcome labels, encodes the complete clips at 1920 × 1080 / 25 fps / real-time speed, verifies frame counts, and fully decodes every MP4. It also produces a 52-second montage of consecutive excerpts, a local HTML gallery and a JSON manifest. The public delivery contains no exported poses, episode banks or hidden plant parameters.

The renderer refuses to resume into a directory produced by a different renderer source, capture or quality setting. Source-record and renderer hashes accompany each output. A changed visual configuration needs a new output directory.

Neural Landing's `force-driven-rotors/1` presentation revision exports all four motor histories separately. RPM is reconstructed from archived motor force using the existing nominal thrust coefficient, and blade phase is integrated at the original 100 Hz before video sampling. Opposite pairs counter-rotate; the recorded motor decay brings them to rest after landing. RPM is model-derived, not a new physical measurement, and initial blade phases and 48-sample shutter blur are cosmetic. The renderer alters only the named visual blades; archived body states, scores and canonical feedback are unchanged. The older capture format remains available for exact historical reproduction.

## Reproduce

Supply local operator evidence and prepared assets explicitly. These commands intentionally contain placeholders, not developer-specific paths:

```bash
MUJOCO_GL=osmesa CUDA_VISIBLE_DEVICES= OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
python -m scripts.roboengineer_presentation.capture \
  --evidence "$EVIDENCE_ROOT" --landing-runs "$LANDING_RUNS" \
  --assets "$PUBLIC_CONTROL_ASSETS" --go2-assets "$GO2_ASSETS" \
  --skydio-assets "$SKYDIO_ASSETS" --out "$PRESENTATION_ROOT/captures"

python -m scripts.roboengineer_presentation.render_all \
  --blender "$BLENDER_453" --root "$PRESENTATION_ROOT" --gpu 0
```

The capture interpreter needs MuJoCo 3.5.0, NumPy 2.3.1, Pillow and the existing task runtime dependencies. Set `LD_LIBRARY_PATH` if OSMesa is installed in a user-local directory. Encoding requires FFmpeg with libx264, ffprobe, Pillow and DejaVu Sans. Blender uses its own bundled Python/NumPy. The portable official Blender 4.5.3 Linux x64 archive used for the initial delivery has SHA-256 `975c58fcb244273838534bba771e64ad87739216b0f9b39a888531a49a72d845`.

For one still, run Blender with `--python render_blender.py -- --capture <capture-dir> --output <preview-dir> --preview <frame-index>`. `capture --only` and `render_all --only` allow independent task processing. `deliver --collection-only` rebuilds the gallery and montage from already encoded full videos.

### Extra AnyCar ramp-jump demo

The optional ninth demo uses the frozen ramp-jump prototype at commit `8f798faae74458bc51ed280fdb499b889f049b3d`. Export that commit's `scripts/control_transfer` tree to an operator-only directory and supply its archived `ramp-jump-v1` evidence:

```bash
python -m scripts.roboengineer_presentation.capture_jump \
  --source-root "$FROZEN_JUMP_SOURCE" --evidence "$JUMP_EVIDENCE" \
  --out "$JUMP_PRESENTATION"
python -m scripts.roboengineer_presentation.render_all \
  --blender "$BLENDER_453" --root "$JUMP_PRESENTATION" --gpu 0 --only anycar-jump
```

The default selection is instance 0, held-out case 0. Capture requires exact state, policy, dynamics, metrics and feedback agreement with the archived record before exporting 200 poses. The complete eight-second clip plays at real time; the camera shows the launch, physical gap, descending landing ramp and stop. The studio foundation stays below the source pit at z=-1.2 m. This scripted reference replay is additional to the original eight-objective collection and does not establish native Harbor or coding-agent acceptance. Its separate provenance JSON and download preserve the original montage and ZIP.

For an explicitly modified demonstration, add `--showcase-config <operator-json>` and `--reference-dir <saved-run-directory>` to `capture_jump`. The config contains `revision`, `course`, `policy`, `plant_seed`, `friction`, `initial_y`, `initial_yaw` and `noise_seed`; these are inputs to the frozen evaluator's `run` function. Run and save that configuration first, then capture verifies exact agreement in a fresh process. The published clip is marked a custom showcase, with `benchmark_case=false`; it is not a held-out benchmark result. Keep the config, private record and pose export outside the public video package.

The user-requested `wide-gap-showcase/2` changes the gap from 0.5620 m to 1.40 m and the controller's approach/braking settings. Car physics, ramp slopes and success predicates are unchanged. The launch-speed coefficient is 5.0 m/s, but the measured takeoff speed is 3.8605 m/s (3.7303 m/s horizontally), compared with 2.8481 m/s previously. The successful custom episode takes off at 1.314 s and lands at 1.630 s; it is shown at real-time speed. This local demonstration search provides no new benchmark or agent score.

## Scope and interpretation

The optional `anycar-drift-v3` clip is captured with `capture_drift --evidence <drift-feedback-v1> --out <presentation-root>` and rendered with `render_all --only anycar-drift-v3`. Its entire nominal record must replay exactly before exporting 400 frames at 25 Hz. Both the overlay and gallery retain the frozen limitations: 0/6 adaptation, 1/20 held-out and 1/10 additional nominal-noise trials, despite the selected nominal score of 64.70. The original 50 fps MuJoCo replay remains separately available; neither presentation replaces the canonical 10 fps observations.

- These clips show scripted or trained reference policies, not Astra/Luna/Sol or other coding-agent scores.
- Neural Fly's selected vector-wind case uses the benchmark's synthetic drag extension. Skydio appearance does not make the model paper-calibrated directional aerodynamics.
- AnyCar's selected compact Silverstone-inspired route includes documented smoothing and shape changes; it is not an exact historical F1 outline.
- G1's selected positive case does not establish full-bank solvability. Go2's three development references remain unsolved.
- New studio cameras can show perspectives unavailable in the canonical feedback. Presentation videos must not be fed back into a benchmark trial or described as the videos an agent watched.
- No native Harbor, physical robot, isolation or new control-performance claim follows from this rendering run.

Asset provenance and license pins remain in the existing task asset preparation code and operator manifests. The rendering tool does not download or redistribute meshes. The video delivery should include the existing Unitree/Skydio notices and F1DB attribution for the route derivative.
