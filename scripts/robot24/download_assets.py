"""Trusted build-time asset fetch; source revisions and content hashes are recorded."""
import argparse, concurrent.futures, hashlib,json,subprocess,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--suite',choices=['gr1','gr1-legacy','365'],required=True);a=p.parse_args()
root=Path('.cache/robot24');downloads=root/'downloads';downloads.mkdir(parents=True,exist_ok=True)
if a.suite=='gr1':
 repo='nvidia/PhysicalAI-DigitalCousin-Assets';rev='1b018839a6da865dffecd3185fe054211bc71270'
 entries=[(n,f'https://huggingface.co/datasets/{repo}/resolve/{rev}/{n}.zip',sha,root/'robocasa-gr1/robocasa/models/assets/objects') for n,sha in [('lightwheel','8e42a0c835a205d7a0e7c33b5c33ab160b220fa9343b50c16526b7c712a2b6e2'),('sketchfab','12af71e68a5c748f8531ce20c9db0ae9ed71ab1d46265388e05155a5b5352b5d')]]
elif a.suite=='gr1-legacy':
 assets=root/'robocasa-gr1/robocasa/models/assets'
 entries=[(n,'https://utexas.box.com/shared/static/'+key+'.zip',None,assets/parent) for n,key,parent in [('textures','otdsyfjontk17jdp24bkhy2hgalofbh4',''),('fixtures','pobhbsjyacahg2mx8x4rm5fkz3wlmyzp',''),('objaverse','ejt1kc2v5vhae1rl4k5697i4xvpbjcox','objects'),('aigen_objs','os3hrui06lasnuvwqpmwn0wcrduh6jg3','objects')]]
else:
 assets=root/'robocasa365/robocasa/models/assets';links=json.loads((assets/'box_links/box_links_assets.json').read_text())
 entries=[(n,'https://utexas.box.com/shared/static/'+links[n].split('/')[-1]+'.zip',None,assets/parent) for n,parent in [('textures',''),('generative_textures',''),('fixtures_lightwheel',''),('objaverse','objects'),('aigen_objs','objects'),('objects_lightwheel','objects')]]
asset_lock=json.loads(Path(__file__).with_name('asset-lock.json').read_text())[a.suite]
expected={row['name']:row for row in asset_lock}
entries=[(name,url,expected[name]['sha256'],dest) for name,url,_,dest in entries]
def fetch(item):
 name,url,sha,dest=item;path=downloads/(a.suite+'-'+name+'.zip')
 result=dict(name=name,url=url,destination=str(dest))
 try:
  if not path.exists():subprocess.run(['curl','--fail','-L','--retry','2','--connect-timeout','30','--max-time','1800',url,'-o',str(path)+'.part'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);Path(str(path)+'.part').rename(path)
  hasher=hashlib.sha256()
  with path.open('rb') as stream:
   for chunk in iter(lambda:stream.read(1048576),b''):hasher.update(chunk)
  digest=hasher.hexdigest()
  if sha and sha!=digest:raise ValueError('asset hash mismatch')
  result.update(sha256=digest,bytes=path.stat().st_size)
  with zipfile.ZipFile(path) as z:
   for member in z.namelist():
    if not (dest/member).resolve().is_relative_to(dest.resolve()):raise ValueError('unsafe archive path')
   z.extractall(dest)
  result['success']=True
 except Exception as exc:result.update(success=False,error=repr(exc))
 print(json.dumps(result),flush=True);return result
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex: results=list(ex.map(fetch,entries))
Path('docs/validation/robot24-20260921').mkdir(parents=True,exist_ok=True)
Path('docs/validation/robot24-20260921/assets-'+a.suite+'.json').write_text(json.dumps(results,indent=2)+'\n')

if not all(row["success"] for row in results):raise SystemExit(1)
