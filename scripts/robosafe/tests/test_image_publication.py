"""Pure optional publication receipt tests; no image, registry, task or HTTP run.

All evidence is synthetic temporary JSON/raw bytes. The independent build proof
is supplied separately from the receipt under test. Tests establish validator
behavior only; they establish no actual publication or public pull availability.
Install in scripts/robosafe/tests or set ROBOSAFE_PUBLICATION_TEST_SOURCE.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

SOURCE = Path(os.environ.get('ROBOSAFE_PUBLICATION_TEST_SOURCE',Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(SOURCE))
spec = importlib.util.spec_from_file_location('rsb_publication_test_target',SOURCE/'image_publication.py')
IP = importlib.util.module_from_spec(spec);spec.loader.exec_module(IP)


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    raw = json.dumps(value,sort_keys=True,indent=2).encode()+b'\n'
    path.write_bytes(raw)
    return {'path':str(path),'sha256':hashlib.sha256(raw).hexdigest()}


def candidate():
    return {'schema':1,'source_commit':'a'*40,'image_id':'b'*64,'source_digest_sha256':'c'*64,
            'visual_assets':{'asset_profile':'realism_v3','visual_revision':'synthetic-fixture',
                             'asset_manifest_sha256':'d'*64,'physics_catalog_version':1}}


class ImagePublicationReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name);self.candidate = candidate()
        self.context_path = self.root/'source-context.json'
        self.context = save(self.context_path,{'fixture':'context raw bytes',
                                              'source_commit':self.candidate['source_commit']})
        self.proof_path = self.root/'independent-image-proof.json'
        self.proof = {**copy.deepcopy(self.candidate),'schema':'rsb.final-core-candidate-image/1',
                      'source_overlay':False,'source_mounts':[],
                      'dependency_files_equal_to_actual_base':True,
                      'source_manifest_sha256':self.context['sha256'],
                      'actual_image_inspection':{'image_id':self.candidate['image_id'],'labels':{
                          'org.opencontainers.image.revision':self.candidate['source_commit']}}}
        local = save(self.proof_path,self.proof)
        self.manifest_path = self.root/'registry-manifest.raw.json'
        self.manifest = {'schemaVersion':2,'mediaType':'application/vnd.oci.image.manifest.v1+json',
                         'config':{'mediaType':'application/vnd.oci.image.config.v1+json','size':123,
                                   'digest':'sha256:'+self.candidate['image_id']},'layers':[]}
        remote = save(self.manifest_path,self.manifest)
        digest = 'sha256:'+remote['sha256']
        self.receipt = {'schema':IP.SCHEMA,'candidate_identity':copy.deepcopy(self.candidate),
                        'local_image_proof':local,'source_context_manifest':copy.deepcopy(self.context),
                        'remote_manifest':remote,'remote_repository':IP.REPOSITORY,
                        'remote_manifest_digest':digest,'registry_readback':{'http_status':200,
                        'repository':IP.REPOSITORY,'requested_digest':digest,'response_digest':digest},
                        'verification_returncode':0}
        self.receipt_path = self.root/'publication.json'

    def load(self,receipt=None,proof_path=None):
        save(self.receipt_path,self.receipt if receipt is None else receipt)
        return IP.load(self.receipt_path,self.candidate,self.proof_path if proof_path is None else proof_path)

    def rebind_manifest(self,manifest):
        self.receipt['remote_manifest'] = save(self.manifest_path,manifest)
        digest = 'sha256:'+self.receipt['remote_manifest']['sha256']
        self.receipt['remote_manifest_digest'] = digest
        self.receipt['registry_readback'].update(requested_digest=digest,response_digest=digest)

    def test_exact_manifest_binds_public_pointer_to_same_config_without_candidate_mutation(self):
        before = copy.deepcopy(self.candidate)
        binding = self.load()
        self.assertEqual(binding['candidate_identity'],before)
        self.assertEqual(binding['local_config_digest'],'sha256:'+before['image_id'])
        self.assertEqual(IP.reference(binding,self.candidate),IP.REPOSITORY+'@'+self.receipt['remote_manifest_digest'])
        self.assertNotEqual(self.receipt['remote_manifest_digest'],'sha256:'+before['image_id'])
        self.assertEqual(self.candidate,before)

    def test_local_default_retains_config_reference_and_does_not_claim_publication(self):
        self.assertEqual(IP.reference(None,self.candidate),'sha256:'+self.candidate['image_id'])
        args = types.SimpleNamespace(publication_receipt=None,publication_image_proof=None,selection_manifest=None)
        self.assertIsNone(IP.from_args(args,{'candidate_identity':self.candidate}))

    def test_missing_raw_evidence_is_not_replaced_by_self_reported_digest_fields(self):
        for field in ('local_image_proof','source_context_manifest','remote_manifest'):
            receipt = copy.deepcopy(self.receipt);receipt.pop(field)
            with self.subTest(field=field),self.assertRaises(ValueError):self.load(receipt)
        receipt = copy.deepcopy(self.receipt)
        receipt['remote_manifest'] = {'sha256':self.receipt['remote_manifest']['sha256']}
        with self.assertRaises(ValueError):self.load(receipt)

    def test_raw_manifest_tamper_is_hold_even_when_original_summary_claims_success(self):
        raw = self.manifest_path.read_bytes();self.manifest_path.write_bytes(raw+b' ')
        with self.assertRaisesRegex(ValueError,'SHA|raw'):self.load()

    def test_rehashed_manifest_with_different_config_is_hold(self):
        manifest = copy.deepcopy(self.manifest);manifest['config']['digest']='sha256:'+'e'*64
        self.rebind_manifest(manifest)
        with self.assertRaisesRegex(ValueError,'Config|Manifest'):self.load()

    def test_missing_or_malformed_config_and_oci_index_are_hold(self):
        variants = []
        missing = copy.deepcopy(self.manifest);missing.pop('config');variants.append(missing)
        for config in (None,[],False,{}, {'digest':True}):
            variants.append({**self.manifest,'config':config})
        variants.append({'schemaVersion':2,'mediaType':'application/vnd.oci.image.index.v1+json','manifests':[]})
        variants.append({**self.manifest,'manifests':[]})
        for manifest in variants:
            self.rebind_manifest(manifest)
            with self.subTest(manifest=manifest),self.assertRaises(ValueError):self.load()

    def test_repository_or_floating_tag_cannot_replace_exact_canonical_repo_at_manifest(self):
        for repository in ('ghcr.io/other/eai-robosafe',IP.REPOSITORY+':0.5.4',IP.REPOSITORY+':latest'):
            receipt = copy.deepcopy(self.receipt);receipt['remote_repository']=repository
            with self.subTest(repository=repository),self.assertRaises(ValueError):self.load(receipt)
        receipt = copy.deepcopy(self.receipt);receipt['remote_manifest_digest']='0.5.4'
        with self.assertRaises(ValueError):self.load(receipt)

    def test_registry_readback_must_match_both_requested_and_response_manifest(self):
        for field,value in (('requested_digest','sha256:'+'e'*64),('response_digest','sha256:'+'e'*64),
                            ('repository','ghcr.io/other/eai-robosafe'),('http_status',404)):
            receipt = copy.deepcopy(self.receipt);receipt['registry_readback'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):self.load(receipt)

    def test_boolean_success_codes_or_nonzero_verification_are_hold(self):
        for value in (False,True,None,'0',1):
            receipt = copy.deepcopy(self.receipt);receipt['verification_returncode']=value
            with self.subTest(returncode=value),self.assertRaises(ValueError):self.load(receipt)
        for value in (True,False,'200',None):
            receipt = copy.deepcopy(self.receipt);receipt['registry_readback']['http_status']=value
            with self.subTest(status=value),self.assertRaises(ValueError):self.load(receipt)

    def test_nonobject_receipt_manifest_or_readback_produces_hold_not_attribute_error(self):
        for value in (None,[],True,'claimed success'):
            with self.subTest(receipt=value),self.assertRaises(ValueError):
                save(self.receipt_path,value);IP.load(self.receipt_path,self.candidate,self.proof_path)
            self.rebind_manifest(value)
            with self.subTest(manifest=value),self.assertRaises(ValueError):self.load()
        self.rebind_manifest(self.manifest)
        for value in (None,[],True):
            receipt = copy.deepcopy(self.receipt);receipt['registry_readback']=value
            with self.subTest(readback=value),self.assertRaises(ValueError):self.load(receipt)

    def test_independently_selected_image_proof_cannot_be_substituted_inside_receipt(self):
        alternative = self.root/'different-build.json';proof = copy.deepcopy(self.proof)
        proof['source_digest_sha256']='e'*64
        self.receipt['local_image_proof']=save(alternative,proof)
        with self.assertRaisesRegex(ValueError,'independently selected'):self.load()

    def test_context_raw_bytes_and_actual_build_source_identity_are_bound(self):
        self.context_path.write_bytes(b'changed context')
        self.receipt['source_context_manifest']['sha256']=hashlib.sha256(self.context_path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError,'source context'):self.load()
        # Restore the authentic context so each identity mutation below has a
        # single failing condition; a stale context mismatch must not mask it.
        self.receipt['source_context_manifest'] = save(self.context_path,{
            'fixture':'context raw bytes','source_commit':self.candidate['source_commit']})
        for field,value in (('source_commit','e'*40),('source_overlay',True),('source_mounts',['/mutable']),
                            ('dependency_files_equal_to_actual_base',False)):
            proof = copy.deepcopy(self.proof);proof[field]=value
            self.receipt['local_image_proof']=save(self.proof_path,proof)
            with self.subTest(field=field),self.assertRaises(ValueError):self.load()

    def test_actual_config_inspection_and_source_revision_cannot_be_self_relabelled(self):
        for field,value in (('image_id','e'*64),('labels',{'org.opencontainers.image.revision':'e'*40})):
            proof = copy.deepcopy(self.proof);proof['actual_image_inspection'][field]=value
            self.receipt['local_image_proof']=save(self.proof_path,proof)
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'inspection'):self.load()

    def test_public_pointer_binding_rejects_candidate_or_manifest_mutation(self):
        original = self.load()
        mutations = [('public_reference',IP.REPOSITORY+':latest'),('remote_manifest_digest','0.5.4'),
                     ('remote_repository','ghcr.io/other/eai-robosafe'),
                     ('local_config_digest','sha256:'+'e'*64)]
        for field,value in mutations:
            binding = copy.deepcopy(original)
            binding[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):IP.reference(binding,self.candidate)
        other = copy.deepcopy(self.candidate);other['image_id']='e'*64
        with self.assertRaises(ValueError):IP.reference(original,other)

    def test_opt_in_needs_independent_receipt_proof_and_explicit_selection(self):
        save(self.receipt_path,self.receipt)
        args = types.SimpleNamespace(publication_receipt=self.receipt_path,
            publication_image_proof=self.proof_path,selection_manifest=Path('synthetic-selection.json'))
        self.assertEqual(IP.from_args(args,{'candidate_identity':self.candidate})['public_reference'],
                         IP.REPOSITORY+'@'+self.receipt['remote_manifest_digest'])
        for field in ('publication_receipt','publication_image_proof','selection_manifest'):
            bad = copy.copy(args);setattr(bad,field,None)
            with self.subTest(field=field),self.assertRaises(ValueError):
                IP.from_args(bad,{'candidate_identity':self.candidate})

    def test_invalid_or_boolean_candidate_cannot_produce_even_a_local_config_pointer(self):
        for image_id in (True,None,'latest','sha256:'+'b'*64):
            bad = copy.deepcopy(self.candidate);bad['image_id']=image_id
            with self.subTest(image_id=image_id),self.assertRaises(ValueError):IP.reference(None,bad)

    def test_nonobject_independent_proof_or_inspection_is_hold(self):
        variants = [None,[],True]
        for inspection in (None,[],True):
            proof = copy.deepcopy(self.proof);proof['actual_image_inspection']=inspection
            variants.append(proof)
        for proof in variants:
            self.receipt['local_image_proof']=save(self.proof_path,proof)
            with self.subTest(proof=proof),self.assertRaises(ValueError):self.load()

    def test_generator_values_keep_config_metadata_but_choose_exact_public_manifest(self):
        spec=importlib.util.spec_from_file_location('rsb_publication_generator',SOURCE/'gen_tasks.py')
        G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)
        inst=G.CI.frozen_fields(json.loads((SOURCE/'instances/a01-i01.json').read_text()))
        orc=G.CI.frozen_fields(json.loads((SOURCE/'oracles/a01-i01.json').read_text()))
        fam=json.loads((SOURCE/'families.json').read_text())['families']['a01']
        inst.update(candidate_identity=copy.deepcopy(self.candidate),
                    robosafebench_commit=self.candidate['source_commit'],
                    robosafebench_image_id=self.candidate['image_id'])
        binding=self.load()
        for clock in ('paused','realtime'):
            inst['key']['clock']=clock
            local=G.values('a01','i01',fam,inst,orc,'0.5.4')
            public=G.values('a01','i01',fam,inst,orc,'0.5.4',binding)
            self.assertEqual(local['IMAGE'],'sha256:'+self.candidate['image_id'])
            self.assertEqual(public['IMAGE'],IP.REPOSITORY+'@'+self.receipt['remote_manifest_digest'])
            self.assertIn(self.candidate['image_id'],public['CANDIDATE_METADATA'])
            self.assertIn(self.receipt['remote_manifest_digest'],public['CANDIDATE_METADATA'])
            self.assertNotIn('image_manifest_digest',local['CANDIDATE_METADATA'])
            self.assertEqual({k:v for k,v in local.items() if k not in ('IMAGE','CANDIDATE_METADATA')},
                             {k:v for k,v in public.items() if k not in ('IMAGE','CANDIDATE_METADATA')})

    def test_public_binding_explicitly_requires_new_task_digests_and_keeps_validation_pending(self):
        binding = self.load()
        self.assertIs(binding['requires_new_task_digests'],True)
        self.assertIs(binding['task_validation_inherited'],False)
        self.assertEqual(binding['public_task_validation'],'pending independent validation')
        # Use the repository's real content-hash algorithm on synthetic bytes.
        # This never renders or executes a real selected task.
        spec = importlib.util.spec_from_file_location('rsb_publication_digest',SOURCE.parent/'task_conventions.py')
        TC = importlib.util.module_from_spec(spec);spec.loader.exec_module(TC)
        mock = self.root/'synthetic-content-hash-fixture';(mock/'environment').mkdir(parents=True)
        compose = mock/'environment/docker-compose.yaml'
        compose.write_text('services:\n  sim:\n    image: '+IP.reference(None,self.candidate)+'\n')
        old_digest = TC.digest(mock)
        old_http_proof = {'task_digest':old_digest,'status':'synthetic historical pass'}
        compose.write_text('services:\n  sim:\n    image: '+IP.reference(binding,self.candidate)+'\n')
        public_digest = TC.digest(mock)
        self.assertNotEqual(public_digest,old_digest)
        self.assertNotEqual(public_digest,old_http_proof['task_digest'])
        self.assertIs(binding['task_validation_inherited'],False)


if __name__=='__main__':unittest.main()
