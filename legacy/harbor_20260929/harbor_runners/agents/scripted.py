"""A native Harbor external agent exercising two feedback-separated submissions."""
import base64
import json
import shlex

from harbor.agents.base import BaseAgent


class ScriptedAgent(BaseAgent):
    def __init__(self, *, scenario="normal", **kwargs):
        super().__init__(**kwargs)
        if scenario not in {"normal", "invalid", "cancel", "pick-cube"}:
            raise ValueError("Unknown scripted test scenario")
        self.scenario = scenario

    @staticmethod
    def name():
        return "topogym-scripted"

    def version(self):
        return "1"

    async def setup(self, environment):
        result = await environment.exec(command="topogym-rollout ready --check-initial")
        if result.return_code:
            raise RuntimeError("Initial observation was not ready before agent setup")

    async def run(self, instruction, environment, context):
        async def execute(command):
            result = await environment.exec(command=command, timeout_sec=900)
            if result.return_code:
                raise RuntimeError("Scripted pipeline command failed; inspect worker/verifier logs")
            return result.stdout

        # This explicit read also checks that videos/logs are readable as the agent
        # UID. It is a no-model transport test, not a claim about visual reasoning.
        inspect = """import json,hashlib,subprocess
from pathlib import Path
s=json.loads(Path('/rollout/session.json').read_text())
r=json.loads(Path(s['latest_result_path']).read_text())
m=json.loads(Path(s['artifacts_manifest']).read_text())['artifacts']
videos=r['media']['videos']
assert videos and r['logs']['steps']
for item in [*videos.values(),*r['logs'].values(),r['media']['frame_map']]:
 p=Path(m[item['artifact_id']]['path'])
 assert hashlib.sha256(p.read_bytes()).hexdigest()==item['sha256']
 if p.suffix=='.mp4':
  subprocess.run(['ffmpeg','-v','error','-xerror','-nostdin','-threads','1','-i',str(p),'-f','null','-'],check=True)
rows=[json.loads(line) for line in Path(r['logs']['steps']['path']).open()]
assert len(rows)==r['saved_physics_steps']+1
assert rows[-1]['state']['state_id']==r['end_state_ref']['state_id']
print(json.dumps({'read_segment':r['segment_id'],'state':r.get('end_state_ref',r.get('state_ref'))}))
"""
        reads = []
        if self.scenario == "pick-cube":
            reads.append(await execute("python -c " + shlex.quote(inspect)))
            source = "from topogym.planning.examples.cube_pick_place import CubePickPlacePolicy\ndef create_policy(): return CubePickPlacePolicy()\n"
            encoded = base64.b64encode(source.encode()).decode()
            await execute("python -c " + shlex.quote(
                f"import base64; from pathlib import Path; Path('/workspace/pick_cube.py').write_bytes(base64.b64decode({encoded!r}))"))
            receipt = json.loads(await execute("topogym-rollout submit /workspace/pick_cube.py --request-id pick-cube --wait --timeout 850"))
            if receipt.get("request_status") != "finished":
                raise RuntimeError("Pick/place policy failed to finish")
            reads.append(await execute("python -c " + shlex.quote(inspect)))
            self.logs_dir.mkdir(parents=True, exist_ok=True)
            (self.logs_dir / "scripted_reads.json").write_text(json.dumps(reads, indent=2))
            return
        for segment, delta in ((1, .0005), (2, -.0005)):
            reads.append(await execute("python -c " + shlex.quote(inspect)))
            # Four EE_DELTA actions; measured state feedback stays in core policy
            # observations. This moves the TCP without attempting to solve a cube.
            source = f"""class Policy:
    def initialize(self, context):
        self.group = next(iter(context['action_spec']['groups']))
    def act(self, obs):
        if obs['execution_state']['control_steps'] >= 4:
            return None
        return {{self.group: {{'translation_world_m': [0., 0., {delta}], 'rotation_world_rad': [0., 0., 0.]}}}}
def create_policy():
    return Policy()
"""
            if segment == 2 and self.scenario == "invalid":
                source = "class Policy:\n def act(self, obs): return {'invalid_action_key': 1.0}\ndef create_policy(): return Policy()\n"
            if segment == 2 and self.scenario == "cancel":
                source = "import time\nclass Policy:\n def act(self, obs): time.sleep(100000)\ndef create_policy(): return Policy()\n"
            encoded = base64.b64encode(source.encode()).decode()
            path = f"/workspace/segment_{segment}.py"
            await execute("python -c " + shlex.quote(
                f"import base64; from pathlib import Path; Path({path!r}).write_bytes(base64.b64decode({encoded!r}))"))
            if segment == 2 and self.scenario == "cancel":
                receipt = json.loads(await execute(f"topogym-rollout submit {path} --request-id segment-2"))
                import asyncio
                for _ in range(100):
                    receipt = json.loads(await execute("topogym-rollout result --request-id segment-2"))
                    if receipt.get("request_status") == "running":
                        break
                    await asyncio.sleep(.1)
                if receipt.get("request_status") != "running":
                    raise RuntimeError("Cancellation fixture never entered execution")
                await asyncio.sleep(1)
                # Returning hands control to the ROOT verifier, whose independent
                # finish request must cancel this blocked policy before collection.
                break
            receipt = json.loads(await execute(f"topogym-rollout submit {path} --request-id segment-{segment} --wait --timeout 850"))
            if receipt.get("request_status") != "finished":
                raise RuntimeError("Segment did not finish")
        reads.append(await execute("python -c " + shlex.quote(inspect)))
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        (self.logs_dir / "scripted_reads.json").write_text(json.dumps(reads, indent=2))
