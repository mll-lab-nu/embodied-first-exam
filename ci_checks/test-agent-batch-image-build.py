"""CPU contracts for frozen helper builds; Docker/model operations are mocked."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT)]
import agent_batch_contract as c
import agent_batch_images as images
import agent_batch_image_build as builds
import agent_batch_delivery as delivery

loader=importlib.util.spec_from_file_location('native_fixture',ROOT/'ci_checks/test-native-agent-batch.py')
fixture=importlib.util.module_from_spec(loader); loader.loader.exec_module(fixture)


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.jobs,self.plan=fixture.fixture(self.root)
        self.ref='fixture:image'; self.wanted='sha256:'+'f'*64
        self.actual=dict(Id='sha256:'+'b'*64,Architecture='amd64',Os='linux',RepoDigests=[])
        self.expected=dict(schema_version=1,runtime={'source':{'sha256':'a'*64}},
                           packages={'fixture':{'version':'1','sha256':'b'*64,'files':1}},
                           dpkg=['installed fixture:amd64 1'],robots={},visuals={})
        self.path=self.root/'images/helper-build/fixture/manifest.json'
        self.context=self.path.parent/'context'; self.context.mkdir(parents=True)
        (self.context/'Dockerfile').write_text('FROM fixture@sha256:'+'a'*64+'\n')
        c.save(self.path,dict(schema_version=1,platform='linux/amd64',expected=self.expected,
                              reference_image={'reference':self.ref,'id':self.wanted},files=c.inventory(self.context)))
        self.spec=dict(manifest=str(self.path.relative_to(self.root)),sha256=c.sha(self.path),expected=self.expected)
        self.plan['image_sources']={self.ref:{'build':self.spec}}
        for task in self.plan['tasks']: task['runtime_binding']['runtime']=self.expected['runtime']
        self.repin()
        images._verified_builds.clear()

    def tearDown(self): self.temp.cleanup()

    def repin(self):
        self.plan.pop('plan_sha256',None); self.plan['plan_sha256']=c.digest(self.plan)
        c.validate(self.plan); c.save(self.jobs/'fixture-plan.json',self.plan)
        metadata=c.read(self.jobs/'fixture-metadata.json'); metadata['plan_sha256']=self.plan['plan_sha256']
        c.save(self.jobs/'fixture-metadata.json',metadata)

    def test_new_id_requires_exact_contents_and_is_recorded(self):
        with patch.object(images,'inspect',return_value=self.actual),patch.object(builds,'inspect_contents',return_value=self.expected) as probe:
            records=images.verified_records(self.plan,self.root)
            self.assertEqual(records[self.ref]['Id'],self.actual['Id'])
            self.assertEqual(records[self.ref]['build_verification']['reference_id'],self.wanted)
            images.verified_records(self.plan,self.root); self.assertEqual(probe.call_count,1)
        images.verify_received_records(self.plan,records)
        records[self.ref]['build_verification']['observed']=dict(self.expected,dpkg=['changed'])
        with self.assertRaisesRegex(ValueError,'verification'): images.verify_received_records(self.plan,records)

    def test_without_policy_new_image_id_remains_blocked(self):
        self.plan.pop('image_sources')
        with patch.object(images,'inspect',return_value=self.actual):
            with self.assertRaisesRegex(ValueError,'image differs'): images.verified_records(self.plan,self.root)

    def test_runtime_or_assets_drift_is_rejected_before_tagging(self):
        for key in ('runtime','packages','dpkg','robots','visuals'):
            with self.subTest(key=key),patch.object(builds,'run',return_value=json.dumps([self.actual])) as run, \
                 patch.object(builds,'inspect_contents',return_value=dict(self.expected,**{key:'changed'})):
                with self.assertRaisesRegex(ValueError,'contents differ'): builds.build(self.root,self.spec,self.ref)
                self.assertFalse(any(call.args[0][1]=='tag' for call in run.call_args_list))

    def test_changed_inputs_even_with_existing_image_are_blocked(self):
        (self.context/'Dockerfile').write_text('different source')
        with patch.object(images,'inspect',return_value=self.actual),patch.object(builds,'build') as build:
            with self.assertRaisesRegex(ValueError,'materials changed'): images.ensure_images(self.plan,self.root)
            build.assert_not_called()

    def test_missing_image_builds_once_then_reuses_verified_image(self):
        installed={}
        def build(*args): installed[self.ref]=self.actual
        with patch.object(images,'inspect',side_effect=lambda ref:installed.get(ref)), \
             patch.object(builds,'build',side_effect=build) as build, \
             patch.object(builds,'inspect_contents',return_value=self.expected):
            images.ensure_images(self.plan,self.root); images.ensure_images(self.plan,self.root)
            self.assertEqual(build.call_count,1)

    def test_build_policy_cannot_change_prepared_runtime(self):
        self.plan['tasks'][0]['runtime_binding']['runtime']={'changed':'runtime'}
        with patch.object(images,'inspect',return_value=self.actual),patch.object(builds,'inspect_contents') as probe:
            with self.assertRaisesRegex(ValueError,'prepared task runtime'): images.verified_records(self.plan,self.root)
            probe.assert_not_called()

    def test_material_path_and_links_cannot_escape_checkout(self):
        with self.assertRaisesRegex(ValueError,'relative'): builds.validate_spec(dict(self.spec,manifest='../outside.json'))
        (self.context/'link').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError,'links'): builds.materials(self.root,self.spec)

    def test_installer_timestamp_exception_does_not_exclude_package_resources(self):
        from agent_batch_image_probe import installation_metadata
        self.assertTrue(installation_metadata(Path('pyuipc-1.dist-info/uv_cache.json')))
        self.assertFalse(installation_metadata(Path('pyuipc/uv_cache.json')))
        self.assertFalse(installation_metadata(Path('pyuipc/backend.so')))

    def test_reference_genesis_patch_is_included_with_both_hash_checks(self):
        block = builds.runtime_patch_recipe(ROOT, self.context)
        source = (ROOT/'images/topogym/Dockerfile').read_text()
        name = 'genesis-1.2.1-cpu-tree.patch'
        self.assertEqual((self.context/name).read_bytes(), (ROOT/'images/topogym'/name).read_bytes())
        self.assertIn(block.replace('COPY '+name, 'COPY images/topogym/'+name), source)
        self.assertEqual(block.count('sha256sum -c -'), 2)
        recipe = (ROOT/'images/helper-build/Dockerfile.template').read_text().replace('@RUNTIME_PATCHES@', block)
        self.assertLess(recipe.index('prepare_nyx_studio.py\nRUN'), recipe.index('patch -p1'))
        self.assertLess(recipe.index('patch -p1'), recipe.index('COPY topogym/'))

    def test_old_source_without_patch_remains_supported_and_missing_patch_fails(self):
        source = self.root/'source'; folder = source/'images/topogym'; folder.mkdir(parents=True)
        (folder/'Dockerfile').write_text('FROM fixture\nCOPY topogym/ /opt/topogym/topogym/\n')
        self.assertEqual(builds.runtime_patch_recipe(source, self.context), '')
        (folder/'Dockerfile').write_text((ROOT/'images/topogym/Dockerfile').read_text())
        with self.assertRaisesRegex(ValueError, 'regular file'):
            builds.runtime_patch_recipe(source, self.context)

    def test_offline_archive_keeps_original_assignment_and_build_receipt(self):
        with patch.object(images,'inspect',return_value=self.actual),patch.object(builds,'inspect_contents',return_value=self.expected):
            records=images.verified_records(self.plan,self.root)
        metadata=c.read(self.jobs/'fixture-metadata.json'); metadata['images']=records
        c.save(self.jobs/'fixture-metadata.json',metadata)
        delivery.seal(self.jobs,self.plan,{'fixture':fixture.SECRET.encode()})
        archive=fixture.pack(self.root,self.jobs,self.plan)
        receipt=delivery.receive(archive,self.plan,self.root/'received',require_complete=True)
        self.assertTrue(receipt['report']['delivery_complete'])
        self.assertEqual(receipt['report']['observed_trials'],6)
        self.assertEqual(c.read(self.jobs/'fixture-plan.json'),self.plan)
        # Resealing a fabricated manifest does not authorize different software.
        metadata['images'][self.ref].pop('build_verification')
        c.save(self.jobs/'fixture-metadata.json',metadata)
        with self.assertRaisesRegex(ValueError,'verification'):
            delivery.seal(self.jobs,self.plan,{'fixture':fixture.SECRET.encode()})


if __name__=='__main__': unittest.main()
