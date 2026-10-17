"""New mechanism selection keeps native members, body scope and historical task identities."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mechanism_make_instances', HERE / 'make_instances.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def family(track, members, robots=(M.ROBOT,), **facts):
    return types.SimpleNamespace(track=track, members=members, robots=robots, title='fixture', domain='test',
        hazard_class='test', response='safe', variants=lambda member: (), evidence_levels=lambda member: (), **facts)


class MechanismSelectionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.registry = {}
        self.bodies = types.SimpleNamespace(ROOM_EXCLUDED={}, ROOM_MEMBER_EXCLUDED={})
        native_families = types.ModuleType('robosafebench.families')
        native_families.registry = lambda: self.registry
        native_families.bodies = self.bodies
        native = types.ModuleType('robosafebench')
        native.families = native_families
        for replacement in (patch.object(M, 'HERE', self.root), patch.dict(sys.modules, {
                'robosafebench': native, 'robosafebench.families': native_families})):
            replacement.start()
            self.addCleanup(replacement.stop)

    def save(self, selection):
        (self.root / 'families.json').write_text(json.dumps({'families': selection}))

    def test_new_mechanisms_keep_distinct_members_native_body_and_camera_limits(self):
        scope = {'interfaces': ('control',), 'clocks': ('paused',), 'movers': ('scripted',)}
        limits = dict(development_scope=scope, release_status='development; installed admission pending')
        plate_members = ('hazard_criterion', 'benign_criterion', 'hazard_plan', 'benign_plan')
        self.registry.update({
            'h_bimanual_knife_transfer': family('AB', ('hazard_unnamed', 'benign_context'), ('yam_bimanual',),
                required_image_cameras=('front',), **limits),
            'd_bounded_recovery': family('D', ('hazard', 'benign'), required_image_cameras=('front',), **limits),
            'g_plate_cloth_clearance': family('G', plate_members, required_image_cameras=('front', 'top'),
                control_panel='explicit_clearance', roles=M.ROLE_MAP['g_plate_cloth_clearance'], **limits),
            'e_delegation_revoked': family('E', ('hazard', 'benign'), required_image_cameras=('front',), **limits),
        })
        self.registry['e_delegation_revoked'].variants = lambda member: ('explicit_safe_plan',)
        selected = M.selection()
        for slug, fid, robot, members in (
                ('a38', 'h_bimanual_knife_transfer', 'yam_bimanual', {'hazard_unnamed', 'benign_context'}),
                ('c19', 'd_bounded_recovery', M.ROBOT, {'hazard', 'benign'}),
                ('f12', 'g_plate_cloth_clearance', M.ROBOT, set(plate_members)),
                ('d18', 'e_delegation_revoked', M.ROBOT, {'hazard', 'benign'})):
            exported = selected[slug]
            self.assertEqual(exported['rsb'], fid)
            self.assertEqual(exported['robot'], robot)
            self.assertEqual({key.get('robot', exported['robot']) for key in exported['instances'].values()}, {robot})
            self.assertEqual({key['member'] for key in exported['instances'].values()}, members)
            self.assertEqual(exported['member_roles'], M.ROLE_MAP[fid])
            self.assertEqual(exported['development_scope'], scope)
            self.assertEqual(exported['release_status'], limits['release_status'])
            self.assertFalse(any(key.get('variant') for key in exported['instances'].values()))
            self.assertFalse(any(key.get('cameras') for key in exported['instances'].values()))
        self.assertEqual(selected['f12']['required_image_cameras'], ('front', 'top'))
        self.assertEqual(selected['a38']['required_image_cameras'], ('front',))
        self.save(selected)
        planned = M.selection(variants=('explicit_safe_plan',))
        for slug, exported in selected.items():
            for number, key in exported['instances'].items():
                self.assertEqual(planned[slug]['instances'][number], key)
        self.assertEqual({(key['member'], key['variant']) for key in planned['d18']['instances'].values()
                          if key.get('variant')}, {('hazard', 'explicit_safe_plan'), ('benign', 'explicit_safe_plan')})
        self.assertEqual(len(planned['f12']['instances']), 4)

    def test_pressure_is_existing_d10_and_native_g1_hold_is_not_lifted(self):
        self.registry['e_room_stranger_escalates'] = family('E', ('hazard', 'benign'), ('tidybot', 'g1_wbc'),
            camera_conditions=('room', 'onboard'))
        self.bodies.ROOM_EXCLUDED['e_room_stranger_escalates'] = ('g1_wbc', 'integrated admission pending')
        selected = M.selection()
        self.assertEqual(list(selected), ['d10'])
        keys = selected['d10']['instances'].values()
        self.assertEqual({(key['member'], key['robot'], key['cameras']) for key in keys},
                         {(member, 'tidybot', camera) for member in ('hazard', 'benign')
                          for camera in ('room', 'onboard')})

    def test_disabled_freshness_remains_out_even_when_variants_requested(self):
        self.registry['e_state_snapshot_changed'] = family('E', ('hazard', 'benign'), enabled=False,
            required_image_cameras=('front',), development_scope={'interfaces': ('control',), 'clocks': ('paused',)})
        self.assertEqual(M.selection(variants=('explicit_safe_plan',)), {})

    def test_new_instances_append_after_all_historical_ids_and_retired_highest_id(self):
        fid = 'e_delegation_revoked'
        self.registry[fid] = family('E', ('hazard', 'benign'))
        hazard = {'member': 'hazard', 'seed': 0}
        retired = {'member': 'removed_member', 'seed': 0}
        self.save({'d18': {'rsb': fid, 'track': 'E', 'instances': {'i02': hazard, 'i09': retired}}})
        selected = M.selection()
        self.assertEqual(selected['d18']['instances'], {'i02': hazard, 'i10': {'member': 'benign', 'seed': 0}})
        self.assertEqual(selected['d18']['instance_id_high_watermark'], 10)
        # Retire the highest live id too. Its tombstone must survive another selection saved to disk.
        self.registry[fid].members = ('hazard',)
        self.save(selected)
        retired_selection = M.selection()
        self.assertEqual(retired_selection['d18']['instances'], {'i02': hazard})
        self.assertEqual(retired_selection['d18']['instance_id_high_watermark'], 10)
        self.save(retired_selection)
        self.registry[fid].members = ('hazard', 'benign')
        appended = M.selection()
        self.assertEqual(appended['d18']['instances'], {'i02': hazard, 'i11': {'member': 'benign', 'seed': 0}})
        self.assertEqual(appended['d18']['instance_id_high_watermark'], 11)


if __name__ == '__main__':
    unittest.main()
