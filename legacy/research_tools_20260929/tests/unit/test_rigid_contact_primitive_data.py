"""URDF roles must handle Genesis' padded primitive buffer without broadcasting."""
from types import SimpleNamespace as NS

import numpy as np
import pytest

from topogym.tasks.base import EntitySpec
from topogym.world.physics.rigid_contacts import resolve_roles


def test_recentered_mesh_keeps_asset_role_and_conflicts_fail_closed(tmp_path):
    path = tmp_path / "mesh.urdf"
    shape = '<geometry><mesh filename="deck.obj"/></geometry>'
    path.write_text(f'<robot><link name="base"><collision name="deck">{shape}</collision></link></robot>')
    geom = NS(idx=4, type=NS(name="MESH"), init_pos=np.array([0., 0., .125]),
              init_quat=np.array([0., 1., 0., 0.]),
              mesh=NS(metadata={"mesh_path": str(tmp_path / "deck.obj")}))
    entity = NS(links=[NS(name="base", geoms=[geom])])
    spec = EntitySpec("base", "urdf", path, contact_roles={"deck": "finish_support"})
    assert resolve_roles(entity, spec) == ({4: "finish_support"}, True)
    path.write_text(f'<robot><link name="base"><collision name="deck">{shape}</collision>'
                    f'<collision name="other"><origin xyz="1 0 0"/>{shape}</collision></link></robot>')
    spec = EntitySpec("base", "urdf", path, contact_roles={"deck": "finish_support", "other": "wood_stop"})
    assert resolve_roles(entity, spec) == ({4: "unknown"}, False)


@pytest.mark.parametrize("shape,values", [
    ('<sphere radius="0.1"/>', [.1]),
    ('<cylinder radius="0.1" length="0.2"/>', [.1, .2]),
    ('<box size="0.1 0.2 0.3"/>', [.1, .2, .3]),
])
def test_padded_primitive_parameters_match_only_authored_geometry(tmp_path, shape, values):
    path = tmp_path / 'primitive.urdf'
    path.write_text(f'<robot><link name="tool"><collision name="metal"><geometry>{shape}</geometry></collision></link></robot>')
    spec = EntitySpec('tool', 'urdf', path, contact_roles={'metal': 'wand_metal'})
    data = np.zeros(7)
    data[:len(values)] = values
    geom = NS(idx=4, type=NS(name=shape.split()[0][1:].upper()),
              init_pos=[0, 0, 0], init_quat=[1, 0, 0, 0], data=data)
    entity = NS(links=[NS(name='tool', geoms=[geom])])
    assert resolve_roles(entity, spec) == ({4: 'wand_metal'}, True)
    data[0] += .01
    assert resolve_roles(entity, spec) == ({4: 'unknown'}, False)
    data[0] = values[0]
    data[-1] = 1
    assert resolve_roles(entity, spec) == ({4: 'unknown'}, False)
    geom.data = []
    assert resolve_roles(entity, spec) == ({4: 'unknown'}, False)
