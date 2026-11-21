#!/bin/bash
set -euo pipefail
cd /app
python /solution/iterate.py --url http://127.0.0.1:8000 --out /app/output/reference
