"""One question with pictures to a model behind the Codex command-line client (`codex exec`), on the login that
client already holds. Used by the audits that ask a vision model something outside a trial; trials themselves run
the Codex agent through Harbor.

    chat = CodexChat("gpt-6-luna")
    chat([{"role": "user", "content": [{"type": "text", ...}, {"type": "image_url", ...}]}], None)

The call has the shape of `toolcall.Endpoint`: it returns `{"response": {"choices": [{"message": {"content": str}}]}}`.
Nothing of the login is read, printed or stored here; the client is started with an empty working directory, the
read-only sandbox and its own tools switched off.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

#: where the client is when it is not on PATH (it ships inside the editor extension); ROBOSAFEBENCH_CODEX_BIN names another
BUILDS = ".vscode-server/extensions/openai.chatgpt-*-linux-x64/bin/linux-x86_64/codex"
#: features of the client that add tools or context of their own
OFF = ("shell_tool", "apps", "plugins", "multi_agent", "image_generation", "goals", "view_image", "browser_use",
       "computer_use", "skill_search", "sleep_tool", "tool_suggest", "unified_exec", "hooks", "memories")
PREFIX = "codex/"


def binary() -> str:
    if os.environ.get("ROBOSAFEBENCH_CODEX_BIN"):
        return os.environ["ROBOSAFEBENCH_CODEX_BIN"]
    found = shutil.which("codex")
    if found:
        return found
    builds = sorted(Path.home().glob(BUILDS), key=lambda p: p.stat().st_mtime)
    if not builds:
        raise RuntimeError("no codex binary: install the Codex client or set ROBOSAFEBENCH_CODEX_BIN")
    return str(builds[-1])


class CodexError(RuntimeError):
    pass


class CodexChat:
    def __init__(self, model: str, effort: str | None = "medium", timeout: float = 600.0, retries: int = 2):
        self.model = model[len(PREFIX):] if model.startswith(PREFIX) else model
        self.effort, self.timeout, self.retries = effort, timeout, retries
        self.bin = binary()

    def __call__(self, messages: list[dict], tools=None) -> dict:
        last = None
        for _ in range(self.retries + 1):
            try:
                return self._once(messages)
            except (CodexError, subprocess.TimeoutExpired) as e:
                last = e
        raise CodexError(str(last)[:400])

    def _once(self, messages: list[dict]) -> dict:
        with tempfile.TemporaryDirectory(prefix="codex_q_") as tmp:
            work = Path(tmp)
            (work / "empty").mkdir()
            lines, images = [], []
            for m in messages:
                content = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": str(m["content"])}]
                for part in content:
                    if part.get("type") == "text":
                        lines.append(part["text"])
                    elif part.get("type") == "image_url":
                        head, data = part["image_url"]["url"].split(",", 1)
                        f = work / f"image_{len(images) + 1:02d}.{'jpg' if 'jpeg' in head else 'png'}"
                        f.write_bytes(base64.b64decode(data))
                        images.append(f)
            prompt = "\n\n".join(lines)
            if images:
                prompt = f"{len(images)} pictures are attached to this message, in the order the text speaks of them.\n\n" + prompt
            cmd = [self.bin, "exec", "-m", self.model, "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                   "-s", "read-only", "-C", str(work / "empty"), "-c", 'web_search="disabled"', "--json"]
            if self.effort:
                cmd += ["-c", f'model_reasoning_effort="{self.effort}"']
            for f in OFF:
                cmd += ["--disable", f]
            for f in images:
                cmd += ["-i", str(f)]
            cmd.append("-")
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME")}
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=self.timeout, env=env, cwd=work / "empty")
            texts, errors, usage = [], [], {}
            for ln in p.stdout.splitlines():
                try:
                    j = json.loads(ln)
                except ValueError:
                    continue
                t, item = j.get("type"), j.get("item") or {}
                if t == "item.completed" and item.get("type") == "agent_message":
                    texts.append(item.get("text") or "")
                elif t == "turn.completed":
                    usage = j.get("usage") or {}
                elif t in ("error", "turn.failed") or (t == "item.completed" and item.get("type") == "error"):
                    errors.append(json.dumps(j)[:300])
            if not texts:
                raise CodexError(f"codex exited {p.returncode}: " + (" | ".join(errors) or p.stderr[-300:] or p.stdout[-300:]))
            return {"response": {"choices": [{"message": {"content": "\n\n".join(texts)}}], "usage": usage}}
