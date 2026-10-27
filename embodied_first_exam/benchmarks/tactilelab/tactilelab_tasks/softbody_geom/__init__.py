"""Pure-numpy geometry, configs, scene builders, scripted plans and success metrics of the soft / dough / FEM tasks.

This package is imported by BOTH processes: the Isaac side (``tactilelab_tasks.backends.newton_client`` and the task
modules) and the Newton sidecar (``sidecar/worlds``).  Nothing here imports ``newton``, ``warp``, Isaac or torch at
module level; everything is numpy and the standard library.  The sidecar imports it under the top-level name
``softbody_geom`` (``sidecar/server.py`` puts ``tactilelab_tasks/`` on ``sys.path``), so all imports inside this package
are relative.

Frames and units: env-local metres, z up.  Quaternions in this package and on the sidecar wire are **xyzw** (Newton's
order); the rest of ``tactilelab_tasks`` uses wxyz, convert with :func:`spec.quat_wxyz_to_xyzw` / :func:`spec.pose7_wxyz_to_xyzw`.

Modules
    spec            quaternion / pose helpers, cloth sheet and sleeve meshes, cable polylines, soft-world config defaults
    soft_scenes     the cloth task worlds (cloth_edge_feed, cloth_fold_half) and the gripper collider list
    dough_scene     MPM particle blobs, pose interpolation
    dough_metrics   column heights, press / fill reports
    dough_task      DoughScene container, press / fill scene builders, tray_boxes
    dough_pinch     direct-pad dough scenes (pinch ridge, straddle push), pad_tools, pinch_report
    materials       MPM material presets
    surface         marching-cubes dough surface (needs scipy + scikit-image; Isaac side only)
    tools           dough tool collider descriptions (press, stamp, scraper)
    plug_scene      FEM plug spec, fixture boxes, particle grid, surface triangles, plug_report
    plug_pad_scene  direct-pad FEM plug scene, plug_pad_report
    plug_task       carrier-variant FEM plug scene
"""
