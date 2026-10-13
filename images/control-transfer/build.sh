#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
CONTROL_IMAGE_VERSION=$(cat images/control-transfer/VERSION)
docker build --target nominal -f images/control-transfer/Dockerfile -t ghcr.io/mll-lab-nu/eai-control-transfer:${CONTROL_IMAGE_VERSION}-nominal .
docker build --target train -f images/control-transfer/Dockerfile -t ghcr.io/mll-lab-nu/eai-control-transfer:${CONTROL_IMAGE_VERSION}-train .
docker build --target evaluator -f images/control-transfer/Dockerfile -t ghcr.io/mll-lab-nu/eai-control-transfer:${CONTROL_IMAGE_VERSION} .
