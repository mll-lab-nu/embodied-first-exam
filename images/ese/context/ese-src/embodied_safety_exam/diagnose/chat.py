"""Model callers for the probe: `chat(prompt, image_paths) -> str`, one fresh context per call.

    codex/<model>         the Codex client on the login it holds (`embodied_safety_exam.harness.codex.CodexChat`, the caller the
                          recognisability audit uses; subscription, no API cost)
    claude-code/<model>   `claude -p --model <model>` with CLAUDE_CODE_OAUTH_TOKEN read from a file (subscription)
    endpoint/<model>      an OpenAI-compatible chat-completions endpoint that takes images (`embodied_safety_exam.harness.toolcall
                          .Endpoint`); the base URL and the key's environment variable have to be given

A coding-agent client is used as a plain model here: it runs in an empty directory with its own tools off, and it is
given no schema: the answer is the text of its final message. What cannot be switched off (Codex keeps its own base
instructions and a few tool definitions) is the same caveat as for trials run through these clients. No credential
is read into this process's output: a token goes to the child's environment only, and error texts pass through
`toolcall.redact`.
"""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SYSTEM = "You answer questions about the pictures attached to the message. You have no tools; answer in text."
CHANNELS = ("codex", "claude-code", "endpoint")
HARBOR_AGENTS = {"codex": "codex", "claude-code": "claude-code"}       # Harbor agent name -> channel
_LIMIT = re.compile(r"rate.?limit|usage limit|limit reached|too many requests|quota|overloaded|\b429\b|5-hour|weekly limit", re.I)


class ChatFailed(RuntimeError):
    """The caller could not get an answer (not a result of the model)."""


class RateLimited(ChatFailed):
    pass


def _redact(text: str) -> str:
    from embodied_safety_exam.harness.toolcall import redact
    return redact(text)


def split(spec: str) -> tuple[str, str]:
    """`codex/gpt-x` -> (`codex`, `gpt-x`). The model part may itself hold slashes (`endpoint/vendor/model`)."""
    channel, _, model = spec.partition("/")
    if channel not in CHANNELS or not model:
        raise ValueError(f"{spec!r}: a probe model is <channel>/<model>, channel one of {CHANNELS}")
    return channel, model


def for_trial(agent: str | None, model: str | None) -> str | None:
    """The probe spec of the model that ran a Harbor trial: agent `codex`, model `openai/gpt-x` -> `codex/gpt-x`.
    None when the trial was not run through one of the subscription CLIs (name the caller with `--probe RUN=...`)."""
    channel = HARBOR_AGENTS.get(agent or "")
    if not channel or not model:
        return None
    return f"{channel}/{model.split('/')[-1]}"


