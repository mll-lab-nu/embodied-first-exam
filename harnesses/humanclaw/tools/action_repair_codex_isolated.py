#!/usr/bin/python3.12
"""Preserve Codex 0.145.0 and its isolation policy under the user's repair paths."""
import os
from pathlib import Path
import sys

RUNTIME = Path("/mmfs1/gscratch/scrubbed/linjli/native-rt")
CODEX = RUNTIME / "codex-0.145.0/bin/codex"
BWRAP = RUNTIME / "codex-0.163.0/codex-resources/bwrap"
OUTPUT = Path("/gscratch/scrubbed/hengyil6/humanclaw-analysis/experiments").resolve()


def main():
    args = sys.argv[1:]
    if args == ["--version"]:
        version = CODEX.with_name(CODEX.name + ".version")
        if version.is_file():
            print(version.read_text().strip())
            return
        os.execv(str(CODEX), [str(CODEX), *args])
    home = Path(os.environ["HOME"]).resolve()
    workspace = Path.cwd().resolve()
    native = home.parent
    if (home.name != "home" or native.name != "native" or workspace != native / "workspace"
            or not native.is_relative_to(OUTPUT) or "action-repair-azure-20261021" not in native.parts):
        raise SystemExit("Refusing a native home outside the dedicated repaired attempt")
    for path in (home / ".codex", home / ".codex/.tmp"):
        if path.is_symlink():
            raise SystemExit("Refusing symlinked Codex temporary cache")
    command = [str(BWRAP), "--dev-bind", "/", "/"]
    for name in ("/mmfs1/home", "/mmfs1/gscratch/stf/hengyil6",
                 "/mmfs1/gscratch/scrubbed/hengyil6", "/mmfs1/gscratch/scrubbed/linjli",
                 "/mmfs1/gscratch/krishna", "/mmfs1/gscratch/cse", "/tmp", "/var/tmp", "/etc/ai-agents"):
        if Path(name).is_dir():
            command.extend(["--tmpfs", name])
    command.extend(["--ro-bind", str(RUNTIME), str(RUNTIME), "--bind", str(native), str(native),
                    "--perms", "0700", "--size", "536870912", "--tmpfs", str(home / ".codex/.tmp"),
                    "--unshare-pid", "--proc", "/proc", "--die-with-parent", "--setenv", "TMPDIR", "/tmp",
                    "--chdir", str(workspace), "--", str(CODEX), *args])
    os.execv(command[0], command)


if __name__ == "__main__":
    main()
