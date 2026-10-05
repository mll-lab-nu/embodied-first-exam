"""Explicit, noninteractive HF credentials. Never import the Hub SDK on an offline path."""
from __future__ import annotations

import os
from pathlib import Path
import re
import stat

DEFAULT_REPO = "LGVamper/toponym_evaluation_results"
HF_ENV = ("HF_TOKEN", "HUGGING_FACE_HUB_TOKEN", "HF_TOKEN_PATH", "HF_HOME",
          "TOPOGYM_HF_AUTH_DIR", "HF_ENDPOINT")


class HFError(ValueError):
    """A public error code/message, never a raw SDK exception or credential."""
    def __init__(self, code, message=None, *, retryable=False):
        self.code, self.retryable = code, retryable
        super().__init__(message or code)


def add_arguments(parser):
    parser.add_argument("--results_to_hf", "--results-to-hf", action="store_true")
    parser.add_argument("--hf-repo-id")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--hf-token-env", help="credential environment variable (default HF_TOKEN)")
    sources.add_argument("--hf-token-file", type=Path, help="private single-line token file; never a token literal")
    parser.add_argument("--hf-exp-date", help="YYYY-MM-DD; retained across retries")
    parser.add_argument("--hf-artifacts", choices=("standard", "metrics"))
    parser.add_argument("--hf-dry-run", action="store_true")


def validate_arguments(args):
    import datetime as dt
    supplied = any(getattr(args, name) is not None for name in
                   ("hf_repo_id", "hf_token_env", "hf_token_file", "hf_exp_date", "hf_artifacts")) or args.hf_dry_run
    if (supplied or args.phase == "upload") and not args.results_to_hf:
        raise HFError("configuration", "HF options and phase upload require --results_to_hf")
    if args.hf_dry_run and args.phase not in ("collect", "upload"):
        raise HFError("configuration", "--hf-dry-run requires phase collect or upload")
    if args.hf_token_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.hf_token_env):
        raise HFError("configuration", "invalid HF environment variable name")
    args.hf_repo_id = args.hf_repo_id or DEFAULT_REPO
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", args.hf_repo_id):
        raise HFError("configuration", "invalid HF dataset repository ID")
    if ".." in args.hf_repo_id or "--" in args.hf_repo_id:
        raise HFError("configuration", "invalid HF dataset repository ID")
    if args.hf_exp_date:
        try:
            if dt.date.fromisoformat(args.hf_exp_date).isoformat() != args.hf_exp_date:
                raise ValueError
        except ValueError:
            raise HFError("configuration", "--hf-exp-date must be YYYY-MM-DD") from None
    args.hf_artifacts = args.hf_artifacts or "standard"


def active(args):
    return args.results_to_hf and args.phase in ("run", "all", "collect", "upload")


def token_text(value):
    value = value.rstrip("\r\n")
    if not value or len(value) > 4096 or any(c.isspace() or not c.isascii() or ord(c) < 33 for c in value):
        raise HFError("credentials", "HF token must be a nonempty single line")
    return value


def read_token(path):
    """Do not follow a final symlink; check the opened inode, including owner/mode."""
    root = Path(__file__).resolve().parents[1]
    location = Path(path).expanduser()
    # Resolve parent aliases and '..' before applying the source exclusion;
    # keep the final component intact so O_NOFOLLOW still rejects symlinks.
    location = location.parent.resolve() / location.name
    if location.is_relative_to(root) and not location.is_relative_to(root / ".secrets"):
        raise HFError("credentials", "put HF token outside the source repository or in its root .secrets directory")
    try:
        fd = os.open(location, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise HFError("credentials", "HF token file must be an owned regular file with mode 0600 or 0400")
            value = stream.read(4098)
        if len(value) > 4096:
            raise HFError("credentials", "HF token file is too large")
        return token_text(value.decode("ascii"))
    except (OSError, UnicodeError):
        raise HFError("credentials", "cannot read private --hf-token-file (use chmod 600)") from None


def resolve_token(args):
    if args.hf_token_file is not None:
        return read_token(args.hf_token_file), "file"
    name = args.hf_token_env or "HF_TOKEN"
    if name not in os.environ:
        raise HFError("credentials", "set HF_TOKEN (or --hf-token-env), or provide --hf-token-file; no interactive login")
    return token_text(os.environ[name]), "env"


def clean_environment(env, args):
    env = dict(env)
    for name in (*HF_ENV, args.hf_token_env):
        if name:
            env.pop(name, None)
    # Explicitly prevent child SDKs from discovering a host's globally cached token.
    env["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
    return env


def error_from_exception(error):
    """Classify only safe metadata; never interpolate the exception string."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status in (401, 403):
        return HFError("permission_denied")
    if status == 404:
        return HFError("repository_or_revision_unavailable")
    if status in (409, 412):
        return HFError("commit_conflict", retryable=True)
    if status == 429 or (status is not None and status >= 500):
        return HFError("rate_limited" if status == 429 else "service_unavailable", retryable=True)
    if any(word in type(error).__name__.lower() for word in ("timeout", "connect", "network", "transport", "protocol")):
        return HFError("network_error", retryable=True)
    return HFError("hub_request_failed")


def main():
    """Store a credential interactively, without shell history or token arguments."""
    import argparse
    import getpass
    import sys
    p=argparse.ArgumentParser(description='Store an HF token using hidden terminal input.')
    p.add_argument('command',choices=('store',))
    p.add_argument('--file',type=Path,required=True)
    a=p.parse_args()
    try:
        if not sys.stdin.isatty(): raise HFError('credentials','run token store in an interactive terminal')
        path=a.file.expanduser().absolute(); root=Path(__file__).resolve().parents[1]
        if path.resolve().is_relative_to(root): raise HFError('credentials','store the token outside the repository')
        if path.exists() or path.is_symlink(): raise HFError('credentials','credential file already exists; preserve it')
        value=token_text(getpass.getpass('HF token (hidden): '))
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as stream: stream.write(value+'\n')
        read_token(path)
        print('Private credential file saved; token not displayed.')
    except (OSError,ValueError) as error: p.exit(2,str(error)+'\n')


if __name__=='__main__': main()
