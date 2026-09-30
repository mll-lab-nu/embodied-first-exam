"""Task-scene evidence consumers; no edits to the shared API test machinery."""
from pathlib import Path
import hashlib
import json
import numpy as np

from runtime_evidence import RuntimeEvidence, state_arrays
from topogym.utils.io import to_jsonable


class SceneEvidence(RuntimeEvidence):
    def __init__(self, folder, task_id, config):
        super().__init__(folder, task_id, config)
        self.report["scope"] = "default-scene appearance, initial physics and explicitly listed diagnostics; not task solved"

    def scene_inventory(self, env):
        entries = []
        for name, entity in env._world.entities.items():
            if name in {"table", "robot"}:
                continue
            entries.append(dict(name=name, entity_type=type(entity).__name__,
                visual_geometries=getattr(entity, "n_vgeoms", None),
                physics_geometries=getattr(entity, "n_geoms", None),
                morph_type=type(entity.morph).__name__,
                asset=str(getattr(entity.morph, "file", "")),
                fixed=getattr(entity.morph, "fixed", None)))
        self.report["scene_entities"] = entries
        self.report["task_parameters"] = to_jsonable(env._task.config)
        self.report["goal_evaluation_complete"] = env._task.goal_complete
        self.report["task_success"] = False
        self.save()


class PhysicsSceneEvidence(SceneEvidence):
    """Explicit RGB-off evidence; invariant checks come from the tick auditor."""

    def sample(self, env, observation, info, *, action=None, label="step"):
        assert not env.config.enable_rgb
        values = state_arrays(dict(world=env.privileged.get('world'), robot=env.privileged.get('robot')))
        index = self.report['samples']
        filename = f'state_{index:04d}.npz'
        np.savez_compressed(self.folder/filename, **values)
        self.rows.write(json.dumps(to_jsonable(dict(index=index, label=label, info=info,
            action=action, state_file=filename)))+'\n')
        self.rows.flush()
        self.report.update(samples=index+1, last_info=to_jsonable(info),
                           presentation=dict(enable_rgb=False, recording='not_requested'))
        self.save()
        assert all(np.isfinite(value).all() for value in values.values())
        return values


def source_identity(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ("topogym", "tests", "scripts")
            for path in sorted((Path(root)/folder).rglob("*.py"))
            if "__pycache__" not in str(path) and "agents" not in path.parts}
