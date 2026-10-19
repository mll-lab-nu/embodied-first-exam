#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Preparation environment needs NumPy and PyTorch. The runtime image does not include PyTorch.
python images/quadrotor-landing/prepare_assets.py --out images/quadrotor-landing/assets
