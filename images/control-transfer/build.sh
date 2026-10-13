#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
docker build --target nominal -f images/control-transfer/Dockerfile -t ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0-nominal .
docker build --target train -f images/control-transfer/Dockerfile -t ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0-train .
docker build --target evaluator -f images/control-transfer/Dockerfile -t ghcr.io/mll-lab-nu/eai-control-transfer:0.1.0 .
