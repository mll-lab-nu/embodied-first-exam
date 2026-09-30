#!/usr/bin/env bash
# Same normalized input identity on the host and after COPY into the controller.
set -euo pipefail
cd -- "${1:?source root required}"
tar --format=gnu --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner --mode='u=rwX,go=rX' \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' --exclude='.env*' --exclude='.secrets' \
  -cf - .dockerignore topogym assets/robots configs requirements images scripts bash_scripts harbor_templates harbor_agents ci_checks \
  | sha256sum | cut -d ' ' -f 1
