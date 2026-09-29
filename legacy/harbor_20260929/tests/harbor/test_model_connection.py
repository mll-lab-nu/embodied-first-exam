import io
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from harbor_runners.endpoints import split_model, resolve_model, CREDENTIAL_ENV
from harbor_runners.run import main, build_parser, config_from_args
from harbor_runners.config import load_config
from harbor_runners.task_generator import prepare

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("bad", [None,"","astra-6","/model","openrouter/","openrouter/a b",
    "openrouter/a;echo","openrouter/$(echo)","openrouter/a\nb","openrouter/a|cat",
    "openrouter/a\u0000","openrouter/a//b","openrouter/a/"])
def test_model_names_reject_missing_provider_and_shell_syntax(bad):
    with pytest.raises(ValueError):
        split_model(bad)


def test_unknown_provider_is_not_guessed_or_rerouted():
    with pytest.raises(ValueError,match="not registered"):
        resolve_model("unknown/model",version="1.18.33")


@pytest.mark.parametrize("version", [None,"latest","1.18","1.18.33;echo"])
def test_version_must_be_pinned(version):
    with pytest.raises(ValueError,match="pinned"):
        resolve_model("openrouter/test/model",version=version)


def test_two_input_cli_reaches_launch_and_auto_ids_are_unique(tmp_path,monkeypatch):
    import harbor_runners.run as runner
    calls=[]
    def launch(run,root,**kwargs):
        calls.append((run,root,kwargs))
        return 0
    monkeypatch.setattr(runner,"launch",launch)
    for _ in range(2):
        assert main(["run","--root",str(tmp_path),"--model-name","openrouter/meta/muse-spark-1.3-contributor",
                     "--api-key","request-specific-test-key"]) == 0
    assert len(calls)==2 and calls[0][0]!=calls[1][0]
    for run,root,kwargs in calls:
        assert kwargs["api_key"]=="request-specific-test-key"
        config=json.loads((run/"experiment.resolved.json").read_text())
        assert config["execution"]=={"harness":"opencode"}
        assert config["model_connection"]["model_id"]=="meta/muse-spark-1.3-contributor"
        assert "request-specific-test-key" not in (run/"job.json").read_text()


def test_stdin_key_and_30k_10k_single_trial(tmp_path,monkeypatch):
    import harbor_runners.run as runner
    calls=[]
    monkeypatch.setattr(runner.sys,"stdin",io.StringIO("stdin-test-key\n"))
    monkeypatch.setattr(runner,"launch",lambda run,root,**kw: calls.append((run,kw)) or 0)
    assert main(["run","--root",str(tmp_path),"--experiment","cube_pick_place_rollout",
        "--model","openrouter/meta/muse-spark-1.3-contributor","--api-key-stdin","--attempts","1",
        "--concurrency","1","--seeds","0","--input-token-limit","30000","--output-token-limit","10000"])==0
    run,kw=calls[0]
    config=json.loads((run/"experiment.resolved.json").read_text())
    manifest=json.loads((run/"manifest.json").read_text())
    assert kw["api_key"]=="stdin-test-key" and manifest["expected_trials"]==1
    assert config["usage"]["limits"]=={"input_tokens":30000,"output_tokens":10000}


def test_cli_overrides_apply_before_validation(tmp_path):
    # A preset intentionally omits the deployment image; an explicit override supplies it.
    preset=load_config()
    for field in ("image","providers_file","opencode_version","gpus"):
        preset.pop(field,None)
    path=tmp_path/"experiment.yaml"
    path.write_text(yaml.safe_dump(preset))
    defaults=tmp_path/"defaults.yaml"
    defaults.write_text(yaml.safe_dump(dict(schema_version=1,experiment_config="experiment.yaml",
        opencode_version="1.18.33",gpu_devices=["0"],gpus=1)))
    args=build_parser().parse_args(["prepare","--defaults",str(defaults),"--model-name","anthropic/test",
                                  "--image","local:test","--gpus","0"])
    config=config_from_args(args)
    assert config["image"]=="local:test" and config["gpus"]==0 and "gpu_devices" not in config


def test_location_options_work_before_or_after_subcommand(tmp_path):
    parser=build_parser()
    before=parser.parse_args(["--root",str(tmp_path),"prepare","--model","openai/test"])
    after=parser.parse_args(["prepare","--root",str(tmp_path),"--model","openai/test"])
    assert before.root==after.root==tmp_path


def test_explicit_zero_limits_and_invalid_limits(tmp_path):
    parser=build_parser()
    args=parser.parse_args(["prepare","--model","openrouter/test","--input-token-limit","0"])
    c=config_from_args(args)
    assert c["usage"]["limits"]["input_tokens"]==0
    c["usage"]["limits"]["output_tokens"]=-1
    with pytest.raises(ValueError):
        prepare(c,tmp_path,"negative")
    assert not (tmp_path/"runs").exists()


def test_production_cannot_turn_off_accounting(tmp_path):
    c=load_config(overrides={"model":"openrouter/test"})
    c["usage"]={"mode":"off"}
    with pytest.raises(ValueError,match="requires observed"):
        prepare(c,tmp_path,"off")
    assert not (tmp_path/"runs").exists()


def test_launch_passes_key_only_in_independent_child_env(tmp_path,monkeypatch,capsys):
    import harbor_runners.run as runner
    run=prepare(load_config(overrides={"model":"openrouter/test"}),tmp_path,"launch")
    seen=[]
    monkeypatch.setenv(CREDENTIAL_ENV,"ambient-key")
    monkeypatch.setattr(runner,"check",lambda run,**kw: seen.append(("check",kw["environ"])))
    def process(command,**kwargs):
        seen.append((command,kwargs))
        return SimpleNamespace(stdout=io.StringIO("finished\n"),wait=lambda:0)
    monkeypatch.setattr(runner.subprocess,"Popen",process)
    monkeypatch.setattr(runner,"collect",lambda *a: {"pipeline_passed":True})
    monkeypatch.setattr(runner,"summarize",lambda *a: {
        "run_dir":str(run),"collected_trials":1,"expected_trials":1,"pipeline_passed":True,
        "model":"test/explicit-key"})
    monkeypatch.setattr(runner,"cleanup",lambda *a: {"status":"removed"})
    assert runner.launch(run,tmp_path,api_key="explicit-key")==0
    assert seen[0][1][CREDENTIAL_ENV]=="explicit-key"
    command,kw=seen[1]
    assert kw["env"][CREDENTIAL_ENV]=="explicit-key" and "explicit-key" not in str(command)
    assert os.environ[CREDENTIAL_ENV]=="ambient-key"
    output=capsys.readouterr().out
    assert "TopoGym episode summary" in output and "Pipeline: PASS" in output
    assert "explicit-key" not in output and "test/[REDACTED]" in output
