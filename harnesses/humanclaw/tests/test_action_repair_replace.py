"""Destructive replacement requires exact identity and survives interrupted renames."""
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location('repair_replace', Path(__file__).parents[1] / 'tools/action_repair_replace.py')
replace = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(replace)


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    own = tmp_path / 'owned'
    own.mkdir()
    monkeypatch.setattr(replace, 'OWN_ROOT', own)
    repair = own / 'suite' / replace.CAMPAIGN / 'results/shard-0001'
    attempt = repair / 'attempt-new'
    source = attempt / 'rollout'
    target = own / 'suite/results/shard-0001'
    relative = Path('scene_ep1_bed/rollout_00/experiment_runs')
    old = target / relative / 'run_old'
    new = source / relative / 'run_new'
    old.mkdir(parents=True)
    new.mkdir(parents=True)
    replace.write(old / 'run.json', {'run_id': 'run_old', 'original': True})
    (old / 'old_payload').write_bytes(b'original video and actions')
    (target / 'metrics_summary.json').write_text('old score')
    manifest = {'run_id': 'run_new', 'status': 'completed', 'outcome': {'task_success': False},
                'metadata': {'episode_id': '1', 'harness': 'codex', 'action_repair': {'old_run_id': 'run_old'}}}
    replace.write(new / 'run.json', manifest)
    (new / 'new_payload').write_bytes(b'new video and actions')
    result = {'ok': True, 'errors': [], 'trace': {'ok': True, 'warnings': []}, 'model_calls': 2,
              'run': str(new), 'run_sha256': replace.digest(new / 'run.json'), 'task_success': False}
    replace.write(repair / 'validated_result.json', {'status': 'completed', 'attempt': str(attempt), 'result': result})
    entry = {'index': 0, 'cohort': 'codex_r1', 'suite': 'suite', 'shard': 'shard-0001', 'episode': '1',
             'destination': str(repair), 'local_copy_run': str(old), 'old_run_id': 'run_old',
             'old_run_sha256': replace.digest(old / 'run.json')}
    plan = {'destination_root': str(own), 'provider_change': {'from': 'Copilot/Magpie', 'to': 'Azure'},
            'entries': [entry]}
    report = SimpleNamespace(validate_trace=lambda path: {'ok': True, 'warnings': []},
                             summarize_runs=lambda path, write: {'runs': ['run_new'], 'root': str(path)})
    monkeypatch.setattr(replace, 'reporting', lambda p, e: (report, lambda path, write_summary: {'new_score': True}))
    return SimpleNamespace(plan=plan, entry=entry, old=old, new=new, source=source, target=target,
                           repair=repair, relative=relative, report=report, own=own)


def test_preview_does_not_delete_or_move(campaign):
    c = campaign
    preview = replace.replacement(c.plan, c.entry)
    assert preview['status'] == 'ready'
    assert c.old.is_dir() and c.new.is_dir() and not c.source.is_symlink()


def test_completed_task_failure_replaces_entire_shard_without_duplicate_payload(campaign):
    c = campaign
    original_new = (c.new / 'run.json').read_bytes()
    result = replace.replacement(c.plan, c.entry, apply=True)
    canonical = c.target / c.relative / 'run_new'
    assert result['status'] == 'replaced_old_deleted'
    assert not c.old.exists() and not list(c.target.parent.glob('.*.replaced-*'))
    assert c.source.is_symlink() and c.source.resolve() == c.target
    assert (canonical / 'run.json').read_bytes() == original_new
    assert (c.new / 'new_payload').read_bytes() == b'new video and actions'
    assert json.loads((c.target / 'metrics_summary.json').read_text()) == {'new_score': True}
    assert not list(c.own.rglob('old_payload'))
    assert len(list(c.own.rglob('new_payload'))) == 1
    assert replace.replacement(c.plan, c.entry, apply=True)['already_applied']


