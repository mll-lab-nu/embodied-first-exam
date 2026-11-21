#!/bin/bash
# Oracle (standard-mcp): the standard twin's oracle, unchanged (solve_standard.sh), with its robot client replaced by
# one that sends every call through the efe-robot MCP server as tool calls (solution/mcp/rcb_client_mcp.py:
# describe_robot, observe, execute_trajectory space native, wait, reset_episode); sitecustomize.py puts it in place of
# rcb_client in every Python process this script starts.
set -e
export EFE_MCP_ORACLE=1
export PYTHONPATH="/solution/mcp${PYTHONPATH:+:$PYTHONPATH}"
bash /solution/solve_standard.sh "$@"
