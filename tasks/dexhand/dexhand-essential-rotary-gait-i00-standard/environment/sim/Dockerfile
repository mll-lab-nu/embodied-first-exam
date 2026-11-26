# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:dexhand-0.2.0@sha256:0d42994b83d95ab5301c592b35586550c9ee426490115e4b43f3b8cf8cc43350
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:dexhand-files-0.7.0@sha256:1397f5ba078dbbb9cff655c1ed962b72c3f42282d3bb5f2002f72209401249d2 \
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
COPY --from=ghcr.io/mll-lab-nu/efe:standard-files-0.5.0@sha256:ff602baf1ef852d21ecf0152d94cf210c8b691a5bdaa88d00dc381f6150b98cb \
     /rcb1.py \
     /rcb_limited.py \
     /run.sh \
     /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:agent-end-files-0.1.1@sha256:af4fa3c2f87c31e67f03232d39ef54d82a0e06d57c23da1c56cd69936779b6d9 /rcb_agent_end.py /srv/rcb_agent_end.py
