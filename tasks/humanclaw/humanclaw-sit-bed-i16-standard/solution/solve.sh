#!/bin/bash
# Reference solution (standard mode): streams the navmesh oracle's actions (found closed-loop with the privileged
# tools) as `skill` rows through the client, the agent's own interface. Uses no privileged information at run time.
set -e
mkdir -p /app/output
python /solution/oracle_stream.py
