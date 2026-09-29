import json
import time
import threading
from pathlib import Path

import pytest

from topogym.agents.usage import BudgetPolicy, UsageEvent, UsageLedger
from topogym.agents.usage.service import UsageService


def record(service, request='r', inputs=2):
    service.ledger.admit(request, source='test', route_id='primary')
    service.ledger.mark_sent(request)
    service.record(UsageEvent(request, 'final', 0, 'test', inputs, 1, final=True))


def test_live_jsonl_export_does_not_wait_for_close_or_recount(tmp_path):
    service = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy(), interval=.01)
    try:
        record(service)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
            if any(row['kind'] == 'usage' for row in rows):
                break
            time.sleep(.01)
        assert any(row['kind'] == 'usage' for row in rows)
        assert len({row['audit_id'] for row in rows}) == len(rows)
        service.refresh(); service.refresh()
        assert service.ledger.snapshot()['input_tokens'] == 2
        assert len((tmp_path / 'events.jsonl').read_text().splitlines()) == len(rows)
    finally:
        service.close()
    assert rows == service.ledger.store.read_audit()


def test_owner_lock_prevents_second_publisher_but_allows_management(tmp_path):
    service = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy())
    try:
        with pytest.raises(RuntimeError, match='already owns'):
            UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy())
        manager = UsageLedger(tmp_path / 'ledger.sqlite')
        manager.update_limits(input_tokens=9, output_tokens=7, expected_revision=1, actor='test', reason='reduce')
        assert service.ledger.snapshot()['policy_revision'] == 2
    finally:
        service.close()


def test_restart_repairs_corrupt_export_from_database_without_recount(tmp_path):
    service = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy())
    record(service)
    service.close()
    (tmp_path / 'events.jsonl').write_text('wrong data\n{"audit_id":')
    recovered = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy())
    try:
        assert recovered.ledger.snapshot()['input_tokens'] == 2
        rows = [json.loads(line) for line in (tmp_path / 'events.jsonl').read_text().splitlines()]
        assert rows == recovered.ledger.store.read_audit()
    finally:
        recovered.close()


def test_export_failure_notifies_stop_and_latches_failure(tmp_path, monkeypatch):
    service = UsageService(tmp_path, scope_id='trial', policy=BudgetPolicy(), interval=.01)
    def broken(*args):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(service.publisher, 'publish', broken)
    try:
        assert service.stopped.wait(2)
        assert service.error == 'OSError'
        assert service.ledger.snapshot()['failure_reason'] == 'gateway_failed'
    finally:
        service.close()
