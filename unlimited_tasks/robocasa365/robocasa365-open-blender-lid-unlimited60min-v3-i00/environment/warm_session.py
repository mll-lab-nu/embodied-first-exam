"""Preinitialized unlimited Session, in main (not a security boundary).

Trusted setup constructs the initial native simulator before the agent deadline.
Agent-created additional Sessions and explicit resets remain inside its budget.
RPC transports the existing public Session methods and numpy observations without
changing controls, initial state or success predicates. No oracle is loaded.
"""
import importlib,os,pickle,socket,struct,sys,threading,time
from pathlib import Path
SOCKET='/tmp/rcb-unlimited-session.sock'
ATTRS={'lower','upper','dt','substeps','sim_steps','actions','controls','instance_sha','counters','initial_hash','model_sha','done','ever_success','total_steps','resets'}
PUBLIC={'observe','state','status','result','render','frame','step','reset','move','solve_ik','ik','skill','record_start','record_stop','save','save_trajectory','load_trajectory','replay','close','budget'}
def readn(sock,n):
 data=b''
 while len(data)<n:
  chunk=sock.recv(n-len(data))
  if not chunk:raise EOFError()
  data+=chunk
 return data
def recv(sock):
 size=struct.unpack('!Q',readn(sock,8))[0]
 if size>2**30:raise ValueError('oversized RPC allocation')
 return pickle.loads(readn(sock,size))
def send(sock,value):
 data=pickle.dumps(value,protocol=5);sock.sendall(struct.pack('!Q',len(data))+data)
class RemoteSession:
 def __init__(self,*args,**kwargs):
  self.connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.connection.connect(SOCKET)
  self._request(('new',args,kwargs))
 def _request(self,value):
  send(self.connection,value);ok,result=recv(self.connection)
  if not ok:
   if result.startswith('AttributeError:'):raise AttributeError(result)
   raise RuntimeError(result)
  return result
 def __getattr__(self,name):
  if name in ATTRS:return self._request(('get', (name,), {}))
  if name not in PUBLIC:raise AttributeError(name+' is not part of the public Session API; use state()/observe().')
  return lambda *args,**kwargs:self._request((name,args,kwargs))
 def close(self):
  try:self._request(('close',(),{}))
  finally:self.connection.close()
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
def install(module):
 # NativeSession retains advanced native introspection in this privileged mode.
 # Trusted /solution programs are baseline-only and retain their original API.
 module.NativeSession=module.Session
 if os.environ.get('RCB_WARM_CLIENT')!='1' or sys.argv[0].startswith('/solution/'):return
 import types
 native_globals=dict(module.__dict__)
 if hasattr(module,'replay'):
  f=module.replay
  module.replay=types.FunctionType(f.__code__,native_globals,f.__name__,f.__defaults__,f.__closure__)
 original=getattr(module,'load_trajectory',None)
 if original:
  def load_trajectory(path,session):
   if isinstance(session,RemoteSession):return session._request(('__load_trajectory',(str(path),),{}))
   return original(path,session)
  module.load_trajectory=load_trajectory
 module.Session=RemoteSession

def serve(module_name):
 os.environ.pop('RCB_WARM_CLIENT',None)
 module=importlib.import_module(module_name);Session=module.Session
 import inspect
 warm=Session(render=True) if 'render' in inspect.signature(Session).parameters else Session()
 lock=threading.Lock();available=[warm]
 def handle(connection):
  session=None
  try:
   name,args,kwargs=recv(connection)
   if name!='new':raise ValueError('new Session required')
   with lock:
    if not args and (not kwargs or kwargs=={'render':True}) and available:session=available.pop()
   if session is None:session=Session(*args,**kwargs)
   send(connection,(True,None))
   while True:
    name,args,kwargs=recv(connection)
    try:
     if name=='__load_trajectory':
      send(connection,(True,module.load_trajectory(args[0],session)));continue
     if name=='get' and len(args)==1 and args[0] in ATTRS:
      send(connection,(True,getattr(session,args[0])));continue
     if name not in PUBLIC:raise ValueError('unknown Session method')
     value=getattr(session,name)(*args,**kwargs)
     send(connection,(True,value))
     if name=='close':session=None;break
    except Exception as exc:send(connection,(False,type(exc).__name__+': '+str(exc)))
  except (EOFError,BrokenPipeError,ConnectionResetError):pass
  finally:
   if session is not None:
    try:session.close()
    except Exception:pass
   connection.close()
 sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.bind(SOCKET);sock.listen()
 Path('/tmp/rcb-unlimited-ready').write_text('ready\n')
 while True:
  client,_=sock.accept();threading.Thread(target=handle,args=(client,),daemon=True).start()
if __name__=='__main__':serve(sys.argv[1])
