"""Opt-in immutable public image transport; never publishes or grants admission.

The registry manifest is a different identity from its Config digest. A public
export is a new task freeze whose HTTP/Harbor checks remain pending.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import candidate_identity as CI

REPOSITORY = 'ghcr.io/mll-lab-nu/eai-robosafe'
SCHEMA = 'rsb.image-publication-receipt/1'
DIGEST = re.compile(r'sha256:[0-9a-f]{64}\Z')
MEDIA_TYPES = {'application/vnd.oci.image.manifest.v1+json',
               'application/vnd.docker.distribution.manifest.v2+json'}


def _valid_candidate(value):
    try:return CI.valid(value)
    except (TypeError,ValueError):return False


def _read(ref, base):
    if not isinstance(ref,dict) or set(ref)!={'path','sha256'} or not isinstance(ref['path'],str):
        raise ValueError('Publication input requires an exact path and raw SHA256')
    path=Path(ref['path']);path=path if path.is_absolute() else base/path
    raw=path.read_bytes()
    if not isinstance(ref['sha256'],str) or hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('Publication input raw SHA256 mismatch')
    return raw


def load(path, candidate, image_proof_path):
    """Read a trusted producer receipt against an independently supplied build proof."""
    if not _valid_candidate(candidate) or image_proof_path is None:
        raise ValueError('Publication requires actual candidate identity and independent image build proof')
    path=Path(path);raw=path.read_bytes();receipt=json.loads(raw);base=path.parent
    if not isinstance(receipt,dict) or receipt.get('schema')!=SCHEMA or receipt.get('candidate_identity')!=candidate:
        raise ValueError('Publication receipt belongs to another candidate')
    proof_raw=Path(image_proof_path).read_bytes()
    if _read(receipt.get('local_image_proof'),base)!=proof_raw:
        raise ValueError('Publication local image proof differs from the independently selected proof')
    proof=json.loads(proof_raw)
    if (not isinstance(proof,dict) or proof.get('schema')!='rsb.final-core-candidate-image/1' or
            any(proof.get(k)!=candidate[k] for k in ('source_commit','source_digest_sha256','image_id','visual_assets')) or
            proof.get('source_overlay') is not False or proof.get('source_mounts')!=[] or
            proof.get('dependency_files_equal_to_actual_base') is not True):
        raise ValueError('Publication requires the same installed source, visual assets and Config identity')
    actual=proof.get('actual_image_inspection',{})
    if (not isinstance(actual,dict) or not isinstance(actual.get('labels'),dict) or actual.get('image_id')!=candidate['image_id'] or
            actual.get('labels',{}).get('org.opencontainers.image.revision')!=candidate['source_commit']):
        raise ValueError('Build inspection does not bind source revision to the Config identity')
    context=_read(receipt.get('source_context_manifest'),base)
    if hashlib.sha256(context).hexdigest()!=proof.get('source_manifest_sha256'):
        raise ValueError('Publication source context differs from the actual image build inputs')
    manifest_raw=_read(receipt.get('remote_manifest'),base);manifest=json.loads(manifest_raw)
    digest='sha256:'+hashlib.sha256(manifest_raw).hexdigest()
    if not isinstance(manifest,dict) or not isinstance(manifest.get('config'),dict):
        raise ValueError('Registry response must be a single image Manifest with Config descriptor')
    if (receipt.get('remote_repository')!=REPOSITORY or receipt.get('remote_manifest_digest')!=digest or
            manifest.get('schemaVersion')!=2 or type(manifest.get('schemaVersion')) is not int or
            manifest.get('mediaType') not in MEDIA_TYPES or 'manifests' in manifest or
            manifest.get('config',{}).get('digest')!='sha256:'+candidate['image_id']):
        raise ValueError('Remote image Manifest must bind the canonical repository to this exact Config')
    readback=receipt.get('registry_readback',{})
    if (not isinstance(readback,dict) or type(readback.get('http_status')) is not int or readback['http_status']!=200 or
            readback.get('repository')!=REPOSITORY or readback.get('requested_digest')!=digest or
            readback.get('response_digest')!=digest or
            type(receipt.get('verification_returncode')) is not int or receipt['verification_returncode']!=0):
        raise ValueError('Exact successful registry Manifest readback is required')
    return {'schema':'rsb.public-image-transport-binding/1','candidate_identity':candidate,
        'local_config_digest':'sha256:'+candidate['image_id'],
        'remote_repository':REPOSITORY,'remote_manifest_digest':digest,
        'public_reference':REPOSITORY+'@'+digest,'publication_receipt_sha256':hashlib.sha256(raw).hexdigest(),
        'local_image_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
        'source_context_manifest_sha256':hashlib.sha256(context).hexdigest(),
        'requires_new_task_digests':True,'task_validation_inherited':False,
        'public_task_validation':'pending independent validation'}


def reference(binding, candidate):
    if not _valid_candidate(candidate):raise ValueError('Actual candidate identity is required')
    if binding is None:
        return 'sha256:'+candidate['image_id']
    if (not isinstance(binding,dict) or binding.get('schema')!='rsb.public-image-transport-binding/1' or
            binding.get('candidate_identity')!=candidate or binding.get('remote_repository')!=REPOSITORY or
            not DIGEST.fullmatch(binding.get('remote_manifest_digest') or '') or
            binding.get('public_reference')!=REPOSITORY+'@'+binding['remote_manifest_digest'] or
            binding.get('local_config_digest')!='sha256:'+candidate['image_id']):
        raise ValueError('Public transport binding differs from the task candidate')
    return binding['public_reference']


def from_args(args, registry):
    path=getattr(args,'publication_receipt',None);proof=getattr(args,'publication_image_proof',None)
    if path is None and proof is None:return None
    if path is None or proof is None or getattr(args,'selection_manifest',None) is None:
        raise ValueError('Publication export requires receipt, independent image proof and explicit selection')
    return load(path,registry.get('candidate_identity'),proof)
