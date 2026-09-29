"""Run with the Harbor venv, without Genesis or the root simulator conftest."""
import importlib.util
from pathlib import Path
import shlex
import pytest
pytest.importorskip("harbor")
from topogym.benchmark.catalog import instances
from topogym.benchmark.export import export

ROOT=Path(__file__).resolve().parents[2]


def test_catalog_all_families_and_variations():
    base,_=instances()
    variants,excluded=instances(all_variants=True)
    assert len({x["simulator"]["task_id"] for x in base})==13
    assert len(variants)>len(base) and excluded
    assert all(x["simulator"]["seed"]==0 and x["simulator"]["max_physics_steps"] is None for x in variants)


def test_native_tasks_are_self_contained_and_fail_closed(tmp_path):
    from harbor.cli.add import _resolve_local_dataset, _resolve_local_task
    from harbor.publisher.packager import Packager
    root=export(ROOT,tmp_path/"tasks",instance_file=ROOT/"configs/benchmark/cube_pick_place.yaml")
    spec=importlib.util.spec_from_file_location("checker",ROOT/"scripts/check_benchmark_tasks.py")
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    assert checker.check(root)["tasks"]==2
    native_refs=_resolve_local_dataset(root)
    assert len(native_refs)==2
    for ref in native_refs:
        directory=root/ref.short_name
        assert ref==_resolve_local_task(directory)
        assert directory/"tests/source-manifest.json" in Packager.collect_files(directory)
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        dockerfile=directory/"tests/Dockerfile"
        original=dockerfile.read_text()
        # Reproduce the actual failure: the host script exists, but the separate
        # verifier image never receives it. A comment must not satisfy the check.
        dockerfile.write_text(original.replace("COPY --chmod=755 test.sh /tests/test.sh",
                                              "# COPY --chmod=755 test.sh /tests/test.sh"))
        try:
            with pytest.raises(AssertionError,match="must install /tests/test.sh"):
                checker.check(root)
        finally:
            dockerfile.write_text(original)
        script=directory/"tests/test.sh"
        original_script=script.read_text()
        script.write_text("#!/bin/sh\nif\n")
        try:
            with pytest.raises(AssertionError,match="Invalid verifier shell script"):
                checker.check_verifier_entrypoint(directory)
        finally:
            script.write_text(original_script)
    assert checker.check(root)["tasks"]==2
    with pytest.raises(FileExistsError):export(ROOT,root,task="cube_pick_place")


def test_codex_adapters_use_native_execution_and_preserve_model(tmp_path,monkeypatch):
    import asyncio
    from harbor.agents.installed.codex import Codex
    from topogym.benchmark.agents import CodexOpenRouter,CodexChatGPT
    adapter=CodexOpenRouter(logs_dir=tmp_path,model_name="openrouter/provider/nested-model",extra_env={"OPENROUTER_API_KEY":"fake-local-test", "OPENROUTER_BASE_URL":"https://example.invalid/v1"})
    config=adapter._build_effective_config("https://example.invalid/v1")
    assert config["model_providers"]["topogym_openrouter"]["wire_api"]=="responses"
    async def execute(self,environment,command,**kwargs):return command
    monkeypatch.setattr(Codex,"exec_as_agent",execute)
    command=asyncio.run(adapter.exec_as_agent(None,"codex exec --model nested-model --json -- 'prompt'"))
    assert shlex.split(command)[3]=="provider/nested-model"
    login=tmp_path/"auth.json";login.write_text("{}")
    chat=CodexChatGPT(logs_dir=tmp_path,model_name="openai/test-model",extra_env={"CODEX_AUTH_JSON_PATH":str(login)})
    assert chat._resolve_auth_json_path()==login
