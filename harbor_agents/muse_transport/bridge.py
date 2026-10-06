"""Per-trial loopback transport, with sanitized provider error diagnostics.

Catalog/SSE schema compatibility follows the MIT project cited in PROVENANCE.json.
The exact selected model and complete conversation remain fixed across requests.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time
import uuid
from urllib.parse import quote, urlsplit

from .rewrite import rewrite_request, restore_response

UPSTREAM = 'https://openrouter.ai/api/v1'


def safe_error(value, key='', limit=2000):
    """Redact before shortening, including keys echoed by a provider or OS error."""
    text = str(value)
    if key:
        for secret in {key, json.dumps(key)[1:-1], quote(key, safe='')}:
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)\b(Bearer|Basic)\s+[^\s\"\',;}]+', r'\1 [REDACTED]', text)
    text = re.sub(r'(?:sk-[A-Za-z0-9_-]{16,}|hf_[A-Za-z0-9]{20,})', '[REDACTED]', text)
    text = re.sub(r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}', '[REDACTED]', text)
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
    return ' '.join(text.split())[:limit]


def provider_message(response, key, evidence=None):
    # Extract an error message only, never a whole request/response or headers.
    raw = response.read(65536)
    try:
        document = json.loads(raw)
        error = document.get('error', document)
        value = error.get('message', error.get('code', 'provider supplied no error message')) if isinstance(error, dict) else error
        # OpenRouter may wrap the actual provider rejection in metadata.raw.
        # Extract its error message, not the raw body, request or headers.
        if isinstance(error, dict):
            metadata = error.get('metadata') or {}
            if evidence is not None and isinstance(metadata, dict):
                for name in ('provider_name', 'model_slug'):
                    if isinstance(metadata.get(name), str):
                        evidence[name] = safe_error(metadata[name], key)
            nested = metadata.get('raw') if isinstance(metadata, dict) else None
            if isinstance(nested, str):
                try: nested = json.loads(nested)
                except ValueError: nested = None
            if isinstance(nested, dict):
                nested = nested.get('error', nested)
                detail = nested.get('message') if isinstance(nested, dict) else None
                if isinstance(detail, str) and detail != value: value = str(value)+'; provider: '+detail
    except (ValueError, AttributeError):
        value = 'non-JSON provider error: ' + raw.decode('utf-8', errors='replace')
    return safe_error(value, key)


class Bridge(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, key, model, logs, *, upstream=UPSTREAM):
        if not model.startswith('meta/muse'):
            raise ValueError('muse-openrouter requires a meta/muse model')
        self.key, self.model, self.upstream = key, model, upstream
        self.logs = Path(logs); self.logs.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock(); self.usage = {}; self.started = 0
        self.diagnostic_lock = threading.Lock()
        self.completed = 0; self.errors = []; self.error_details = []; self.metadata = None
        super().__init__(('127.0.0.1', 0), Handler)
        self.persist()

    def diagnostic(self, event, request_id=None, **fields):
        """Metadata only: never log prompts, tool arguments, keys or headers wholesale."""
        def scrub(value):
            if isinstance(value, str): return safe_error(value, self.key)
            if isinstance(value, dict): return {k: scrub(v) for k, v in value.items()}
            if isinstance(value, list): return [scrub(v) for v in value]
            return value
        row = scrub(dict(time=time.time(), event=event, request_id=request_id, **fields))
        with self.diagnostic_lock:
            with (self.logs/'openrouter-requests.jsonl').open('a') as stream:
                stream.write(json.dumps(row)+'\n')

    def connection(self):
        target = urlsplit(self.upstream)
        cls = http.client.HTTPSConnection if target.scheme == 'https' else http.client.HTTPConnection
        return cls(target.hostname, target.port, timeout=600), target.path.rstrip('/')

    def headers(self):
        return {'Authorization': 'Bearer '+self.key, 'Content-Type': 'application/json',
                'Accept-Encoding': 'identity', 'X-Title': 'TopoGym Muse OpenRouter'}

    def persist(self):
        totals = {k: sum(row[k] for row in self.usage.values())
                  for k in ('input_tokens', 'output_tokens', 'cached_tokens')}
        data = dict(model=self.model, requests=self.started, completed=self.completed,
                    responses=self.usage, totals=totals, errors=self.errors, error_details=self.error_details,
                    complete=bool(self.started) and self.started == self.completed and not self.errors)
        path = self.logs/'openrouter-usage.json'; temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data, indent=2)+'\n'); temporary.replace(path)

    def fail(self, code, detail=None, *, request_id=None, phase=None):
        self.diagnostic('request_error', request_id, code=code, phase=phase,
                        message=safe_error(detail, self.key) if detail is not None else None)
        with self.lock:
            self.errors.append(code)
            if detail is not None:
                self.error_details.append(dict(code=code, message=safe_error(detail, self.key),
                                               request_id=request_id, phase=phase))
                self.error_details = self.error_details[-20:]
            self.persist()

    def record(self, payload, request_id=None):
        response = payload.get('response', payload)
        self.diagnostic('upstream_terminal', request_id, response_id=response.get('id'),
                        response_model=response.get('model'), status=response.get('status'),
                        event_type=payload.get('type'), usage_present=isinstance(response.get('usage'), dict))
        if payload.get('type') not in (None, 'response.completed', 'response.incomplete'):
            if payload.get('type') in ('error', 'response.failed'):
                error = response.get('error') or payload.get('error') or payload
                detail = error.get('message', error.get('code', 'response failed')) if isinstance(error, dict) else error
                self.fail('provider_response_failed', detail, request_id=request_id, phase='upstream_terminal')
            return
        usage = response.get('usage'); rid = response.get('id')
        if not rid or not isinstance(usage, dict):
            self.fail('response_usage_missing', request_id=request_id, phase='upstream_terminal'); return
        counts = {k: usage.get(k) for k in ('input_tokens', 'output_tokens')}
        counts['cached_tokens'] = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
        if any(type(n) is not int or n < 0 for n in counts.values()):
            self.fail('response_usage_invalid', request_id=request_id, phase='upstream_terminal'); return
        with self.lock:
            duplicate = rid in self.usage
            if rid in self.usage:
                if self.usage[rid] != counts: self.errors.append('duplicate_response_usage_mismatch')
            else:
                self.usage[rid] = counts; self.completed += 1
            self.persist()
        self.diagnostic('usage_recorded', request_id, response_id=rid, usage=counts,
                        duplicate=duplicate, included_in_totals=not duplicate)

    def catalog(self):
        if self.metadata is None:
            conn, base = self.connection()
            try:
                conn.request('GET', base+'/models', headers=self.headers())
                r = conn.getresponse()
                if r.status != 200:
                    code = 'catalog_http_'+str(r.status)
                    detail = provider_message(r, self.key); self.fail(code, detail)
                    raise ValueError(code+': '+detail)
                models = json.loads(r.read())['data']
                self.metadata = next((m for m in models if m.get('id') == self.model), None)
                if self.metadata is None: raise ValueError('selected_model_unavailable')
            finally:
                conn.close()
        m = self.metadata
        context = m.get('context_length')
        output = (m.get('top_provider') or {}).get('max_completion_tokens')
        if type(context) is not int or context <= 0: raise ValueError('catalog_context_missing')
        # Same conservative per-response cap advertised by the reference bridge.
        output = min(output if type(output) is int and output > 0 else 16384, 16384, context)
        row = dict(id=self.model, model_id=self.model, provider_id='meta', profile_id='tbh',
                   display_label=self.model, title=self.model, visibility='visible', display_order=0,
                   is_default=True, is_current=True, context_limit=context, output_limit=output,
                   description='TopoGym OpenRouter adapter',
                   metadata=dict(family='muse', is_hidden=False, limit=dict(context=context)))
        return dict(schema_version=1, data=[row])


class Handler(BaseHTTPRequestHandler):
    # HTTP/1.0 close-delimited SSE avoids inventing a Content-Length for a stream.
    def log_message(self, *args): pass

    def reply(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_GET(self):
        if self.path.split('?')[0].rstrip('/') not in ('/muse-code/models','/models'):
            self.reply(404, {'error': {'message': 'unsupported adapter endpoint'}}); return
        try: self.reply(200, self.server.catalog())
        except Exception as exc:
            self.server.fail('catalog_failed', type(exc).__name__+': '+str(exc))
            self.reply(502, {'error': {'message': 'OpenRouter model catalog unavailable'}})

    def do_POST(self):
        bridge = self.server
        if self.path.rstrip('/') != '/responses':
            self.reply(404, {'error': {'message': 'unsupported adapter endpoint'}}); return
        conn = None; streaming = False
        request_id = uuid.uuid4().hex; started = time.monotonic()
        phase = 'read_local_request'; status = None
        upstream_bytes = downstream_bytes = events = 0
        terminal = False; forwarded_terminal = False
        bridge.diagnostic('request_started', request_id, model=bridge.model)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 128*1024*1024: raise ValueError('invalid_request_size')
            payload = json.loads(self.rfile.read(length))
            if payload.get('model') != bridge.model: raise ValueError('model_switch_forbidden')
            phase = 'model_catalog'
            limit = bridge.catalog()['data'][0]['output_limit']
            if type(payload.get('max_output_tokens')) is int:
                payload['max_output_tokens'] = min(payload['max_output_tokens'], limit)
            phase = 'rewrite_request'
            payload, aliases = rewrite_request(payload)
            with bridge.lock:
                bridge.started += 1; bridge.persist()
            phase = 'send_upstream_request'
            conn, base = bridge.connection()
            conn.request('POST', base+'/responses', body=json.dumps(payload).encode(), headers=bridge.headers())
            phase = 'read_upstream_headers'
            response = conn.getresponse()
            status = response.status
            bridge.diagnostic('upstream_headers', request_id, http_status=status,
                              # Allowlisted correlation headers only; no auth/cookies/body.
                              provider_request_id=response.getheader('x-request-id') or response.getheader('request-id'),
                              content_type=response.getheader('Content-Type'),
                              elapsed_s=round(time.monotonic()-started, 3))
            if response.status != 200:
                code = 'http_'+str(response.status)
                phase = 'read_upstream_error'; provider = {}
                detail = provider_message(response, bridge.key, provider)
                bridge.diagnostic('provider_rejection', request_id, http_status=status, **provider)
                bridge.fail(code, detail, request_id=request_id, phase=phase)
                phase = 'write_downstream_error'
                self.reply(response.status, {'error': {'message': 'OpenRouter '+code+': '+detail, 'code': response.status}})
                return
            if 'text/event-stream' not in response.getheader('Content-Type',''):
                phase = 'read_upstream_json'
                raw = response.read(); upstream_bytes += len(raw)
                data = json.loads(raw); bridge.record(data, request_id); terminal = True
                phase = 'write_downstream_json'
                self.reply(200, restore_response(data, aliases)); forwarded_terminal = True
                return
            phase = 'write_downstream_headers'
            self.send_response(200); self.send_header('Content-Type','text/event-stream')
            self.send_header('Cache-Control','no-cache'); self.end_headers(); streaming = True
            sequence = 0; lines = []
            def emit(lines):
                nonlocal sequence, terminal, phase, downstream_bytes, events, forwarded_terminal
                phase = 'decode_upstream_event'
                data = '\n'.join(line[5:].lstrip() for line in lines if line.startswith('data:'))
                if not data or data == '[DONE]': return
                obj = json.loads(data)
                is_terminal = obj.get('type') in ('response.completed','response.incomplete','response.failed','error')
                if is_terminal:
                    bridge.record(obj, request_id); terminal = True
                obj = restore_response(obj, aliases)
                obj['sequence_number'] = sequence; sequence += 1
                event = str(obj.get('type','message'))
                wire = ('event: '+event+'\ndata: '+json.dumps(obj)+'\n\n').encode()
                phase = 'write_downstream_event'
                self.wfile.write(wire); self.wfile.flush()
                downstream_bytes += len(wire); events += 1
                if is_terminal: forwarded_terminal = True
            phase = 'read_upstream_stream'
            for raw in response:
                upstream_bytes += len(raw)
                line = raw.decode('utf-8').rstrip('\r\n')
                if line: lines.append(line)
                else: emit(lines); lines = []
                phase = 'read_upstream_stream'
            if lines: emit(lines)
            if not terminal: bridge.fail('stream_ended_without_terminal_response', request_id=request_id, phase='upstream_eof')
        except Exception as exc:
            bridge.fail('transport_or_protocol_error', type(exc).__name__+': '+str(exc),
                        request_id=request_id, phase=phase)
            if not streaming:
                try: self.reply(502, {'error': {'message': 'OpenRouter adapter request failed; see openrouter-usage.json'}})
                except OSError: pass
        finally:
            if conn: conn.close()
            bridge.diagnostic('request_finished', request_id, last_phase=phase, http_status=status,
                              elapsed_s=round(time.monotonic()-started, 3),
                              upstream_bytes=upstream_bytes, downstream_stream_bytes=downstream_bytes,
                              forwarded_events=events, upstream_terminal_seen=terminal,
                              terminal_forwarded=forwarded_terminal)
