from types import SimpleNamespace
import pytest
from topogym.agents.usage.config import BudgetSettings, validate_usage


def test_shared_settings_preserve_defaults_and_timing():
    result=BudgetSettings.from_mapping({'mode':'observed','limits':{'input_tokens':0}})
    assert result.policy.input_tokens==0 and result.policy.output_tokens==20_000_000
    assert result.watchdog_interval_ms==100 and result.stop_grace_ms==1000


def test_active_pipeline_rejects_off():
    with pytest.raises(ValueError,match='active pipeline'):
        BudgetSettings.from_mapping({'mode':'off'})


@pytest.mark.parametrize('field,value', [('watchdog_interval_ms',0),('stop_grace_ms',True),('watchdog_interval_ms',1001)])
def test_direct_settings_constructor_cannot_bypass_timing_validation(field,value):
    from topogym.agents.usage import BudgetPolicy
    with pytest.raises(ValueError): BudgetSettings(BudgetPolicy(),**{field:value})
