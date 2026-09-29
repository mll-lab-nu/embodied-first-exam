import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from harbor_runners.config import load_config
from harbor_runners.task_generator import prepare
from harbor_runners.usage_bridge import require_capabilities, validate_usage
from harbor_runners.agents.usage_adapter import UsageAgent
from harbor_runners.collect import collect
from harbor_runners.rollout_output_report import summarize
from harbor_runners.endpoints import resolve_model
from topogym.agents.usage import BudgetPolicy, UsageEvent, UsageLedger
from topogym.agents.usage.store import atomic_json

ROOT = Path(__file__).resolve().parents[2]


def budget_config():
    config = load_config(ROOT / 'configs/harbor/experiments/cube_pick_place_rollout.yaml')
    config['model'] = 'openrouter/test/model'
    return config


def test_default_limits_and_explicit_zero():
    assert validate_usage({'mode':'observed'})['limits'] == {'input_tokens':50_000_000,'output_tokens':20_000_000}
    assert validate_usage({'mode':'observed','limits':{'input_tokens':0}})['limits']['input_tokens'] == 0


@pytest.mark.parametrize('edit', [
    {'mode':'off','limits':{'input_tokens':1}}, {'mode':'observed','limits':{'input_tokens':True}},
    {'mode':'observed','scope':'job'}, {'mode':'observed','on_usage_unavailable':'ignore'},
    {'mode':'observed','watchdog_interval_ms':0}, {'mode':'observed','total_tokens':70_000_000},
])
def test_invalid_budget_config_rejected(edit):
    with pytest.raises(ValueError): validate_usage(edit)


def test_budgeted_task_uses_native_network_phases_without_real_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENROUTER_META_SPARK_API_KEY','real-private-test-key')
    config = budget_config()
    run = prepare(config, tmp_path, 'budget')
    job = json.loads((run/'job.json').read_text())
    agent = job['agents'][0]
    assert agent['import_path'].endswith(':UsageAgent') and agent['env'] == {}
    import toml
    task = next((run/'harbor_tasks').iterdir())
    spec = toml.loads((task/'task.toml').read_text())
    assert spec['agent']['network_mode'] == 'no-network'
    assert spec['verifier']['network_mode'] == 'no-network'
    compose = yaml.safe_load((task/'environment/docker-compose.yaml').read_text())
    service = compose['services']['main']
    assert service['cap_drop'] == ['NET_RAW']
    assert any(v['target'] == '/run/topogym-usage' and v['read_only'] for v in service['volumes'])
    for file in run.rglob('*'):
        if file.is_file(): assert 'real-private-test-key' not in file.read_text()


@pytest.mark.parametrize('model', ['openai/gpt-test','anthropic/claude-test','openrouter/test/model'])
def test_native_delegate_isolated_from_ambient_provider_credentials(tmp_path, monkeypatch, model):
    monkeypatch.setenv('OPENAI_API_KEY','host-secret')
    monkeypatch.setenv('ANTHROPIC_API_KEY','host-secret')
    monkeypatch.setenv('CLAUDE_FORCE_OAUTH','true')
    monkeypatch.setenv('CODEX_FORCE_AUTH_JSON','true')
    agent = UsageAgent(connection=resolve_model(model,version='1.18.33'), usage=validate_usage({'mode':'observed'}),
        sockets=str(tmp_path), logs_dir=tmp_path/'agent', model_name=model)
    delegate = agent._new_delegate('trial-only','http://127.0.0.1:1234')
    assert delegate._get_env('CLAUDE_FORCE_OAUTH') is None
    assert delegate._get_env('CODEX_FORCE_AUTH_JSON') is None
    assert 'host-secret' not in json.dumps(delegate.extra_env)
    assert agent.extra_env == {}
    if model.startswith('openrouter/'):
        assert delegate._opencode_config['provider']['openrouter']['options']['baseURL'].endswith(':1234/v1')


def test_strict_and_unknown_providers_fail_before_run_is_created(tmp_path):
    config = budget_config()
    config['usage']['mode'] = 'strict'
    with pytest.raises(ValueError, match='upper bounds'): prepare(config,tmp_path,'strict')
    assert not (tmp_path/'runs/harbor/strict').exists()
    config['usage']['mode'] = 'observed'
    config['model'] = 'unknown/test'
    with pytest.raises(ValueError, match='not registered'): prepare(config,tmp_path,'unknown')


def test_connection_cannot_smuggle_arbitrary_native_kwargs():
    connection=resolve_model('openrouter/test',version='1.18.33')
    connection['kwargs']={'max_turns':2}
    with pytest.raises(ValueError, match='connection'):
        require_capabilities(connection, {'mode':'observed'})


def test_lost_container_budget_failure_stays_in_denominator(tmp_path):
    config = budget_config()
    run = prepare(config,tmp_path,'lost-container')
    trial = run/'jobs/job/trial-one'
    trial.mkdir(parents=True)
    atomic_json(trial/'result.json', {'exception_info':{'exception_type':'ContainerStopped'}})
    ledger = UsageLedger(trial/'usage/ledger.sqlite',scope_id='trial-one',policy=BudgetPolicy(10,10))
    ledger.admit('r',source='test'); ledger.mark_sent('r')
    ledger.record(UsageEvent('r','e',0,'test',11,1,final=True))
    atomic_json(trial/'usage/snapshot.json',ledger.finalize())
    index = collect(run,tmp_path)
    result = index['trials']['trial-one']
    assert not index['pipeline_passed'] and result['verification']['reward'] == 0
    assert result['failure_reason'] == 'budget_exceeded'
    summary = summarize(run)
    assert summary['budget_success_rate'] == 0 and summary['planned_task_trials'] == 1
    assert summary['budget_failed_trials'] == 1 and summary['incomplete_archives'] == 1


def test_collection_uses_ledger_when_export_is_stale_success(tmp_path):
    run = prepare(budget_config(), tmp_path, 'stale-export')
    trial = run / 'jobs/job/trial-one'
    trial.mkdir(parents=True)
    atomic_json(trial/'result.json', {'exception_info':None})
    book = UsageLedger(trial/'usage/ledger.sqlite',scope_id='trial-one',policy=BudgetPolicy(10,10))
    book.admit('r',source='test'); book.mark_sent('r')
    book.record(UsageEvent('r','e',0,'test',2,1,final=True))
    atomic_json(trial/'usage/snapshot.json',book.finalize())
    book.fail('gateway_failed')  # exporter failed after the earlier snapshot
    index = collect(run,tmp_path)
    result = index['trials']['trial-one']
    assert result['failure_reason'] == 'gateway_failed'
    assert not result['budget_qualified'] and result['verification']['reward'] == 0
