"""Reference solution of a standard-mcp task: with EFE_MCP_ORACLE=1 (solution/solve.sh), `import rcb_client` gives
rcb_client_mcp, the same Robot API through the efe-robot MCP tools (whatever sys.path the oracle sets up)."""
import os
import sys

if os.environ.get("EFE_MCP_ORACLE") == "1":
    sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
    import rcb_client_mcp
    sys.modules["rcb_client"] = rcb_client_mcp
