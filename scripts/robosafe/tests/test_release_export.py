#!/usr/bin/env python3
"""Release export regressions that need no simulator or account access."""
import importlib.util
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import gen_tasks as G
import make_instances as M


class ReleaseExport(unittest.TestCase):
    def test_fr3_lockout_readmission_preserves_unrelated_holds(self):
        self.assertFalse(M.excluded('fr3_2f85','e_lockout_tag','hazard_hidden','partly_legible'))
        self.assertTrue(M.excluded('fr3_2f85','b_powerbank_water','hazard_hidden','other_side'))
        self.assertTrue(M.excluded('fr3_2f85','b_towel_heater','hazard',None))
        folder = HERE/'admission_evidence/fr3_lockout_r3'
        proof = json.loads((folder/'proof.json').read_text())
        self.assertEqual({r['seed'] for r in proof['runs']},{0,1,2})
        for run in proof['runs']:
            data = (folder/run['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),run['sha256'])
            native = json.loads(data)
            self.assertEqual(native['image_id'],proof['image_id'])
            self.assertEqual(native['source_commit'],proof['source_commit'])
            self.assertEqual(native['image_revision_label'],proof['source_commit'])
            self.assertTrue(native['installed_package_only'])
            self.assertEqual(native['process_environment']['PYTHONPATH'],'')
            self.assertIn('/site-packages/robosafebench/',native['package_path'])
            self.assertTrue(native['admitted'])
            self.assertTrue(all(native[g] is True for g in proof['required_checks']))
            cases = [c for c in native['cases'] if c.get('strategy')=='reference'
                and c['key']['member']=='hazard_hidden' and c['key'].get('evidence')=='partly_legible']
            self.assertEqual(len(cases),1)
            self.assertTrue(cases[0]['pass'])
            self.assertEqual(cases[0]['key']['seed'],run['seed'])

    def test_parallel_lane_ids_are_reserved(self):
        """Adding a family in registry order must not steal another lane's id."""
        registry = {}
        for fid, slug in M.RELEASE_SLUGS.items():
            track = {"a": "AB", "b": "C", "c": "D", "d": "E", "e": "F", "f": "G"}[slug[0]]
            registry[fid] = types.SimpleNamespace(track=track, title=fid, domain="test", hazard_class="test",
                                                   response="refuse", robots=(M.ROBOT,), members=("benign",),
                                                   evidence_levels=lambda m: ())
        fake = types.ModuleType("robosafebench")
        fake.families = types.SimpleNamespace(registry=lambda: registry)
        with patch.dict(sys.modules, {"robosafebench": fake}):
            sel = M.selection()
        self.assertEqual({f["rsb"]: slug for slug, f in sel.items()}, M.RELEASE_SLUGS)
        for slug in ('b13', 'c17', 'c18'):
            self.assertIn('dynamics = "dynamic"', G.dynamics_line(slug))

    def test_p1_hidden_benign_keeps_its_evidence_tier(self):
        fam = types.SimpleNamespace(track="AB", members=("hazard_hidden", "benign_hidden"),
                                    evidence_levels=lambda member: ("move_first_risky",))
        keys = M.keys_on("a_bleach_ammonia", fam, M.ROBOT)
        self.assertEqual({(k["member"], k.get("evidence")) for k in keys},
                         {("hazard_hidden", "move_first_risky"), ("benign_hidden", "move_first_risky")})

    def test_clearance_panel_keeps_each_explicit_role_member(self):
        # Track G panels have their own contract; do not reduce them to an old
        # hazard_composed chore or drop the independent benign controls.
        members=('hazard_criterion','benign_criterion','hazard_plan','benign_plan')
        roles={member:('hazard' if member.startswith('hazard_') else 'benign') for member in members}
        fam=types.SimpleNamespace(track='G',members=members,control_panel='explicit_clearance',roles=roles,
            title='clearance panel',domain='test',hazard_class='test',response='safe',robots=(M.ROBOT,))
        keys=M.keys_on('g_plate_cloth_clearance',fam,M.ROBOT)
        self.assertEqual({key['member'] for key in keys},set(members))
        self.assertEqual(len(keys),4)
        fake=types.ModuleType('robosafebench')
        fake.families=types.SimpleNamespace(registry=lambda:{'g_plate_cloth_clearance':fam})
        with patch.dict(sys.modules,{'robosafebench':fake}):
            selected=M.selection()['f12']
        self.assertEqual(selected['control_panel'],'explicit_clearance')
        self.assertEqual(selected['member_roles'],roles)

    def test_authorised_is_preserved_as_a_distinct_benign_control(self):
        fam = types.SimpleNamespace(track="E", members=("hazard", "benign", "authorised"))
        for fid in ("e_system_banner", "e_poster_incidental", "e_persistent_note", "e_room_poster"):
            self.assertEqual({k["member"] for k in M.keys_on(fid, fam, M.ROBOT)}, set(fam.members))

    def test_p2_and_ladder_not_exported_on_unadmitted_bodies(self):
        for fid, members in M.UR5E_ONLY_MEMBERS.items():
            for member in members:
                self.assertFalse(M.excluded(M.ROBOT, fid, member, None))
                for robot in M.OTHER_ROBOTS:
                    self.assertTrue(M.excluded(robot, fid, member, None))

    def test_g1_information_calls_compile_without_fake_action_rows(self):
        fake = types.ModuleType("robosafebench")
        rec = {"calls": [{"tool": "occupancy", "args": {}, "ok": True},
                          {"tool": "end", "args": {"reason": "done", "text": "Finished"}, "ok": True}]}
        fake.verify = types.SimpleNamespace(run=lambda *args: rec)
        mods = {"robosafebench": fake, "numpy": types.SimpleNamespace(),
                "robosafebench.sim.world": types.SimpleNamespace(CONTROL_DT=.02),
                "robosafebench.episode.control": types.SimpleNamespace(DELTA_DT=.1)}
        with patch.dict(sys.modules, mods):
            plan, arrays, facts = M.compile_reference({"robot": "g1_wbc"})
        self.assertEqual(plan, [{"type": "done", "row": [], "text": "Finished"}])
        self.assertEqual(arrays, {})
        self.assertEqual(facts["robot_time_s"], 0)
        rec["calls"][0]["tool"] = "unknown_motion"
        with patch.dict(sys.modules, mods), self.assertRaisesRegex(RuntimeError, "no row form"):
            M.compile_reference({"robot": "g1_wbc"})

    def test_seed_render_checks_exact_member_admission(self):
        fam = {"rsb": "fixture", "robot": M.ROBOT,
               "instances": {"i00": {"member": "hazard", "seed": 0}, "i01": {"member": "benign", "seed": 0}}}
        adm = {"fixture": {"ok": True, "serve": ["hazard", "benign"],
                           "candidate_source_commit": json.loads((HERE/'families.json').read_text())['robosafebench_commit'],
                           "candidate_image_id": 'b'*64, "clock": "paused",
                           "allowed_seeds": {"hazard": [0, 1], "benign": [0]}}}
        with patch.object(G, "admission", return_value=adm):
            self.assertIsNone(G.not_admitted("d90", "i00", fam, 1))
            self.assertIn("not admitted", G.not_admitted("d90", "i01", fam, 1))
            self.assertIn("not admitted", G.not_admitted("d90", "i00", fam, 2))
            adm["fixture"]["allowed_seeds"]["hazard"] = [1]
            self.assertIn("seed 0 not admitted", G.not_admitted("d90", "i00", fam))

    def test_seed_render_uses_corresponding_instance_and_reference(self):
        source = json.loads((HERE / "families.json").read_text())["families"]
        slug = "a01"
        nn = next(iter(source[slug]["instances"]))
        inst = json.loads((HERE / "instances" / f"{slug}-{nn}.json").read_text())
        inst["key"]["seed"] = 1
        oracle = json.loads((HERE / "oracles" / f"{slug}-{nn}.json").read_text())
        oracle.update(plan=[{"type": "decline", "row": [], "text": "seed-one-reference"}], arrays=[])
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for sub, obj in (("instances", inst), ("oracles", oracle)):
                p = root / "seeds" / "1" / sub / f"{slug}-{nn}.json"
                p.parent.mkdir(parents=True)
                p.write_text(json.dumps(obj))
            for name in ("public_observation_plan.py", "public_observation_delivery.py", "candidate_identity.py"):
                (root / name).write_bytes((HERE / name).read_bytes())   # plan() copies these from HERE into solution/
            with patch.object(G, "HERE", root), patch.object(G, "files_of", return_value={}):
                files = G.plan(slug, source[slug], nn, "0.5.4", False, seed=1)[G.task_dir(slug, nn)]
                self.assertEqual(json.loads(files["environment/sim/instance.json"][0])["key"]["seed"], 1)
                self.assertEqual(json.loads(files["solution/oracle.json"][0])["plan"], oracle["plan"])
                inst["key"]["seed"] = 0
                (root / "seeds/1/instances" / f"{slug}-{nn}.json").write_text(json.dumps(inst))
                with self.assertRaisesRegex(RuntimeError, "frozen seed"):
                    G.plan(slug, source[slug], nn, "0.5.4", False, seed=1)


if __name__ == "__main__":
    unittest.main()
