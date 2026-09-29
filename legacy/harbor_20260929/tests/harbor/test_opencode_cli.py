"""Opt-in real OpenCode binary against local HTTP fixtures, with no paid API calls.

TOPOGYM_TEST_OPENCODE=/absolute/path/opencode pytest .../test_opencode_cli.py
"""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading

import pytest

from harbor_runners.agents.opencode import bind
from harbor_runners.endpoints import resolve_model
from topogym.agents.usage import UsagePipeline

BINARY = os.environ.get("TOPOGYM_TEST_OPENCODE")
pytestmark = pytest.mark.skipif(not BINARY, reason="Set TOPOGYM_TEST_OPENCODE to run the pinned real CLI")


def reply(protocol, model, stream):
    usage = {"input_tokens":10,"output_tokens":2}
    if protocol == "chat_completions":
        usage = {"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}
        common = {"id":"chat-test","created":1,"model":model}
        if not stream:
            return {**common,"object":"chat.completion","choices":[{"index":0,
                "message":{"role":"assistant","content":"OK"},"finish_reason":"stop"}],"usage":usage}
        return [
            {**common,"object":"chat.completion.chunk","choices":[{"index":0,
             "delta":{"role":"assistant","content":"OK"},"finish_reason":None}]},
            {**common,"object":"chat.completion.chunk","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]},
            {**common,"object":"chat.completion.chunk","choices":[],"usage":usage},
        ]
    if protocol == "messages":
        message = {"id":"msg-test","type":"message","role":"assistant","model":model,
            "content":[{"type":"text","text":"OK"}],"stop_reason":"end_turn","stop_sequence":None,"usage":usage}
        if not stream:
            return message
        return [
            {"type":"message_start","message":{**message,"content":[],"stop_reason":None,
                                              "usage":{"input_tokens":10,"output_tokens":0}}},
            {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}},
            {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"OK"}},
            {"type":"content_block_stop","index":0},
            {"type":"message_delta","delta":{"stop_reason":"end_turn","stop_sequence":None},
             "usage":{"output_tokens":2}},
            {"type":"message_stop"},
        ]
    content = {"type":"output_text","text":"OK","annotations":[]}
    item = {"id":"msg-test","type":"message","role":"assistant","status":"completed","content":[content]}
    response = {"id":"resp-test","object":"response","created_at":1,"status":"completed",
        "model":model,"output":[item],"usage":{**usage,"total_tokens":12,
        "input_tokens_details":{"cached_tokens":0},"output_tokens_details":{"reasoning_tokens":0}}}
    if not stream:
        return response
    return [
        {"type":"response.created","response":{**response,"status":"in_progress","output":[]}},
        {"type":"response.output_item.added","output_index":0,"item":{**item,"status":"in_progress","content":[]}},
        {"type":"response.content_part.added","item_id":"msg-test","output_index":0,"content_index":0,
         "part":{**content,"text":""}},
        {"type":"response.output_text.delta","item_id":"msg-test","output_index":0,"content_index":0,"delta":"OK"},
        {"type":"response.output_text.done","item_id":"msg-test","output_index":0,"content_index":0,"text":"OK"},
        {"type":"response.content_part.done","item_id":"msg-test","output_index":0,"content_index":0,"part":content},
        {"type":"response.output_item.done","output_index":0,"item":item},
        {"type":"response.completed","response":response},
    ]


@contextmanager
def provider(protocol):
    seen=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path,dict(self.headers),body))
            stream=body.get("stream",False)
            payload=reply(protocol,body["model"],stream)
            if stream:
                encoded="".join(
                    ("event: "+event["type"]+"\n" if "type" in event else "")+
                    "data: "+json.dumps(event)+"\n\n" for event in payload)
                if protocol=="chat_completions": encoded+="data: [DONE]\n\n"
                data=encoded.encode()
            else:
                data=json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type","text/event-stream" if stream else "application/json")
            self.send_header("Content-Length",str(len(data)))
            self.end_headers()
            self.wfile.write(data)
    server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    thread=threading.Thread(target=server.serve_forever,kwargs={"poll_interval":.01},daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1",seen
    finally:
        server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize("model,protocol,path",[
    ("openrouter/meta/muse-spark-1.3-contributor","chat_completions","/v1/chat/completions"),
    ("anthropic/claude-sonnet-4-6","messages","/v1/messages"),
    ("openai/gpt-5","responses","/v1/responses"),
])
def test_real_cli_uses_fixed_main_and_auxiliary_model_through_gateway(tmp_path,model,protocol,path):
    connection=resolve_model(model,version="1.18.33")
    with provider(protocol) as (upstream,seen):
        pipeline=UsagePipeline(tmp_path/"usage",scope_id="cli-test",
            settings={"mode":"observed","limits":{"input_tokens":1_000_000,"output_tokens":100_000}})
        try:
            local=pipeline.start({"primary":{"url":upstream,"protocol":protocol,
                "model":connection["model_id"]}},lambda route:"fixture-upstream-key")["primary"]
            env,_=bind(connection,url=local["url"],token=local["token"])
            env.update({key:os.environ[key] for key in ("PATH","LANG","TERM") if key in os.environ})
            for key in ("DATA","CONFIG","CACHE","STATE"):
                folder=tmp_path/key.lower()
                folder.mkdir()
                env["XDG_"+key+"_HOME"]=str(folder)
            env.update(OPENCODE_DISABLE_DEFAULT_PLUGINS="true",OPENCODE_DISABLE_LSP_DOWNLOAD="true",
                       OPENCODE_DISABLE_CLAUDE_CODE="true",OPENCODE_FAKE_VCS="git")
            work=tmp_path/"work"; work.mkdir()
            version=subprocess.run([BINARY,"--version"],capture_output=True,text=True,env=env,timeout=20)
            assert version.stdout.strip()=="1.18.33",version.stderr
            result=subprocess.run([BINARY,"--model="+model,"run","--format=json",
                "--dangerously-skip-permissions","--","Reply OK without using tools."],
                cwd=work,env=env,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=60)
            (tmp_path/"cli.stdout.jsonl").write_text(result.stdout)
            (tmp_path/"cli.stderr.txt").write_text(result.stderr)
            assert result.returncode==0,result.stderr+"\n"+result.stdout[-4000:]
            assert seen,result.stderr+"\n"+result.stdout
            assert {item[0] for item in seen}=={path}
            assert all(item[2]["model"]==connection["model_id"] for item in seen)
            snapshot=pipeline.finalize()
            assert snapshot["budget_qualified"],snapshot
            assert snapshot["input_tokens"]==10*len(seen) and snapshot["output_tokens"]==2*len(seen)
        finally:
            pipeline.close()
