# The `sim` sidecar's image (environment/docker-compose.yaml builds it): its base image, this directory at /srv, and at
# their paths under /srv the files it shares with other tasks, from pinned files-only images (images/<name>/
# FILES.json, scripts/files_image.py). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-soccer-0.1.0
COPY . /srv/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/audit/ /srv/audit/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/variants/e333006dc5/metering/ /srv/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /privileged/environment/fullsim/renderers/ /srv/renderers/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/bodies/booster_t1/ /srv/bodies/booster_t1/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/sport/models/ /srv/sport/models/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/sport/seat/ /srv/sport/seat/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/sport/rl/v2/ /srv/sport/rl/v2/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /sim/sport/rl/joint/v1/ /srv/sport/rl/joint/v1/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /shared/tests/grade.py /srv/core/grading.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /shared/tests/variants/44aa8d7a20/sport_grade.py /srv/sport/grade.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /privileged/environment/fullsim/bodies/limits.py \
     /privileged/environment/fullsim/bodies/servo.py \
     /privileged/environment/fullsim/bodies/sources.py \
     /srv/bodies/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /sim/variants/56839c849b/core/README.md \
     /sim/variants/ad819abd79/core/__init__.py \
     /privileged/environment/fullsim/core/channel.py \
     /sim/core/client.py \
     /privileged/environment/fullsim/core/diaglog.py \
     /privileged/environment/fullsim/core/diagnose.py \
     /privileged/environment/fullsim/core/episode.py \
     /sim/core/game.py \
     /privileged/environment/fullsim/core/http.py \
     /sim/variants/dac3238d5e/core/launch.py \
     /privileged/environment/fullsim/core/local.py \
     /privileged/environment/fullsim/core/observe.py \
     /privileged/environment/fullsim/core/outcome.py \
     /privileged/environment/fullsim/core/realtime.py \
     /sim/core/rng.py \
     /privileged/environment/fullsim/core/score.py \
     /sim/variants/88a2efdf27/core/seats.py \
     /shared/tests/seeds.py \
     /privileged/environment/fullsim/core/serve.py \
     /privileged/environment/fullsim/core/service.py \
     /privileged/environment/fullsim/core/spec.py \
     /privileged/environment/fullsim/core/spectator.py \
     /privileged/environment/fullsim/core/sport.py \
     /privileged/environment/fullsim/core/testkit.py \
     /privileged/environment/fullsim/core/turn.py \
     /privileged/environment/fullsim/core/workers.py \
     /srv/core/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /sim/core/metering/__init__.py \
     /privileged/environment/fullsim/core/metering/api_errors.py \
     /privileged/environment/fullsim/core/metering/think_clock.py \
     /srv/core/metering/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /privileged/environment/fullsim/core/tests/fixture/plugin.py \
     /sim/core/tests/fixture/sport.toml \
     /srv/core/tests/fixture/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /privileged/environment/fullsim/core/tests/fixture_images/plugin.py \
     /sim/core/tests/fixture_images/sport.toml \
     /srv/core/tests/fixture_images/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /privileged/environment/fullsim/core/tests/fixture_turn/plugin.py \
     /sim/core/tests/fixture_turn/sport.toml \
     /srv/core/tests/fixture_turn/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /sim/variants/9bce593aa6/core/tests/test_core.py \
     /privileged/environment/fullsim/core/tests/test_diagnose.py \
     /srv/core/tests/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f /privileged/environment/fullsim/spectator/broadcast_log.py /srv/spectator/broadcast_log.py
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /sim/variants/cab0e94a08/sport/builtin_players.py \
     /sim/sport/overhead.py \
     /sim/sport/plugin.py \
     /sim/variants/264b3f9f1b/sport/reference_check.py \
     /sim/sport/rl_joint.py \
     /sim/sport/rl_opponent.py \
     /sim/sport/soccer.py \
     /sim/sport/soccer_scene.py \
     /sim/variants/0f5f8bdf5f/sport/sport.toml \
     /sim/sport/step_kick.py \
     /sim/sport/swing_kick.py \
     /srv/sport/
COPY --from=ghcr.io/mll-lab-nu/efe:embodied-olympics-match-files-0.4.0@sha256:0d8eb42153dfb410f293e1ab6da62c5f3b7f08901fbb8c91f1d98e6729ebf88f \
     /sim/sport/rl/joint/v1/gait.npz \
     /sim/sport/rl/joint/v2/plan.npz \
     /srv/sport/rl/joint/v2/
