import importlib.util
import json
from pathlib import Path
import sys

import pytest

from harbor_runners.config import load_config

ROOT = Path(__file__).resolve().parents[2]


def script(monkeypatch,tmp_path,args):
    spec=importlib.util.spec_from_file_location('usage_pipeline_test',ROOT/'scripts/test_harbor_pipeline.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original=module.load_config
    module.ROOT=tmp_path
    module.load_config=lambda path,**kw: original(ROOT/'configs/harbor/experiments'/path.name,**kw)
    monkeypatch.setattr(sys,'argv',['test_harbor_pipeline.py',*args])
    return module


def test_pick_fixture_and_budget_defaults():
    config=load_config(ROOT/'configs/harbor/experiments/cube_pick_place_rollout.yaml')
    assert config['usage']['limits']=={'input_tokens':3_000_000,'output_tokens':1_000_000}
    instance=config['instances'][0]
    assert instance['fixture']==instance['simulator']['task_id']=='cube_pick_place'
    assert instance['evaluation']=='task_success' and instance['state_fields']==['world']
    assert instance['simulator']['control_mode']=='EE_ABS'
    assert instance['initial_observation_steps']==5


@pytest.mark.parametrize('case',['pick-cube','budget-input','budget-output'])
def test_api_gate_precedes_any_preparation(monkeypatch,tmp_path,case):
    module=script(monkeypatch,tmp_path,['--case',case,'--model','openrouter/test/model'])
    with pytest.raises(SystemExit) as result: module.main()
    assert result.value.code==2 and not (tmp_path/'runs').exists()


@pytest.mark.parametrize('case',['pick-cube','pick-cube-scripted','budget-input','budget-output'])
def test_prepare_only_generates_real_native_tasks(monkeypatch,tmp_path,case):
    module=script(monkeypatch,tmp_path,['--case',case,'--prepare-only','--run-id','prepare-test',
        '--model','openrouter/test/model'])
    assert module.main()==0
    run=tmp_path/'runs/harbor/prepare-test'
    config=json.loads((run/'experiment.resolved.json').read_text())
    assert config['instances'][0]['fixture']=='cube_pick_place'
    instruction=(run/'harbor_tasks/cube-pick-place-seed0/instruction.md').read_text()
    for command in ('topogym-rollout history','topogym-rollout logs --segment 0',
                    'topogym-rollout frames --segment 0', 'Open the returned',
                    'does NOT contain the individual steps'):
        assert command in instruction
    sources=json.loads((run/'rollout_sources.resolved.json').read_text())
    assert 'topogym/agents/rollout/history.py' in sources
    assert 'topogym/simulator/rollout_simulation/history.py' in sources
    if case=='pick-cube-scripted':
        assert config['usage']=={'mode':'off'}
        assert config['execution']=={'harness':'scripted','scenario':'pick-cube'}
    elif case=='pick-cube':
        assert config['usage']['limits']['output_tokens']==1_000_000
    elif case=='budget-input': assert config['usage']['limits']['input_tokens']==1
    else: assert config['usage']['limits']['output_tokens']==1024
    report=json.loads((tmp_path/'runs/test_results/prepare-test/report.json').read_text())
    assert report['status']=='prepared_only'


def test_initial_observation_cli_override(monkeypatch,tmp_path):
    module=script(monkeypatch,tmp_path,['--case','pick-cube-scripted','--prepare-only',
        '--run-id','initial-steps','--initial-observation-steps','3'])
    assert module.main()==0
    config=json.loads((tmp_path/'runs/harbor/initial-steps/experiment.resolved.json').read_text())
    assert config['instances'][0]['initial_observation_steps']==3


@pytest.mark.parametrize('value',[-1,True,1.5,1001])
def test_invalid_initial_observation_steps_rejected(value):
    from harbor_runners.config import validate
    config=load_config(ROOT/'configs/harbor/experiments/cube_pick_place_rollout.yaml')
    config['instances'][0]['initial_observation_steps']=value
    with pytest.raises(ValueError,match='initial_observation_steps'):
        validate(config)


def test_unsolved_pick_never_passes_just_because_pipeline_succeeded(monkeypatch,tmp_path):
    module=script(monkeypatch,tmp_path,['--case','pick-cube','--run-id','unsolved',
        '--model','openrouter/test/model','--allow-api'])
    def launch(run, root, **kwargs):
        (run/'rollout_index.json').write_text(json.dumps({'expected_trials':1,'pipeline_passed':True,
            'trials':{'t':{'pipeline_passed':True,'budget_qualified':True,
            'verification':{'task_success':False,'reward':0}}}}))
        return 0
    module.launch=launch
    assert module.main()==1
    report=json.loads((tmp_path/'runs/test_results/unsolved/report.json').read_text())
    assert report['expectation_met'] is False