class ClaudeCodeChat:
    """`claude -p`, one call per question; the token is read from `token_file` (a line CLAUDE_CODE_OAUTH_TOKEN=...)."""

    def __init__(self, model: str, effort: str | None = "medium", timeout: float = 600.0, runner=None, binary: str | None = None,
                 token_file: str | None = None):
        self.model, self.effort, self.timeout = model, effort, timeout
        self.binary = binary or os.environ.get("ESE_CLAUDE_BIN") or shutil.which("claude") or str(Path.home() / ".local/bin/claude")
        self.token_file = Path(token_file or os.environ.get("ESE_CLAUDE_ENV") or Path.home() / ".config/rcb/claude.env").expanduser()
        self.runner = runner or (lambda cmd, stdin, env, cwd, timeout: subprocess.run(cmd, input=stdin, capture_output=True, text=True, env=env, cwd=cwd, timeout=timeout))
        self.usage: dict = {}

    def _token(self) -> str:
        if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
            return os.environ["CLAUDE_CODE_OAUTH_TOKEN"]
        if self.token_file.exists():
            for line in self.token_file.read_text().splitlines():
                if line.startswith("CLAUDE_CODE_OAUTH_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        raise ChatFailed(f"no CLAUDE_CODE_OAUTH_TOKEN in the environment or in {self.token_file}")

    def command(self, work: Path) -> list[str]:
        cmd = [self.binary, "-p", "--model", self.model, "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--tools", "", "--setting-sources", "", "--no-session-persistence", "--disable-slash-commands",
               "--system-prompt-file", str(work / "system.txt")]
        return cmd + (["--effort", self.effort] if self.effort else [])

    def __call__(self, prompt: str, image_paths: list) -> str:
        work = Path(tempfile.mkdtemp(prefix="probe_claude_"))
        try:
            (work / "empty").mkdir()
            (work / "config").mkdir()
            (work / "system.txt").write_text(SYSTEM)
            content = [{"type": "text", "text": prompt}]
            for f in image_paths:
                content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                            "data": base64.b64encode(Path(f).read_bytes()).decode()}})
            line = json.dumps({"type": "user", "message": {"role": "user", "content": content}}) + "\n"
            env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(Path.home()), "CLAUDE_CONFIG_DIR": str(work / "config"),
                   "CLAUDE_CODE_OAUTH_TOKEN": self._token()}
            try:
                p = self.runner(self.command(work), line, env, str(work / "empty"), self.timeout)
            except subprocess.TimeoutExpired:
                raise ChatFailed(f"claude timed out after {self.timeout:.0f} s") from None
            texts, result = [], None
            for ln in (p.stdout or "").splitlines():
                try:
                    j = json.loads(ln)
                except ValueError:
                    continue
                if j.get("type") == "assistant":
                    msg = j.get("message") or {}
                    texts += [c["text"] for c in msg.get("content") or [] if c.get("type") == "text" and c.get("text", "").strip()]
                    u = msg.get("usage") or {}
                    if u:
                        self.usage = {"input": u.get("input_tokens"), "cached": u.get("cache_read_input_tokens"), "output": u.get("output_tokens")}
                elif j.get("type") == "result":
                    result = j
            if result is not None and not result.get("is_error") and isinstance(result.get("result"), str) and result["result"].strip():
                return result["result"]
            if texts and (result is None or not result.get("is_error")):
                return "\n\n".join(texts)
            blob = _redact(str((result or {}).get("result") or "") + (p.stdout or "")[-600:] + (p.stderr or "")[-600:])
            raise (RateLimited if _LIMIT.search(blob) else ChatFailed)(f"claude exited {p.returncode} without an answer: {blob[:500]}")
        finally:
            shutil.rmtree(work, ignore_errors=True)


class EndpointChat:
    """A caller of the shape of `toolcall.Endpoint` (`(messages, tools) -> {"response": ...}`): a chat-completions
    endpoint, or `embodied_safety_exam.harness.codex.CodexChat`. An error that reads like a usage limit is a `RateLimited`."""

    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.usage: dict = {}

    def __call__(self, prompt: str, image_paths: list) -> str:
        content = [{"type": "text", "text": prompt}]
        for f in image_paths:
            content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(Path(f).read_bytes()).decode()}})
        try:
            got = self.endpoint([{"role": "system", "content": SYSTEM}, {"role": "user", "content": content}], None)
        except RuntimeError as e:
            text = _redact(str(e)[:500])
            raise (RateLimited if _LIMIT.search(text) else ChatFailed)(text) from None
        self.usage = got["response"].get("usage") or {}
        text = got["response"]["choices"][0]["message"].get("content") or ""
        if not str(text).strip():
            raise ChatFailed("the endpoint gave an empty answer")
        return str(text)


def make(spec: str, effort: str | None = "medium", timeout: float = 600.0, base_url: str | None = None, key_env: str | None = None,
         key_file: str | None = None):
    """The caller for `<channel>/<model>`."""
    channel, model = split(spec)
    if channel == "codex":
        from embodied_safety_exam.harness import codex
        # no retries inside the caller: every call is counted against the probe's cap
        return EndpointChat(codex.CodexChat(model, effort, timeout=timeout, retries=0))
    if channel == "claude-code":
        return ClaudeCodeChat(model, effort, timeout)
    from embodied_safety_exam.harness import toolcall
    base_url = base_url or os.environ.get("ESE_BASE_URL")
    if not base_url or not key_env:
        raise ValueError("endpoint/<model> needs --base-url (or ESE_BASE_URL) and --key-env")
    if not toolcall.load_key(key_env, key_file):
        raise ValueError(f"no key: set {key_env} or give --key-file")
    extra = {**toolcall.PROFILES.get(model, {}).get("extra", {})}
    extra.setdefault("max_tokens", 1200)
    return EndpointChat(toolcall.Endpoint(base_url, model, key_env, extra=extra, timeout=timeout, retries=3))
