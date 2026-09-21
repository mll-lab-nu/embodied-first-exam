"""Token reservations and real local Codex transport, with no OpenAI requests."""
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from topogym.agent_rollout.agents import CodexAgent
from topogym.agent_rollout.budget_proxy import BudgetProxy
from topogym.agent_rollout.token_budget import TokenBudget, TokenBudgetExhausted
from topogym.agent_rollout.isolation import sandbox_command


def usage(inputs, outputs):
    return dict(input_tokens=inputs, output_tokens=outputs, total_tokens=inputs+outputs)


class FakeOpenAI:
    def __init__(self, *, missing_usage=False, input_tokens=40, output_tokens=10):
        self.calls = []
        self.missing_usage = missing_usage
        self.input_tokens, self.output_tokens = input_tokens, output_tokens

    def __call__(self, path, payload):
        self.calls.append((path, payload))
        if path.endswith('input_tokens'):
            return io.BytesIO(json.dumps(dict(input_tokens=self.input_tokens)).encode())
        text = json.dumps(dict(kind='stop', code='', paths=[], reason='Local protocol test complete.'))
        receipt = None if self.missing_usage else usage(self.input_tokens, self.output_tokens)
        message = dict(id='msg_test', type='message', role='assistant', status='completed',
                       content=[dict(type='output_text', text=text, annotations=[])])
        response = dict(id=f'resp_{len(self.calls)}', object='response', model=payload['model'],
                        status='completed', output=[message], usage=receipt)
        if not payload.get('stream'):
            return io.BytesIO(json.dumps(response).encode())
        events = [dict(type='response.created', response=dict(response, status='in_progress', output=[])),
                  dict(type='response.output_item.added', output_index=0,
                       item=dict(message, status='in_progress', content=[])),
                  dict(type='response.output_text.delta', item_id='msg_test', output_index=0,
                       content_index=0, delta=text),
                  dict(type='response.output_item.done', output_index=0, item=message),
                  dict(type='response.completed', response=response)]
        return io.BytesIO(b''.join(b'data: '+json.dumps(dict(event, sequence_number=i)).encode()+b'\n\n'
                                  for i, event in enumerate(events)))


class BudgetChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private, self.public = self.root/'private', self.root/'public'
        self.private.mkdir()
        self.public.mkdir()
        (self.public/'scratch').mkdir()
        self.budget = TokenBudget(self.private, self.public, 100)

    def proxy(self, backend):
        result = BudgetProxy('fake-test-key', 'gpt-6-astra', self.budget,
                             max_output_tokens=80, timeout_s=5, transport=backend)
        self.addCleanup(result.close)
        return result

    def post(self, proxy, payload):
        request = Request(proxy.base_url+'/responses', data=json.dumps(payload).encode(),
                          headers={'Authorization': 'Bearer '+proxy.token, 'Content-Type': 'application/json'})
        return build_opener(ProxyHandler({})).open(request, timeout=5)

    def test_reservation_caps_next_request_and_counts_subsets_once(self):
        request, cap = self.budget.reserve(40, 80)
        self.assertEqual(cap, 60)
        self.assertEqual(self.budget.snapshot()['reserved'], 100)
        receipt = dict(usage(40, 10), input_tokens_details={'cached_tokens': 30},
                       output_tokens_details={'reasoning_tokens': 8})
        self.budget.complete(request, receipt)
        self.budget.complete(request, receipt)  # Identical receipt is idempotent.
        self.assertEqual(self.budget.snapshot()['used'], 50)
        with self.assertRaises(TokenBudgetExhausted):
            self.budget.reserve(50, 10)
        self.assertEqual(len(self.budget.calls), 1)
        self.assertIn('50 / 100', self.budget.notice())

    def test_unknown_usage_keeps_reservation_and_blocks_more_requests(self):
        fake = FakeOpenAI(missing_usage=True)
        proxy = self.proxy(fake)
        with self.post(proxy, dict(model='gpt-6-astra', input='one', stream=True)) as stream:
            stream.read()
        state = self.budget.snapshot()
        self.assertFalse(state['usage_complete'])
        self.assertEqual(state['reserved'], 100)
        self.assertEqual(state['blocked'], 'usage_unknown')
        with self.assertRaises(HTTPError):
            self.post(proxy, dict(model='gpt-6-astra', input='retry'))
        self.assertEqual(len(fake.calls), 2)

    def test_proxy_counts_full_multimodal_payload_before_generation(self):
        fake = FakeOpenAI()
        proxy = self.proxy(fake)
        payload = dict(model='gpt-6-astra', input=[dict(role='user', content=[
            dict(type='input_text', text='inspect'), dict(type='input_image', image_url='data:image/png;base64,AA==')])],
            tools=[dict(type='function', name='look', parameters=dict(type='object'))],
            instructions='Original instruction', text=dict(format=dict(type='json_object')),
            stream=False, max_output_tokens=999)
        with self.post(proxy, payload) as stream:
            self.assertEqual(json.load(stream)['usage']['total_tokens'], 50)
        count_path, count = fake.calls[0]
        generation_path, generation = fake.calls[1]
        self.assertEqual([count_path, generation_path], ['/responses/input_tokens', '/responses'])
        for field in ('input', 'tools', 'instructions', 'text'):
            self.assertEqual(count[field], generation[field])
        self.assertIn('0 / 100', count['instructions'])
        self.assertEqual(generation['max_output_tokens'], 60)
        self.assertNotIn('max_output_tokens', count)
        self.assertNotIn('stream', count)
        self.assertEqual(self.budget.snapshot()['used'], 50)
        self.assertNotIn('fake-test-key', (self.private/'token_budget.json').read_text())

    def test_preflight_count_failure_never_generates_or_retries(self):
        calls = []
        def fail(path, payload):
            calls.append(path)
            raise HTTPError('https://api.openai.com', 429, 'quota', {},
                            io.BytesIO(b'{"error":{"message":"You have no credits remaining"}}'))
        proxy = self.proxy(fail)
        for _ in range(2):
            with self.assertRaises(HTTPError):
                self.post(proxy, dict(model='gpt-6-astra', input='test'))
        self.assertEqual(calls, ['/responses/input_tokens'])
        self.assertIn('no credits remaining', self.budget.reason)
        self.assertEqual(self.budget.snapshot()['requests'], 0)

    def test_closing_attempt_during_count_cannot_start_generation(self):
        entered, release = threading.Event(), threading.Event()
        calls, errors = [], []
        def delayed(path, payload):
            calls.append(path)
            entered.set()
            release.wait(timeout=5)
            return io.BytesIO(b'{"input_tokens":40}')
        proxy = self.proxy(delayed)
        def client():
            try:
                self.post(proxy, dict(model='gpt-6-astra', input='test'))
            except HTTPError as exc:
                errors.append(exc.code)
        thread = threading.Thread(target=client)
        thread.start()
        try:
            self.assertTrue(entered.wait(timeout=2))
            proxy.close()
        finally:
            release.set()
            thread.join(timeout=5)
        self.assertEqual(errors, [400])
        self.assertEqual(calls, ['/responses/input_tokens'])
        self.assertEqual(self.budget.snapshot()['reserved'], 0)

    def test_budget_exhaustion_blocks_billable_request(self):
        fake = FakeOpenAI(input_tokens=100)
        proxy = self.proxy(fake)
        with self.assertRaises(HTTPError):
            self.post(proxy, dict(model='gpt-6-astra', input='too large'))
        self.assertEqual([p for p, _ in fake.calls], ['/responses/input_tokens'])
        self.assertEqual(self.budget.blocked, 'token_budget_exhausted')

    def test_unknown_input_fields_and_hosted_tools_are_rejected(self):
        for extra in (dict(context_management=[{}]), dict(tools=[dict(type='web_search')])):
            fake = FakeOpenAI()
            # A fresh ledger per rejection because the proxy deliberately fails closed.
            self.budget = TokenBudget(self.private, self.public, 100)
            proxy = self.proxy(fake)
            with self.assertRaises(HTTPError):
                self.post(proxy, dict(model='gpt-6-astra', input='test', **extra))
            self.assertEqual(fake.calls, [])

    def test_receipt_exceeding_reservation_is_recorded_and_stops(self):
        request, _ = self.budget.reserve(20, 10)
        with self.assertRaises(RuntimeError):
            self.budget.complete(request, usage(25, 10))
        self.assertEqual(self.budget.snapshot()['used'], 35)
        self.assertEqual(self.budget.blocked, 'reservation_exceeded')
        with self.assertRaises(RuntimeError):
            self.budget.reserve(10, 5)

    def test_budgeted_sandbox_does_not_receive_real_credentials(self):
        home, output, original_home = self.root/'home', self.root/'output', self.root/'original_home'
        for path in (home, output, original_home):
            path.mkdir()
        auth = original_home/'auth.json'
        auth.write_text('{"OPENAI_API_KEY":"fake-stored-key"}')
        with patch.dict(os.environ, {'CODEX_HOME': str(original_home), 'OPENAI_API_KEY': 'fake-openai-key',
                                     'CODEX_API_KEY': 'fake-codex-key'}):
            args, env = sandbox_command(['codex', '--help'], self.public, home, output, inherit_auth=False)
        self.assertNotIn(str(auth), args)
        self.assertNotIn('OPENAI_API_KEY', env)
        self.assertNotIn('CODEX_API_KEY', env)

    def test_runtime_surfaces_budget_exhaustion_and_preserves_ledger(self):
        from types import SimpleNamespace
        from topogym.agent_rollout.runtime import run_repeat
        from topogym.agent_rollout.suite import prepare
        suite = prepare(self.root/'suite', {'counter': 'topogym.agent_rollout.suite:prepare_counter'})
        def exhausted(*args):
            self.budget.reserve(100, 10)
        fake_agent = SimpleNamespace(isolation='test', budget=self.budget, decide=exhausted)
        job = dict(public=str(self.root/'runtime_public'), private=str(self.root/'runtime_private'),
            agent=dict(id='test', provider='replay', mode='rgb'), repeat=1,
            preset=str(suite.parent/'counter/rollout_1.json'), max_steps=10, max_calls=2,
            max_segments=2, max_total_steps=10, samples_per_camera=2)
        with patch('topogym.agent_rollout.runtime.create_agent', return_value=fake_agent), \
                patch('topogym.agent_rollout.runtime.publish_segment', return_value=dict(model_inputs=[])):
            result = run_repeat(job)
        self.assertEqual(result['status'], 'token_budget_exhausted')
        self.assertEqual(result['ticks'], 0)
        self.assertEqual(result['token_budget']['limit'], 100)
        self.assertFalse(result['success_within_token_budget'])
        request = json.loads((Path(job['private'])/'call_1.request.json').read_text())
        self.assertIn('0 / 100 tokens used', request['prompt'])

    def test_real_codex_cli_uses_metered_proxy_and_resumes(self):
        from PIL import Image
        fake = FakeOpenAI()
        original = BudgetProxy.__init__
        def local_proxy(instance, *args, **kwargs):
            original(instance, *args, **dict(kwargs, transport=fake))
        Image.new('RGB', (32, 32), 'red').save(self.public/'test.png')
        with patch.dict(os.environ, {'CODEX_API_KEY': 'fake-test-key'}), \
                patch.object(BudgetProxy, '__init__', local_proxy):
            agent = CodexAgent(dict(model='gpt-6-astra', token_limit=1000, max_output_tokens=80,
                                    timeout_s=30), self.public, self.private)
            self.addCleanup(agent.close)
            for number in (1, 2):
                decision, receipt = agent.decide(dict(prompt='Return a stop decision.', images=['test.png']), number)
                self.assertEqual(decision['kind'], 'stop')
                self.assertEqual(receipt, usage(40, 10))
            self.assertEqual(agent.budget.snapshot()['used'], 100)
            self.assertEqual(len(fake.calls), 4)
            self.assertIn('50 / 1,000', fake.calls[2][1]['instructions'])


if __name__ == '__main__':
    unittest.main()
