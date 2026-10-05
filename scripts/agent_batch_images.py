"""Install maintainer-pinned images behind the unchanged batch entrypoint."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import urllib.parse

from agent_batch_contract import locked, sha
from agent_batch_bootstrap import run, download


def references(plan):
    refs={}
    for task in plan['tasks']:
        for key in ('image','agent_image'):
            if key in task['runtime_binding']:
                image=task['runtime_binding'][key]
                old=refs.setdefault(image['reference'],image['id'])
                if old!=image['id']: raise ValueError('conflicting task image IDs')
    for image in plan.get('images',{}).values():
        old=refs.setdefault(image['image'],image['id'])
        if old!=image['id']: raise ValueError('conflicting role image IDs')
    return refs


def validate_sources(sources,refs):
    if not isinstance(sources,dict) or set(sources)-set(refs): raise ValueError('image source does not match a required image')
    for source in sources.values():
        if not isinstance(source,dict): raise ValueError('invalid image source')
        if set(source)=={'pull'}:
            if not isinstance(source['pull'],str) or not re.fullmatch(r'[a-z0-9][a-z0-9._:/-]*@sha256:[a-f0-9]{64}',source['pull']):
                raise ValueError('image pull source must be an immutable registry digest')
        elif set(source)=={'build'}:
            from agent_batch_image_build import validate_spec
            validate_spec(source['build'])
        elif set(source)=={'url','sha256','bytes'}:
            url=urllib.parse.urlsplit(source['url'])
            if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
                raise ValueError('image archive needs a public HTTPS URL without credentials')
            if not re.fullmatch('[a-f0-9]{64}',source['sha256']) or type(source['bytes']) is not int or source['bytes']<=0:
                raise ValueError('image archive needs its SHA-256 and exact byte count')
        else: raise ValueError('image source needs build, pull, or url/sha256/bytes')
    return sources


def inspect(ref):
    result=subprocess.run(['docker','image','inspect',ref],capture_output=True,text=True,timeout=30)
    return json.loads(result.stdout)[0] if result.returncode==0 else None


_verified_builds={}


def verify_build(plan,ref,actual,root):
    """Authorize an image-ID change only under an explicit maintainer build policy."""
    from agent_batch_image_build import materials, inspect_contents, assert_contents
    spec=plan['image_sources'][ref]['build']
    manifest,context=materials(root,spec)
    wanted=references(plan)[ref]
    if manifest['reference_image']!={'reference':ref,'id':wanted}:
        raise ValueError('build materials belong to a different reference image')
    for task in plan['tasks']:
        if task['runtime_binding']['image']['reference']==ref:
            if task['runtime_binding']['runtime']!=spec['expected']['runtime']:
                raise ValueError('build policy differs from prepared task runtime')
    if actual.get('Architecture')!='amd64' or actual.get('Os')!='linux':
        raise ValueError('rebuilt image platform differs from prepared runtime')
    key=(actual['Id'],spec['sha256'])
    if key not in _verified_builds:
        observed=inspect_contents(actual['Id'],context/'probe')
        assert_contents(observed,spec['expected'])
        _verified_builds[key]=observed
    return dict(method='frozen-materials',reference_id=wanted,manifest_sha256=spec['sha256'],
                observed=_verified_builds[key])


def verified_records(plan,root):
    refs=references(plan); sources=validate_sources(plan.get('image_sources',{}),refs)
    records={}
    for ref,wanted in refs.items():
        actual=inspect(ref)
        if actual is None: raise ValueError('required image is absent: '+ref)
        source=sources.get(ref,{})
        proof=verify_build(plan,ref,actual,root) if 'build' in source else None
        if proof is None and actual['Id']!=wanted:
            raise ValueError('image differs from frozen runtime binding')
        record={k:actual.get(k) for k in ('Id','RepoDigests','Architecture','Os')}
        if proof is not None: record['build_verification']=proof
        records[ref]=record
    return records


def verify_received_records(plan,records):
    """Offline receiver checks the recorded contents against its original assignment."""
    for ref,source in plan.get('image_sources',{}).items():
        if 'build' not in source: continue
        spec=source['build']; record=records.get(ref,{})
        wanted=dict(method='frozen-materials',reference_id=references(plan)[ref],
                    manifest_sha256=spec['sha256'],observed=spec['expected'])
        if (record.get('build_verification')!=wanted or record.get('Architecture')!='amd64'
                or record.get('Os')!='linux' or not re.fullmatch('sha256:[a-f0-9]{64}',record.get('Id',''))):
            raise ValueError('missing or mismatched helper image build verification')


def ensure_images(plan,root):
    refs=references(plan); sources=validate_sources(plan.get('image_sources',{}),refs)
    cache=Path(root)/'.tools/agent-batch/images'; cache.mkdir(parents=True,exist_ok=True)
    with locked(cache/'install.lock'):
        for ref,want in refs.items():
            actual=inspect(ref)
            source=sources.get(ref)
            if source is not None and 'build' in source:
                from agent_batch_image_build import build, materials
                # Check the frozen inputs even when a matching image is already present.
                materials(root,source['build'])
                if actual is None:
                    build(root,source['build'],ref)
                    actual=inspect(ref)
                if actual is None: raise ValueError('build did not install required image')
                verify_build(plan,ref,actual,root)
                continue
            if actual:
                if actual['Id']!=want: raise ValueError('installed image differs from assignment: '+ref)
                continue
            if source is None:
                if ref.startswith('topogym-local/'):
                    raise ValueError('maintainer has not supplied a distributable source for missing image: '+ref)
                source={'pull':ref}
            print('Fetching frozen image: '+ref,flush=True)
            if 'pull' in source:
                run(['docker','pull',source['pull']])
                pulled=inspect(source['pull'])
                if not pulled or pulled['Id']!=want: raise ValueError('downloaded image ID differs from assignment')
                if source['pull']!=ref: run(['docker','tag',source['pull'],ref])
            else:
                archive=cache/(source['sha256']+'.tar.gz')
                if not archive.exists():
                    if shutil.disk_usage(cache).free<source['bytes']+64*1024**2: raise ValueError('insufficient disk for image archive')
                    with tempfile.TemporaryDirectory(prefix='.download-',dir=cache) as td:
                        part=Path(td)/'image.tar.gz'
                        download(source['url'],part)
                        if part.stat().st_size!=source['bytes'] or sha(part)!=source['sha256']:
                            raise ValueError('downloaded image archive checksum/size mismatch')
                        part.rename(archive)
                if archive.is_symlink() or archive.stat().st_size!=source['bytes'] or sha(archive)!=source['sha256']:
                    raise ValueError('cached image archive differs from assignment')
                run(['docker','load','--input',archive])
            actual=inspect(ref)
            if not actual or actual['Id']!=want: raise ValueError('frozen image was not installed correctly: '+ref)
