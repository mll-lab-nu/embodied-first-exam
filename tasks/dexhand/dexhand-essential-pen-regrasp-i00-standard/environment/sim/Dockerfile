# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.5.1@sha256:f851deb355ccfacfb366e8a6acf11fa91e575a4e410fa356db84e3221407ad20 \
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
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.4.1@sha256:7f1a830075fd6dd25e7a20a340316c041df583a29062796f59a4fa63b6f76946 \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
