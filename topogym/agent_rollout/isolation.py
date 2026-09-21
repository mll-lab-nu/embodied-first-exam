"""Linux read boundary: only this repeat's published inputs reach the agent."""
import os
from pathlib import Path


def sandbox_command(command, public, agent_home, output, *, inherit_auth=True):
    public = Path(public).resolve()
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    args = ["bwrap", "--die-with-parent", "--new-session", "--unshare-pid", "--unshare-ipc", "--unshare-uts"]
    for path in ("/usr", "/bin", "/lib", "/lib64"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    for path in ("/etc/ssl", "/etc/resolv.conf", "/etc/hosts", "/etc/nsswitch.conf"):
        if Path(path).exists():
            args += ["--ro-bind", path, path]
    args += ["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
             "--ro-bind", str(public), "/workspace",
             "--bind", str(public / "scratch"), "/workspace/scratch",
             "--bind", str(agent_home), str(codex_home),
             "--bind", str(output), "/agent-output", "--chdir", "/workspace"]
    # Auth is read directly, never copied into an evaluation artifact. The rest
    # of the user's Codex history, config, plugins and memories are not mounted.
    auth = codex_home / "auth.json"
    if inherit_auth and auth.is_file():
        args += ["--ro-bind", str(auth), str(codex_home / "auth.json")]
    # Keep HOME/CODEX_HOME values unchanged; only their filesystem view changes.
    allowed = ("PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "OPENAI_API_KEY", "CODEX_API_KEY",
               "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY", "https_proxy", "http_proxy", "no_proxy")
    env = {k: v for k, v in os.environ.items() if k in allowed}
    if not inherit_auth:
        env.pop("OPENAI_API_KEY", None)
        env.pop("CODEX_API_KEY", None)
    return args + command, env
