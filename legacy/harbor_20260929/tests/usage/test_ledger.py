from concurrent.futures import ThreadPoolExecutor
import json
import pytest

from topogym.agents.usage import BudgetPolicy, BudgetStopped, CapacityUnavailable, UsageEvent, UsageLedger


def ledger(tmp_path, *, inputs=10, outputs=10, mode="observed"):
    return UsageLedger(tmp_path / "ledger.sqlite", scope_id="trial", policy=BudgetPolicy(inputs, outputs, mode))


def sent(book, identifier="r", **kwargs):
    book.admit(identifier, source="test", **kwargs)
    book.mark_sent(identifier)


def event(i=0, *, inputs=1, outputs=1, final=True, request="r", **kwargs):
    return UsageEvent(request, str(i), i, "test", inputs, outputs, final=final, **kwargs)


@pytest.mark.parametrize("dimension", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("amount,failed", [(9, False), (10, False), (11, True)])
def test_independent_inclusive_boundaries(tmp_path, dimension, amount, failed):
    book = ledger(tmp_path)
    sent(book)
    values = dict(inputs=1, outputs=1)
    values["inputs" if dimension == "input_tokens" else "outputs"] = amount
    result = book.record(event(**values))
    assert bool(result["stop"]) == failed
    assert result[dimension] == amount
    assert book.finalize()["budget_qualified"] == (not failed)
    if failed:
        assert result["stop"]["dimensions"] == [dimension]
        assert result["overshoot"][dimension] == 1


def test_exact_limit_then_next_request_is_exhausted(tmp_path):
    book = ledger(tmp_path)
    sent(book)
    book.record(event(inputs=10))
    with pytest.raises(BudgetStopped, match="budget_exhausted"):
        sent(book, "next")


def test_cumulative_delta_dedup_and_restored_process(tmp_path):
    book = ledger(tmp_path, inputs=100, outputs=100)
    sent(book)
    receipt = event(0, inputs=10, outputs=2, final=False)
    book.record(receipt)
    book = UsageLedger(tmp_path / "ledger.sqlite")
    book.record(receipt)
    book.record(event(1, inputs=10, outputs=5))
    sent(book, "retry")
    book.record(event(0, inputs=10, outputs=2, request="retry", semantics="delta", final=False))
    book.record(event(1, inputs=0, outputs=3, request="retry", semantics="delta"))
    assert book.snapshot()["usage"] == {"input_tokens": 20, "output_tokens": 10}
    assert book.finalize()["budget_qualified"]


def test_cumulative_reorder_does_not_double_count(tmp_path):
    book = ledger(tmp_path)
    sent(book)
    book.record(event(2, inputs=4, outputs=3, final=False))
    book.record(event(1, inputs=3, outputs=2, final=False))
    assert book.record(event(3, inputs=4, outputs=4))["output_tokens"] == 4
    assert book.finalize()["budget_qualified"]


@pytest.mark.parametrize("fault", ["rollback", "other_source", "delta_gap", "missing", "conflicting_id"])
def test_uncertain_usage_fails_closed(tmp_path, fault):
    book = ledger(tmp_path)
    sent(book)
    first = event(0, inputs=3, outputs=2, final=False)
    book.record(first)
    if fault == "rollback": receipt = event(1, inputs=2)
    elif fault == "other_source": receipt = UsageEvent("r", "1", 1, "untrusted", 3, 3, final=True)
    elif fault == "delta_gap": receipt = event(2, semantics="delta")
    elif fault == "conflicting_id": receipt = event(0, inputs=5)
    else:
        sent(book, "unknown")
        receipt = event(0, inputs=None, outputs=2, request="unknown")
    result = book.record(receipt)
    assert result["stop"] and not result["usage_complete"]
    assert not book.finalize()["budget_qualified"]


def test_concurrent_reservations_are_atomic_and_temporary_shortage_not_failure(tmp_path):
    book = ledger(tmp_path, mode="strict")
    def admit(i):
        try:
            sent(book, str(i), input_bound=6, output_bound=6)
            return str(i)
        except CapacityUnavailable:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = [i for i in pool.map(admit, range(8)) if i is not None]
    assert len(accepted) == 1
    assert book.snapshot()["stop"] is None
    book.record(event(request=accepted[0], inputs=2, outputs=2))
    sent(book, "later", input_bound=8, output_bound=8)


def test_partial_usage_reduces_reservation_not_twice(tmp_path):
    book = ledger(tmp_path, mode="strict")
    sent(book, input_bound=8, output_bound=8)
    result = book.record(event(inputs=4, outputs=3, final=False))
    assert result["pending_reservation"] == {"input_tokens": 4, "output_tokens": 5}
    assert result["remaining"] == {"input_tokens": 2, "output_tokens": 2}
    result = book.record(event(1, inputs=4, outputs=4))
    assert result["pending_reservation"] == {"input_tokens": 0, "output_tokens": 0}


def test_unknown_requests_retain_reservations_on_restart(tmp_path):
    from topogym.agents.usage.service import UsageService
    book = ledger(tmp_path, mode="strict")
    sent(book, input_bound=5, output_bound=5)
    service = UsageService(tmp_path, scope_id="trial", policy=BudgetPolicy(mode="strict"))
    try:
        result = service.ledger.snapshot()
        assert result["failure_reason"] == "usage_incomplete"
        assert result["pending_reservation"]["output_tokens"] == 5
        assert result["input_tokens"] is None and result["output_tokens"] is None
    finally:
        service.close()


def test_hot_update_revision_reduction_and_no_resurrection(tmp_path):
    book = ledger(tmp_path)
    sent(book)
    book.record(event(inputs=6, outputs=4))
    result = book.update_limits(input_tokens=5, output_tokens=10, expected_revision=1, actor="test", reason="reduce")
    assert result["failure_reason"] == "budget_exceeded"
    stop_id = result["stop"]["stop_id"]
    with pytest.raises(ValueError, match="revision"):
        book.update_limits(input_tokens=20, output_tokens=20, expected_revision=1, actor="test", reason="stale")
    result = book.update_limits(input_tokens=20, output_tokens=20, expected_revision=2, actor="test", reason="increase")
    assert result["stop"]["stop_id"] == stop_id
    assert not book.finalize()["budget_qualified"]


def test_late_receipt_can_complete_accounting_but_not_reverse_failure(tmp_path):
    book = ledger(tmp_path)
    sent(book, output_bound=5)
    book.fail("usage_incomplete", request_id="r")
    result = book.record(event(inputs=3, outputs=4))
    assert result["usage_complete"] and result["failure_reason"] == "usage_incomplete"
    assert result["pending_reservation"]["output_tokens"] == 0


def test_only_unsent_reservations_may_be_released(tmp_path):
    book=ledger(tmp_path,mode='strict')
    book.admit('unsent',source='test',input_bound=8,output_bound=8)
    book.release_unsent('unsent')
    assert book.snapshot()['remaining']=={'input_tokens':10,'output_tokens':10}
    sent(book,input_bound=8,output_bound=8)
    with pytest.raises(ValueError,match='sent request'): book.release_unsent('r')


def test_strict_under_reservation_and_committed_limit_reduction_stop(tmp_path):
    book=ledger(tmp_path,mode='strict',inputs=100,outputs=100)
    sent(book,input_bound=10,output_bound=10)
    assert book.record(event(inputs=11,outputs=1))['failure_reason']=='reservation_violation'
    other=ledger(tmp_path/'other',mode='strict',inputs=100,outputs=100)
    sent(other,input_bound=80,output_bound=80)
    result=other.update_limits(input_tokens=50,output_tokens=100,expected_revision=1,actor='test',reason='reduce')
    assert result['failure_reason']=='budget_exhausted' and not result['usage_complete']


def test_policy_update_does_not_rewrite_a_successful_final_result(tmp_path):
    book=ledger(tmp_path)
    sent(book);book.record(event())
    book.finalize()
    with pytest.raises(ValueError,match='finalized'):
        book.update_limits(input_tokens=0,output_tokens=0,expected_revision=1,actor='test',reason='late')


@pytest.mark.parametrize("value", [-1, 1.5, True, "10"])
def test_invalid_counts_never_silently_coerce(value):
    with pytest.raises(ValueError):
        BudgetPolicy(input_tokens=value)
