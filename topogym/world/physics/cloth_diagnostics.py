"""Optional read-only management recorder for live cloth preparation ticks."""
import json
from pathlib import Path

import numpy as np

from topogym.evaluation.cloth_diagnostics import ClothParticleDiagnostics
from topogym.utils.io import sha256_file, write_json_atomic
from topogym.world.physics.pbd_binding import read_birth_visual_binding


class ClothDiagnosticRecorder:
    def __init__(self, folder, task, profile, *, table_bounds, speed_limit=.03):
        self.root = Path(folder)
        self.root.mkdir(parents=True, exist_ok=False)
        self.entity = task.entities["blanket"]
        binding = read_birth_visual_binding(self.entity)
        self.birth_hash = binding.sha256
        self.changed_hashes = set()
        self.diagnostics = ClothParticleDiagnostics(task.material_uv,
            width=task.layout.width_m, panel_fractions=profile.panel_fractions,
            crease_band=profile.crease_band_m, particle_size=task.layout.particle_size_m,
            table_z=task.table_height_m, table_bounds=table_bounds,
            particle_start=int(self.entity.particle_start), speed_limit=speed_limit,
            edges=self.entity.edges, rest_lengths=self.entity._edges_len_rest,
            support_indices=binding.support_indices, support_weights=binding.support_weights,
            visual_uv=task.birth_uv)
        np.savez_compressed(self.root/"static.npz", material_uv_m=task.material_uv,
            panel_id=self.diagnostics.panels, crease_distance_m=self.diagnostics.crease_distance,
            support_indices=binding.support_indices, support_weights=binding.support_weights,
            visual_uv_m=task.birth_uv, particle_birth_positions_m=binding.particle_birth_positions_m,
            edges=self.diagnostics.edges, rest_lengths=self.diagnostics.rest)
        write_json_atomic(self.root/"metadata.json", dict(schema_version=1, entity="blanket",
            particle_start=binding.particle_start, visual_start=binding.vvert_start,
            original_particle_count=len(task.material_uv), binding_sha256=binding.sha256,
            static_sha256=sha256_file(self.root/"static.npz"), speed_limit_m_s=speed_limit,
            observation_phase="post World.advance, including configured table friction",
            material_ownership="UV regions fixed at birth; not dynamic stack layers",
            contact_candidate_radius_m=1.05*task.layout.particle_size_m,
            implementation_sha256={str(p.name): sha256_file(p) for p in
                (Path(__file__), Path(__file__).parents[2]/"evaluation/cloth_diagnostics.py")}))
        self.stream = (self.root/"ticks.jsonl").open("x")

    def sample(self, tick, time_s, stage, positions, velocities):
        binding_error = None
        try:
            current = read_birth_visual_binding(self.entity)
            current_pair = (current.support_indices, current.support_weights)
            if current.sha256 != self.birth_hash and current.sha256 not in self.changed_hashes:
                np.savez_compressed(self.root/f"binding_change_{tick}.npz",
                    support_indices=current.support_indices, support_weights=current.support_weights)
                self.changed_hashes.add(current.sha256)
        except (ValueError, RuntimeError) as error:
            current_pair = None
            binding_error = str(error)
        start = self.entity.particle_start
        free = self.entity.solver.particles.free.to_numpy()[start:start+self.entity.n_particles, 0]
        row = self.diagnostics.sample(tick, time_s, stage, positions, velocities,
            current_binding=current_pair, free=free)
        if binding_error is not None:
            row["binding"] = dict(available=False, read_error=binding_error)
        self.stream.write(json.dumps(row, allow_nan=False)+"\n")
        self.stream.flush()
        return row

    def close(self):
        if not self.stream.closed:
            self.stream.close()
            write_json_atomic(self.root/"summary.json", self.diagnostics.summary())
