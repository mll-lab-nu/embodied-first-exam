# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.11.0@sha256:5bd382fdadf7a766bfdb014dd30350f5c1a5f87e5bcb559a3a0539b2d2cce7aa \
     /privileged/environment/checker.py \
     /privileged/environment/essential.py \
     /privileged/environment/essential_articulated.py \
     /sim/essential_assets.py \
     /sim/essential_cube_layer_scene.py \
     /sim/essential_cube_reorient_scene.py \
     /privileged/environment/essential_held_joystick_scene.py \
     /privileged/environment/essential_inhand.py \
     /privileged/environment/essential_pen_regrasp_scene.py \
     /sim/essential_registry.json \
     /privileged/environment/essential_rotary_gait_scene.py \
     /privileged/environment/essential_rotary_multi.py \
     /privileged/environment/essential_two_object_scene.py \
     /privileged/environment/essential_visual.py \
     /sim/finalize.py \
     /sim/finalize.sh \
     /privileged/environment/hands.py \
     /sim/rcb_dexhand.py \
     /privileged/environment/replay.py \
     /privileged/environment/runtime.py \
     /privileged/environment/scene.py \
     /sim/server.py \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.8.0@sha256:497a2b864b3a1aaf1f60206dc14f08a0f99960037f0e54be3d4bc2e39f5adba4 /agent_end/rcb_agent_end.py /srv/rcb_agent_end.py
