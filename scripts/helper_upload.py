"""Publish a sealed three-file helper delivery; retry without rerunning evaluation."""
from pathlib import Path
import tempfile
import time
from helper_assignment import atomic_json, read_json, utc
from helper_bundle import verify_bundle, exclusive, guard, BundleError
from difficulty_hf_auth import resolve_token, HFError
from difficulty_results_hf import Hub, file_identity

def upload_bundle(archive,work,args,*,hub=None,sleep=time.sleep):
    archive=Path(archive).resolve(); work=Path(work).resolve()
    with tempfile.TemporaryDirectory(prefix='helper-upload-check-') as temp:
        bundle=verify_bundle(archive,extract_to=Path(temp))
        assignment=read_json(Path(temp)/'delivery/assignment.json')
    target=assignment['upload']
    if target['type']!='hf': raise BundleError('assignment uses a shared folder; upload the three sealed files there')
    prefix=f"{target['prefix']}/{bundle['helper']}/{bundle['batch']}/{bundle['bundle_id']}"
    files=[archive,archive.with_name(archive.name+'.sha256'),archive.parent/'MANIFEST.md']
    identities={p.name:file_identity(p,guard) for p in files}
    preview=dict(repo_id=target['repo_id'],prefix=prefix,files=identities,evaluation_complete=bundle['summary']['evaluation_complete'])
    if args.hf_dry_run: return dict(preview,dry_run=True,upload_complete=False)
    state_dir=work/'helper_upload'/bundle['bundle_id']; state_dir.mkdir(parents=True,exist_ok=True)
    if hub is None:
        token,_=resolve_token(args)
        hub=Hub(token,target['repo_id'],state_dir,guard)
    receipt=dict(schema_version=1,bundle_id=bundle['bundle_id'],assignment_sha256=bundle['assignment_sha256'],**preview)
    marker=state_dir/'UPLOAD_COMPLETE.json'; atomic_json(marker,receipt)
    marker_path=prefix+'/UPLOAD_COMPLETE.json'
    with exclusive(state_dir/'.lock'):
        for attempt in range(4):
            guard()
            try:
                hub.call('auth')
                if not hub.call('private'): raise HFError('configuration','helper upload requires a private dataset')
                head=hub.call('head')
                remote=hub.call('info',paths=[prefix+'/'+p.name for p in files],revision=head)
                pending=[]
                for p in files:
                    expected=identities[p.name]; got=remote.get(prefix+'/'+p.name)
                    if got:
                        matches=(got['size']==expected['size'] and
                                 (got.get('sha256')==expected['sha256'] or (not got.get('sha256') and got.get('git_blob_sha1')==expected['git_blob_sha1'])))
                        if not matches: raise HFError('identity_conflict','remote bundle path has different bytes')
                    else: pending.append((prefix+'/'+p.name,str(p)))
                previous=hub.call('read',path=marker_path,revision=head)
                if previous and previous!=receipt: raise HFError('identity_conflict','remote receipt differs')
                if previous and pending: raise HFError('identity_conflict','completed remote delivery has missing files')
                atomic_json(state_dir/'state.json',dict(status='uploading',attempt=attempt+1,**preview))
                if pending:
                    # The SDK uses content-addressed blobs, so retrying a lost
                    # response rechecks the remote head before committing again.
                    head=hub.call('commit',parent=head,files=pending,message='Upload helper evidence '+bundle['bundle_id'])
                remote=hub.call('info',paths=[prefix+'/'+p.name for p in files],revision=head)
                for p in files:
                    got=remote.get(prefix+'/'+p.name); expected=identities[p.name]
                    if not got or got['size']!=expected['size'] or not (got.get('sha256')==expected['sha256'] or
                        (not got.get('sha256') and got.get('git_blob_sha1')==expected['git_blob_sha1'])):
                        raise HFError('remote_verification_failed')
                    if file_identity(p,guard)!=expected: raise HFError('invalid_results','sealed files changed during upload')
                if previous is None:
                    head=hub.call('commit',parent=head,files=[(marker_path,str(marker))],message='Verify helper delivery '+bundle['bundle_id'])
                if hub.call('read',path=marker_path,revision=head)!=receipt: raise HFError('remote_verification_failed')
                result=dict(receipt,upload_complete=True,commit=head,verified_at=utc())
                atomic_json(state_dir/'receipt.json',result); atomic_json(state_dir/'state.json',dict(status='complete',**result))
                return result
            except HFError as error:
                atomic_json(state_dir/'state.json',dict(status='failed',error_code=error.code,attempt=attempt+1,**preview))
                if not error.retryable or attempt==3: raise
                sleep(min(2**attempt,8))
