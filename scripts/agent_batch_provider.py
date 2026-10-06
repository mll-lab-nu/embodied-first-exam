"""Native Codex connection settings shared by the canary and Harbor runner.

No proxy, request rewriting, model fallback or credential storage. The outer
openrouter/ segment identifies the provider; the complete remaining slug is
passed to Codex unchanged.
"""
import re

OPENROUTER_URL = 'https://openrouter.ai/api/v1'
OPENROUTER_KEYS = ('OPENROUTER_API_KEY', 'OPENROUTER_API_KEY_FOR_SMOKE')


def canonical_model(model, provider=None):
    if provider not in (None, '', 'openai', 'openrouter'):
        raise ValueError('PROVIDER must be openai or openrouter for this native Codex runner')
    if provider == 'openrouter' and not model.startswith('openrouter/'):
        model = 'openrouter/' + model
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./:-]+', model):
        raise ValueError('invalid model ID')
    if model.startswith('openrouter/'):
        slug = model.removeprefix('openrouter/')
        if '/' not in slug or any(not part or part in ('.', '..') for part in slug.split('/')):
            raise ValueError('OpenRouter needs openrouter/<provider>/<model>, including the complete model slug')
        if provider == 'openai':
            raise ValueError('OpenRouter model conflicts with PROVIDER=openai')
    elif not model.startswith('openai/'):
        raise ValueError('use openai/<model> or openrouter/<provider>/<model>')
    return model


def openrouter_credentials(environment):
    """Normalize aliases without ever echoing a credential or guessing from its bytes."""
    env = dict(environment)
    keys = {env[name] for name in OPENROUTER_KEYS if env.get(name)}
    if len(keys) > 1:
        raise ValueError('OpenRouter credential variables disagree; supply one key')
    selected = (env.get('PROVIDER') == 'openrouter' or env.get('MODEL', '').startswith('openrouter/')
                or bool(keys) or env.get('OPENAI_BASE_URL', '').rstrip('/') == OPENROUTER_URL)
    if not selected:
        return env
    if env.get('PROVIDER') not in (None, '', 'openrouter'):
        raise ValueError('OpenRouter credentials conflict with PROVIDER')
    if env.get('CODEX_AUTH_JSON_PATH') or env.get('CODEX_FORCE_AUTH_JSON', '').lower() in ('1', 'true', 'yes'):
        raise ValueError('OpenRouter requires an API key; remove subscription auth settings')
    if env.get('OPENAI_BASE_URL', OPENROUTER_URL).rstrip('/') != OPENROUTER_URL:
        raise ValueError('OpenRouter credentials require https://openrouter.ai/api/v1; use a separate ENV_FILE')
    key = next(iter(keys), env.get('OPENAI_API_KEY'))
    if not key:
        raise ValueError('OpenRouter API key missing: set OPENROUTER_API_KEY or OPENROUTER_API_KEY_FOR_SMOKE')
    if env.get('OPENAI_API_KEY') and env['OPENAI_API_KEY'] != key:
        raise ValueError('OpenAI and OpenRouter keys conflict; use a separate ENV_FILE')
    env.update(PROVIDER='openrouter', OPENAI_API_KEY=key, OPENROUTER_API_KEY=key, OPENAI_BASE_URL=OPENROUTER_URL)
    return env


def codex_config(model, environment=None):
    """Only public settings; used both in CODEX_HOME and Harbor's native config option."""
    model = canonical_model(model)
    if model.startswith('openrouter/'):
        return {'model_provider': 'openrouter', 'model_providers': {'openrouter': {
            'name': 'OpenRouter', 'base_url': OPENROUTER_URL, 'wire_api': 'responses',
            'env_key': 'OPENAI_API_KEY', 'supports_websockets': False,
        }}}
    url = (environment or {}).get('OPENAI_BASE_URL')
    return {'openai_base_url': url} if url else {}


def model_id(model):
    return canonical_model(model).split('/', 1)[1]
