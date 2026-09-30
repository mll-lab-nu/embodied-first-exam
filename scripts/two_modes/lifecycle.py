"""Trusted host-only lifecycle. No secrets or oracle data enter public observations."""
import asyncio,json,time,ipaddress
from pathlib import Path
from harbor.environments.docker.docker import _sanitize_docker_compose_project_name
async def command(*args,input=None,timeout=1800,check=True):
 p=await asyncio.create_subprocess_exec(*map(str,args),stdin=asyncio.subprocess.PIPE if input is not None else None,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
 try:out,err=await asyncio.wait_for(p.communicate(input.encode() if isinstance(input,str) else input),timeout)
 except asyncio.TimeoutError:p.kill();await p.wait();raise
 if check and p.returncode:raise RuntimeError(err.decode(errors='replace')[-2000:])
 return out.decode(errors='replace')
async def containers(event,limited):
 project=_sanitize_docker_compose_project_name(event.trial_name+'__env');out={}
 for service in ['main','codex-egress','harbor-docker-egress-control-sidecar']+(['sim'] if limited else []):
  ids=(await command('docker','ps','-aq','--filter','label=com.docker.compose.project='+project,'--filter','label=com.docker.compose.service='+service)).split()
  if len(ids)!=1:raise RuntimeError('Missing container '+service)
  out[service]=ids[0]
 return out
async def isolate(ids,limited):
 main=json.loads(await command('docker','inspect',ids['main']))[0];host=main['HostConfig']
 assert not host['Privileged'] and not host['CapAdd'] and 'ALL' in host['CapDrop']
 assert not host['PidMode'] and host.get('IpcMode')!='host'
 assert any(x.startswith('no-new-privileges') for x in host['SecurityOpt'])
 guard=json.loads(await command('docker','inspect',ids['harbor-docker-egress-control-sidecar']))[0]
 assert host['NetworkMode']=='container:'+guard['Id'] and not main['NetworkSettings']['Networks']
 networks=guard['NetworkSettings']['Networks']
 for name in networks:assert json.loads(await command('docker','network','inspect',name))[0]['Internal']
 if limited:
  assert not any(any(x in m['Destination'] for x in ('/private','/recorded','/run/limited','docker.sock','/tests','/solution')) for m in main['Mounts'])
 addresses={}
 for service in ['codex-egress']+(['sim'] if limited else []):
  d=json.loads(await command('docker','inspect',ids[service]))[0]
  addresses[service]=next(v['IPAddress'] for n,v in d['NetworkSettings']['Networks'].items() if n in networks)
  ipaddress.ip_address(addresses[service])
 await command('docker','exec','-i',ids['main'],'sh','-c','cat >> /etc/hosts',input=''.join(ip+' '+name+'\n' for name,ip in addresses.items()))
 rules='table inet rcb_limited { chain output { type filter hook output priority -110; policy drop; oifname "lo" ip daddr 127.0.0.1 accept; oifname "lo" ip6 daddr ::1 accept; '
 rules+=' '.join('ip daddr '+ip+' tcp dport '+('8000' if name=='sim' else '3128')+' accept;' for name,ip in addresses.items())+'\n}\n}\n'
 await command('docker','exec','-i',ids['harbor-docker-egress-control-sidecar'],'nft','-f','-',input=rules)
 await command('docker','exec',ids['harbor-docker-egress-control-sidecar'],'network-policy','allow-all')
 gateways=[]
 for n in networks:
  d=json.loads(await command('docker','network','inspect',n))[0]
  gateways += [x['Gateway'] for x in d['IPAM']['Config'] if x.get('Gateway')]
 probe='import socket,json\naddresses='+repr([(g,p) for g in gateways for p in (22,9173,2375,2376)]+[('1.1.1.1',443),('8.8.8.8',443)])+'''
for host,port in addresses:
 with socket.socket() as sock:
  sock.settimeout(.3)
  assert sock.connect_ex((host,port))!=0,(host,port)
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
 sock.settimeout(.3)
 try:
  sock.sendto(b'\\x01\\x23\\x01\\x00\\x00\\x01\\x00\\x00\\x00\\x00\\x00\\x00\\x07example\\x03com\\x00\\x00\\x01\\x00\\x01',('127.0.0.11',53))
  sock.recv(512)
  raise AssertionError('Docker DNS bypass')
 except OSError:pass
for target in ('example.com:443','openrouter.ai:443','api.openai.com:443','sim:8000','chatgpt.com:80'):
 with socket.create_connection(('codex-egress',3128),timeout=10) as sock:
  sock.sendall(('CONNECT '+target+' HTTP/1.1\\r\\nHost: '+target+'\\r\\n\\r\\n').encode())
  assert b'403' in sock.recv(256),target
print(json.dumps({'gateway_blocked':True,'public_egress_blocked':True,'dns_blocked':True,'unlisted_proxy_blocked':True}))
'''
 result=json.loads(await command('docker','exec','-i',ids['main'],'python','-',input=probe))
 result['capabilities_dropped']=True;result['namespace_isolation']=True
 return result

async def public_probe(ids):
 return json.loads(await command('docker','exec','-i',ids['main'],'python','-',input=Path(__file__).with_name('public_probe.py').read_text()))
