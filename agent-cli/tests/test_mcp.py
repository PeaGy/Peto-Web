import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from conftest import FakeUI
from peto_agent.mcp import Connection, MCP, validate
from peto_agent.workspace import Workspace, WorkspaceError
from test_loop_client import peto, message
from peto_agent.client import Client
from peto_agent.loop import Session


SERVER = '''import json,sys,os
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m: continue
 method=m['method']
 if method=='initialize': r={'protocolVersion':'2025-11-25','capabilities':{'tools':{}}}
 elif method=='tools/list': r={'tools':[{'name':'echo','description':'Echo input','inputSchema':{'type':'object','properties':{'text':{'type':'string'}}}}]}
 else: r={'content':[{'type':'text','text':m['params']['arguments']['text']}],'isError':False}
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)
'''


def setup(project, ui):
    server = project / 'server.py'
    server.write_text(SERVER, encoding='utf-8')
    spec = {'command': sys.executable, 'args': ['-u', str(server)]}
    (project / 'server.json').write_text(json.dumps(spec), encoding='utf-8')
    manager = MCP(Workspace(project), ui)
    manager.command('add demo server.json')
    return manager


def test_stdio_lifecycle_and_permissions(project):
    ui = FakeUI(answers=['n', 'y', 'n', 'y'])
    manager = setup(project, ui)
    assert manager.catalog() == []
    manager.command('enable demo')
    assert manager.catalog() == []
    manager.command('enable demo')
    conn = manager.connections['demo']
    assert manager.list_tools('demo')['tools'][0]['name'] == 'echo'
    assert 'error' in manager.call('demo', 'echo', '{"text":"test"}')
    assert manager.call('demo', 'echo', '{"text":"test"}')['content'][0]['text'] == 'test'
    manager.close()
    assert conn.process.poll() is not None
    assert manager.catalog() == []
    with pytest.raises(WorkspaceError):
        manager.call('demo', 'echo', '{}')


def test_timeout_stops_process(project):
    path = project / 'sleep.py'
    path.write_text('import time; time.sleep(20)')
    conn = Connection({'command': sys.executable, 'args': [str(path)]}, project, timeout=.2)
    with pytest.raises(WorkspaceError):
        conn.open()
    assert conn.process.poll() is not None


def test_model_discovers_and_calls_mcp(project, peto):
    ui = FakeUI(answers=['y', 'y'])
    manager = setup(project, ui)
    manager.command('enable demo')
    work = Session(Client(peto.url, 'test'), Workspace(project), ui)
    work.tools.mcp = manager
    # Tools binds handlers at construction; use the same connected instance.
    work.tools._handlers['mcp_list_tools'] = manager.list_tools
    work.tools._handlers['mcp_call_tool'] = manager.call
    def reply(path, body):
        assert body['context']['mcp_servers'] == [{'name':'demo', 'tools':1}]
        results = [json.loads(x['output']) for x in body['input'] if x.get('type')=='function_call_output']
        if not results:
            name, args = 'mcp_list_tools', {'server':'demo'}
        elif len(results) == 1:
            assert results[0]['tools'][0]['inputSchema']['type'] == 'object'
            name, args = 'mcp_call_tool', {'server':'demo','tool':'echo','arguments_json':'{"text":"MCP_OK"}'}
        else:
            assert results[1]['content'][0]['text'] == 'MCP_OK'
            return 200, [{'type':'done','output':[message('Done')],'usage':{}}]
        return 200, [{'type':'done','output':[{'type':'function_call','name':name,'call_id':str(len(results)),
            'arguments':json.dumps(args)}], 'usage':{}}]
    peto.reply = reply
    try:
        work.run_task('Use demo to echo MCP_OK')
        assert len(peto.requests) == 3
    finally:
        manager.close()


def test_env_only_explicit_keys_are_passed(project, monkeypatch):
    monkeypatch.setenv('TOP_SECRET_TEST', 'do-not-inherit')
    monkeypatch.setenv('EXPLICIT_TEST', 'mapped-value')
    path = project / 'env.py'
    path.write_text(SERVER.replace("m['params']['arguments']['text']", "str(os.environ.get('TOP_SECRET_TEST')) + ':' + os.environ['MAPPED']"))
    conn = Connection({'command':sys.executable, 'args':['-u',str(path)], 'env':{'MAPPED':'${EXPLICIT_TEST}'}},project)
    try:
        conn.open()
        result = conn.request('tools/call', {'name':'echo','arguments':{'text':'x'}})
        assert result['content'][0]['text'] == 'None:mapped-value'
    finally:
        conn.close()


@pytest.mark.parametrize('spec', [
    {'url':'http://example.com/mcp'}, {'url':'https://example.com/mcp?key=secret'},
    {'url':'https://example.com', 'headers':{'Authorization':'Bearer secret'}},
    {'command':'python','args':'script.py'}, {'command':'python','url':'https://example.com'},
    {'command':'python','env':{'BAD\nNAME':'x'}},
])
def test_invalid_config(spec):
    with pytest.raises(WorkspaceError):
        validate(spec)


@pytest.mark.parametrize('sse', [False, True])
def test_http_session_and_tools(project, sse):
    seen = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            m = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(m['method'])
            if m['method'] != 'initialize':
                assert self.headers['Mcp-Session-Id'] == 'test-session'
                assert self.headers['MCP-Protocol-Version'] == '2025-11-25'
            if 'id' not in m:
                self.send_response(202)
                self.end_headers()
                return
            result = {'protocolVersion':'2025-11-25','capabilities':{'tools':{}}} if m['method']=='initialize' else {'tools':[]}
            body = json.dumps({'jsonrpc':'2.0','id':m['id'],'result':result})
            if sse:
                body = 'event: message\ndata: ' + body + '\n\n'
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream' if sse else 'application/json')
            self.send_header('Mcp-Session-Id','test-session')
            self.end_headers()
            self.wfile.write(body.encode())
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        conn = Connection({'url':f'http://127.0.0.1:{server.server_port}/mcp'}, project)
        conn.open()
        conn.close()
        assert seen == ['initialize','notifications/initialized','tools/list']
    finally:
        server.shutdown()
        server.server_close()