@pytest.mark.parametrize('problem', ['incomplete', 'old_changed', 'new_changed', 'different_episode', 'another_run', 'another_episode'])
def test_refuses_unsafe_replacement_and_keeps_original(campaign, problem):
    c = campaign
    if problem == 'incomplete':
        value = replace.read(c.repair / 'validated_result.json')
        value['status'] = 'failed'
        replace.write(c.repair / 'validated_result.json', value)
    elif problem == 'old_changed':
        (c.old / 'run.json').write_text('changed')
    elif problem == 'new_changed':
        (c.new / 'run.json').write_text('changed')
    elif problem == 'different_episode':
        c.entry['episode'] = '999'
    elif problem == 'another_run':
        other = c.old.parent / 'run_other'
        other.mkdir()
        (other / 'run.json').write_text('{}')
    elif problem == 'another_episode':
        (c.target / 'unrelated_episode').mkdir()
    with pytest.raises((ValueError, json.JSONDecodeError)):
        replace.replacement(c.plan, c.entry, apply=True)
    assert (c.old / 'old_payload').is_file()
    assert (c.new / 'new_payload').is_file()


def test_symlink_to_coauthor_directory_is_never_followed_for_deletion(campaign, tmp_path):
    c = campaign
    external = tmp_path / 'coauthor'
    c.target.rename(external)
    c.target.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink'):
        replace.replacement(c.plan, c.entry, apply=True)
    assert (external / c.relative / 'run_old/old_payload').is_file()


@pytest.mark.parametrize('interrupt_at', ['new_move', 'delete'])
def test_interrupted_transaction_can_finish_without_losing_new_run(campaign, monkeypatch, interrupt_at):
    c = campaign
    real_move, real_delete = replace.os.replace, replace.shutil.rmtree
    def move(source, destination):
        if Path(source) == c.source:
            raise OSError('simulated interrupted installation')
        return real_move(source, destination)
    def delete(path):
        raise OSError('simulated interrupted deletion')
    with monkeypatch.context() as m:
        if interrupt_at == 'new_move':
            m.setattr(replace.os, 'replace', move)
        else:
            m.setattr(replace.shutil, 'rmtree', delete)
        with pytest.raises(OSError):
            replace.replacement(c.plan, c.entry, apply=True)
    assert (c.new / 'new_payload').is_file()
    result = replace.replacement(c.plan, c.entry, apply=True)
    assert result['status'] == 'replaced_old_deleted'
    assert not list(c.target.parent.glob('.*.replaced-*'))


def test_install_when_no_owned_original_exists_never_touches_coauthor(campaign):
    c = campaign
    replace.shutil.rmtree(c.target)
    result = replace.replacement(c.plan, c.entry, apply=True)
    assert result['old_copy_present'] is False
    assert result['old_data']['allocated_bytes'] == 0
    assert (c.target / c.relative / 'run_new/new_payload').is_file()


def test_failed_post_move_trace_check_does_not_delete_original(campaign):
    c = campaign
    c.report.validate_trace = lambda path: {'ok': Path(path).is_relative_to(c.source), 'warnings': []}
    with pytest.raises(ValueError, match='Installed trace'):
        replace.replacement(c.plan, c.entry, apply=True)
    staged = list(c.target.parent.glob('.*.replaced-*'))
    assert len(staged) == 1
    assert (staged[0] / c.relative / 'run_old/old_payload').is_file()


@pytest.mark.parametrize('change_payload', [False, True])
def test_gpfs_root_directory_mtime_can_change_but_payload_cannot(campaign, monkeypatch, change_payload):
    c = campaign
    original = replace.os.replace
    def gpfs_move(source, target):
        original(source, target)
        if Path(source) == c.source:
            moved = Path(target)
            before = moved.stat()
            os.utime(moved, ns=(before.st_atime_ns, before.st_mtime_ns + 1000000000))
            if change_payload:
                (moved / c.relative / 'run_new/new_payload').write_bytes(b'CORRUPTED')
    monkeypatch.setattr(replace.os, 'replace', gpfs_move)
    if change_payload:
        with pytest.raises(ValueError, match='Payload changed during installation'):
            replace.replacement(c.plan, c.entry, apply=True)
        assert list(c.target.parent.glob('.*.replaced-*'))
    else:
        assert replace.replacement(c.plan, c.entry, apply=True)['status'] == 'replaced_old_deleted'


