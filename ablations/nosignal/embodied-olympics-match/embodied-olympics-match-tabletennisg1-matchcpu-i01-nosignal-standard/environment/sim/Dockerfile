# The `sim` sidecar's image (environment/docker-compose.yaml builds it; the practice service and the practice player
# run from it too): the sport's image (Embodied Olympics' generated sim, practice world and practice player of
# tabletennis_g1, g1tt-10+core-0.5), then this directory at /srv (Embodied First Exam's patches of core/, listed in
# ci_checks/benchmarks/embodied-olympics-match/exported.toml). .dockerignore keeps the build's own two files out of /srv.
FROM ghcr.io/mll-lab-nu/efe:embodied-olympics-match-tabletennisg1-0.1.0@sha256:8bc6d02f91aa5730bbf93bc5c1c4a477feee6f5846ff8c609aaa3a25e0eb36af
COPY . /srv/
