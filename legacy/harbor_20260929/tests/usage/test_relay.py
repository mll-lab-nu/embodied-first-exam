import json
import threading
import time

from topogym.agents.usage import BudgetPolicy, UsageEvent
from topogym.agents.usage.gateway import Gateway
from topogym.agents.usage.relay import watch_budget
from topogym.agents.usage.service import UsageService


def test_live_public_snapshot_and_host_loss_watchdog(tmp_path):
    service=UsageService(tmp_path/'private',scope_id='t',policy=BudgetPolicy())
    gateway=Gateway(service,protocol='responses',upstream_url='http://127.0.0.1:1/v1',api_key='not-used',
                    socket_path=tmp_path/'gateway.sock')
    output=tmp_path/'public.json'
    shutdown, failed=threading.Event(),threading.Event()
    thread=threading.Thread(target=watch_budget,args=(str(tmp_path/'gateway.sock'),gateway.token,output,shutdown),
        kwargs={'interval':.01,'on_failure':lambda snapshot: failed.set()})
    thread.start()
    try:
        deadline=time.monotonic()+2
        while not output.exists() and time.monotonic()<deadline: time.sleep(.01)
        assert output.exists()
        service.ledger.admit('r',source='test'); service.ledger.mark_sent('r')
        service.record(UsageEvent('r','e',0,'test',12,3,final=True))
        while json.loads(output.read_text())['input_tokens']!=12 and time.monotonic()<deadline: time.sleep(.01)
        assert json.loads(output.read_text())['input_tokens']==12
        gateway.close()
        assert failed.wait(2)
    finally:
        shutdown.set(); thread.join(2); service.close()
