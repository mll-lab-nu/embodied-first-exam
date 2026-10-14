#!/bin/bash
# Oracle: our reference skill (lowlevel/reference: the toolkit only).
set -e
mkdir -p /app/output
rm -rf /app/output/skill
cp -r /solution/skill /app/output/skill
