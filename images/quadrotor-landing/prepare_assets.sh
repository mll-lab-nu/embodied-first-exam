#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Preparation environment needs NumPy and PyTorch. The runtime image does not include PyTorch.
python -m scripts.quadrotor_landing.prepare_assets --out images/quadrotor-landing/assets