def test_explicit_prune_keeps_validated_results(campaign):
    c = campaign
    assert replace.prune_confirmed_original(c.plan, c.entry, apply=True)['status'] == 'retained_validated_episode'
    assert c.old.exists() and c.new.exists()


def test_explicit_prune_deletes_only_audited_old_shard_then_allows_new_install(campaign):
    c = campaign
    validated = (c.repair / 'validated_result.json').read_bytes()
    (c.repair / 'validated_result.json').unlink()
    preview = replace.prune_confirmed_original(c.plan, c.entry)
    assert preview['status'] == 'ready_to_prune' and c.old.exists()
    result = replace.prune_confirmed_original(c.plan, c.entry, apply=True)
    assert result['status'] == 'original_deleted_before_rerun'
    assert not c.target.exists() and c.new.exists()
    assert replace.prune_confirmed_original(c.plan, c.entry, apply=True)['already_applied']
    (c.repair / 'validated_result.json').write_bytes(validated)
    assert replace.replacement(c.plan, c.entry, apply=True)['old_copy_present'] is False


def test_prune_refuses_wrong_old_identity(campaign):
    c = campaign
    (c.repair / 'validated_result.json').unlink()
    (c.old / 'run.json').write_text('{}')
    with pytest.raises(ValueError, match='differs from audited'):
        replace.prune_confirmed_original(c.plan, c.entry, apply=True)
    assert (c.old / 'old_payload').exists()


def test_prune_recovers_interrupted_deletion_without_touching_new_payload(campaign, monkeypatch):
    c = campaign
    (c.repair / 'validated_result.json').unlink()
    original = replace.shutil.rmtree
    def partial(path):
        (c.old / 'run.json').unlink()
        raise OSError('interrupted old deletion')
    with monkeypatch.context() as m:
        m.setattr(replace.shutil, 'rmtree', partial)
        with pytest.raises(OSError):
            replace.prune_confirmed_original(c.plan, c.entry, apply=True)
    assert replace.prune_confirmed_original(c.plan, c.entry, apply=True)['status'] == 'original_deleted_before_rerun'
    assert c.new.exists() and not c.target.exists()


@pytest.mark.parametrize('problem', [None, 'different_episode', 'newer', 'changed_source', 'corrected'])
@pytest.mark.parametrize('old_status', ['interrupted', 'completed', 'running'])
def test_prune_includes_only_verified_earlier_original_attempts(campaign, tmp_path, problem, old_status):
    c = campaign
    (c.repair / 'validated_result.json').unlink()
    selected = {'run_id': 'run_old', 'status': 'completed', 'started_at_utc': '2026-10-18T00:00:00Z',
                'metadata': {'episode': {'name': 'scene_episode1'}}}
    replace.write(c.old / 'run.json', selected)
    c.entry['old_run_sha256'] = replace.digest(c.old / 'run.json')
    reference = tmp_path / 'read_only_source/experiment_runs/run_old'
    reference.mkdir(parents=True)
    c.entry['source_run'] = str(reference)
    failed = {**selected, 'run_id': 'run_failed', 'status': old_status,
              'started_at_utc': '2026-10-17T00:00:00Z'}
    if problem == 'different_episode':
        failed['metadata'] = {'episode': {'name': 'unrelated_episode'}}
    elif problem == 'newer':
        failed['started_at_utc'] = '2026-10-19T00:00:00Z'
    elif problem == 'corrected':
        failed['metadata'] = {**failed['metadata'], 'action_repair': {}}
    extra = c.old.parent / 'run_failed'
    extra.mkdir()
    source_extra = reference.parent / 'run_failed'
    source_extra.mkdir()
    replace.write(extra / 'run.json', failed)
    replace.write(source_extra / 'run.json', failed if problem != 'changed_source' else {})
    if problem:
        with pytest.raises(ValueError, match='unverified additional run'):
            replace.prune_confirmed_original(c.plan, c.entry, apply=True)
        assert c.target.exists() and c.new.exists()
    else:
        result = replace.prune_confirmed_original(c.plan, c.entry, apply=True)
        assert len(result['additional_original_attempts']) == 1
        assert not c.target.exists() and c.new.exists()
    assert (source_extra / 'run.json').exists()
