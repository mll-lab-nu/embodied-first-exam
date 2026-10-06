#!/usr/bin/env python3
"""Prepare private API/HF credentials in the foreground, before nohup.

Always asks for a fresh model key unless --check or --api-key-env is explicitly
selected. An existing HF token can be reused. Uses only the Python standard
library and existing credential readers. Does not
install tools, contact a provider, start trials, or change an assignment.
"""
import argparse
import getpass
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from urllib.parse import urlsplit
import warnings

from difficulty_hf_auth import read_token, token_text
from secret_scan import load_env
from agent_batch_provider import OPENROUTER_URL, OPENROUTER_KEYS, openrouter_credentials

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = 'https://api.openai.com/v1'


class SetupError(ValueError):
    pass


def private_path(value):
    path = Path(value).expanduser()
    path = path.parent.resolve() / path.name
    if path.is_relative_to(ROOT) or path.is_symlink():
        raise SetupError('Credential files must be outside this repository and must not be symlinks.')
    return path


def check_private_file(path):
    """Tighten an owned regular file's permissions without changing its contents."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_size > 65536:
            raise SetupError('Existing credential file must be a small regular file owned by this user.')
        if stat.S_IMODE(info.st_mode) & 0o077:
            os.fchmod(stream.fileno(), 0o600)


def api_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{16,4096}', value) or value.startswith('hf_'):
        raise SetupError('Enter the model API key as one token, without quotes, a Bearer prefix or an HF token.')
    return value


def base_url(value):
    try:
        parsed = urlsplit(value)
        if (not value.isascii() or any(c.isspace() or c in '\"\'' for c in value)
                or parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise ValueError
        parsed.port  # Validate the optional port without echoing the URL on error.
    except (ValueError, TypeError, AttributeError):
        raise SetupError('The API base URL must be an HTTPS URL without credentials, query or fragment.') from None
    return value


def hidden_input(prompt):
    if not sys.stdin.isatty():
        raise SetupError('Fresh model credentials require hidden input. Run configure_agent_batch.py in a foreground terminal before nohup.')
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except (getpass.GetPassWarning, EOFError):
            raise SetupError('Hidden terminal input is unavailable; no credential was saved.') from None


def create_private_file(path, contents, *, replace=False):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.helper-auth-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        # Only an explicitly refreshed model credential may replace an owned
        # regular file. HF credentials always retain create-only semantics.
        if replace:
            check_private_file(path)
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    except FileExistsError:
        raise SetupError('A credential file appeared during setup; preserved it. Run setup again to validate it.') from None
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def configure(env_file, hf_token_file, *, api_base_url=None, check_only=False, provider=None, api_key_env=None):
    env_file, hf_token_file = private_path(env_file), private_path(hf_token_file)
    if env_file == hf_token_file:
        raise SetupError('Model credentials and the HF token need separate files.')
    requested_base = base_url(api_base_url) if api_base_url is not None else None
    if provider not in (None, 'openai', 'openrouter'):
        raise SetupError('Provider must be openai or openrouter.')
    if provider == 'openrouter':
        if requested_base and requested_base.rstrip('/') != OPENROUTER_URL:
            raise SetupError('OpenRouter uses https://openrouter.ai/api/v1.')
        requested_base = OPENROUTER_URL
    if api_key_env and (not re.fullmatch(r'[A-Z][A-Z0-9_]*', api_key_env) or api_key_env.startswith('HF_')):
        raise SetupError('--api-key-env must name a model credential environment variable.')
    existing_model = env_file.exists()
    if existing_model:
        check_private_file(env_file)
        values = load_env(env_file)
        if set(values) - {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'PROVIDER', *OPENROUTER_KEYS}:
            raise SetupError('This API-key setup accepts only model credentials/provider settings in ENV_FILE; keep HF/subscription credentials separate.')
    elif check_only:
        raise SetupError('Model credential file is missing; run configure_agent_batch.py in the foreground.')
    existing_hf = hf_token_file.exists()
    if existing_hf:
        check_private_file(hf_token_file)
        read_token(hf_token_file)
    elif check_only:
        raise SetupError('HF token file is missing; run configure_agent_batch.py in the foreground.')
    if check_only:
        try:
            normalized = openrouter_credentials(values)
        except ValueError as error:
            raise SetupError(str(error)) from None
        api_key(normalized.get('OPENAI_API_KEY'))
        actual_base = base_url(normalized.get('OPENAI_BASE_URL', DEFAULT_BASE_URL))
        if provider == 'openai' and normalized.get('PROVIDER') == 'openrouter':
            raise SetupError('Existing provider differs; use a separate ENV_FILE. Existing credentials were preserved.')
        if requested_base is not None and actual_base != requested_base:
            raise SetupError('Existing API endpoint differs from --api-base-url; existing credentials were preserved.')
        return env_file, hf_token_file
    # Provider selection comes from this invocation, never a previous model key
    # or endpoint in the file. Do not silently reuse a saved key, even on retry.
    router = provider == 'openrouter' or requested_base == OPENROUTER_URL
    if api_key_env:
        key = api_key(os.environ.get(api_key_env))
    else:
        label = 'OpenRouter' if router else 'OpenAI-compatible'
        key = api_key(hidden_input(label + ' model API key (hidden; required each setup, not the HF token): '))
    name = 'OPENROUTER_API_KEY' if router else 'OPENAI_API_KEY'
    text = name + '=' + key + '\nOPENAI_BASE_URL=' + (requested_base or DEFAULT_BASE_URL) + '\n'
    if router: text += 'PROVIDER=openrouter\n'
    # Finish all prompts before changing either credential. Cancelling or an
    # invalid key must not fall back to the previous file or start the runner.
    if not existing_hf:
        token = token_text(hidden_input('HF upload token (hidden): '))
        create_private_file(hf_token_file, token + '\n')
    create_private_file(env_file, text, replace=existing_model)
    # Verify using the same dotenv/token readers used by the actual pipeline.
    api_key(openrouter_credentials(load_env(env_file)).get('OPENAI_API_KEY'))
    read_token(hf_token_file)
    return env_file, hf_token_file


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path.home() / 'rcb.env')
    parser.add_argument('--hf-token-file', type=Path, default=Path.home() / '.config/eai/helper-hf.token')
    parser.add_argument('--api-base-url', help='provider endpoint for this setup; default https://api.openai.com/v1')
    parser.add_argument('--provider', choices=('openai','openrouter'), help='provider for this setup; default openai; OpenRouter selects its endpoint automatically')
    parser.add_argument('--api-key-env', help='read the key from this environment variable instead of prompting; never the key itself')
    parser.add_argument('--check', action='store_true', help='check existing credentials without prompting')
    args = parser.parse_args(argv)
    try:
        env_file, hf_token_file = configure(args.env_file, args.hf_token_file,
                                           api_base_url=args.api_base_url, check_only=args.check,
                                           provider=args.provider, api_key_env=args.api_key_env)
    except SetupError as error:
        print('Credential setup blocked: ' + str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, UnicodeError):
        print('Credential setup blocked: could not safely read or save the credential files. Existing files were preserved.', file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('\nCredential setup cancelled; no experiment was started.', file=sys.stderr)
        return 130
    print('Existing credentials checked; no key was requested or changed.' if args.check else
          'Model API key refreshed for this setup (contents not displayed).')
    print('Model credentials: ' + str(env_file))
    print('HF upload token: ' + str(hf_token_file))
    print('This checks local configuration only; the runner checks model access before claiming trials.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
