# Asset licences (abc-sim image)

`/opt/abc/abc_sim` is ABC Sim's simulator package, Apache-2.0 (`/opt/abc/LICENSE`), from github.com/amazon-far/abc at d0832d1. The meshes and textures under `/opt/abc/abc_sim/models/assets/` are the subset of its simulator asset packages that this benchmark's frozen scenes use; their licences and credits, as upstream states them (its README, "Simulator asset licenses"), follow. Per-object credits ship inside the packages (`OFFICE_ATTRIBUTIONS.md`, the package `README.md` and `LICENSE` files).

The simulator asset packages bundle meshes and textures from the sources below. abc-side processing — recentering, rescaling, trimesh re-export, resized
textures, custom convex collision decompositions, and retuned MJCF wrappers —
does not change the upstream licenses. Per-object credits ship inside the
packages where noted.

| Source | License | Where it is used |
| --- | --- | --- |
| [RoboCasa](https://github.com/robocasa/robocasa) objaverse pack: objects curated from [Objaverse 1.0](https://objaverse.allenai.org/objaverse-1.0), originally by individual Sketchfab creators | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (RoboCasa asset release) | `mug`; the object libraries in `task_put_relative`, `task_grab_clutter`, and `task_conveyor_pick`; mug variants in `task_mug_flip` and `task_mug_tree`; plates in `task_dishrack`; bottles in `task_water_bottles`; objects in `task_multi_drawer_search` and `task_inhand_transfer` |
| RoboCasa lightwheel pack: objects by [LightWheel AI](https://www.lightwheel.ai/) | CC BY 4.0 (RoboCasa asset release) | object variants in `task_put_relative`, `task_grab_clutter`, `task_conveyor_pick`, `task_inhand_transfer`, and `task_multi_drawer_search`; dish racks in `task_dishrack` |
| RoboCasa aigen pack: AI-generated objects ([Luma.ai](https://lumalabs.ai/)) | CC BY 4.0 (RoboCasa asset release) | `bowl` |
| [Google Scanned Objects](https://github.com/kevinzakka/mujoco_scanned_objects) | CC BY 4.0 | Two office objects in `task_multi_drawer_search`; per-object credits in the package's `OFFICE_ATTRIBUTIONS.md` |
| Sketchfab creators, individually credited | CC BY 4.0 | Six office objects in `task_multi_drawer_search` (see `OFFICE_ATTRIBUTIONS.md`); the box and crate in `task_bins` (see the package `README.md`); the Fujiya tin in `task_chess` by [Vision Fountain](https://sketchfab.com/visionfountain); [`bin`](https://sketchfab.com/3d-models/bin-8984db4f15284436ab704919327ca251) by [AlaPasta](https://sketchfab.com/alapasta); [`blocks`](https://sketchfab.com/3d-models/wooden-alphabet-blocks-5f8dfddbbc7d468784ca014378f7e5fe) by [Cherryvania](https://sketchfab.com/mikequeen123); [`dustpan`](https://sketchfab.com/3d-models/dustpan-d91eae20c02a4741aeb889246b417ae4) by [c_irby_paint](https://sketchfab.com/cirby2180); [`garbage_can`](https://sketchfab.com/3d-models/garbage-can-trashcan-bin-926826667ff04fb09a0907bbec54c766) by [BlackCube](https://sketchfab.com/blackcube4), including its copy in `task_water_bottles`; [`paper_ball`](https://sketchfab.com/3d-models/paper-ball-8afd2bfbe8c14fad937f768617d55f9e) by [ianshanewise](https://sketchfab.com/ianshanewise); [`tray`](https://sketchfab.com/3d-models/plastic-tray-e9b536258ae4499abec7b31ebd231daf) by [Aullwen](https://sketchfab.com/Aullwen) |
| [freepoly.org](https://freepoly.org/) | CC0 | The yellow tin in `task_chess` |
| [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO) | MIT | The `short_cabinet` drawer fixture in `task_multi_drawer_search`; license copy in the package |
| [i2rt YAM](https://github.com/i2rt-robotics) | MIT | The `i2rt_yam` robot model package; license copy in the package |
| This project | Apache-2.0 | Everything else, modeled or scanned in-house: `ball_sorting_toy`, `brush`, `brush_flat`, `building_blocks`, `chess`, `cup_stacking`, `dishrack`, `drawer`, `flexible_gripper`, `hand_brush_smooth`, `jenga`, `letters`, `marker`, `mug_tree`, `new_brush`, `plate`, the generated `task_nuts_bolts` meshes, the conveyor fixture in `task_conveyor_pick`, the baked plate/rack originals in `task_dishrack`, `tin_2` in `task_chess`, and all task-tuned MJCF wrappers and collision meshes |

