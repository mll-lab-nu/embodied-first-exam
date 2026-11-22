#!/bin/bash
# Oracle (standard-mcp): the standard twin's oracle, unchanged (solve_standard.sh), with its robot client replaced by
# one that sends every call through the efe-robot MCP server as tool calls (solution/mcp/rcb_client_mcp.py:
# describe_robot, observe, execute_trajectory space native, wait, reset_episode); sitecustomize.py puts it in place of
# rcb_client in every Python process this script starts. The client's wire format (rcb1.py, which some oracles import
# to build their requests) is in the server's directory /opt/efe_mcp_client.
set -e
export EFE_MCP_ORACLE=1
export PYTHONPATH="/solution/mcp${PYTHONPATH:+:$PYTHONPATH}:/opt/efe_mcp_client"
bash /solution/solve_standard.sh "$@"
