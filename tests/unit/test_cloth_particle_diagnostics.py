import numpy as np
import pytest

from topogym.evaluation.cloth_diagnostics import ClothParticleDiagnostics


def diagnostic(**extra):
    uv = np.array([[0., -.15], [.01, -.15], [0., .15], [.01, .15]])
    return ClothParticleDiagnostics(uv, width=.4, panel_fractions=(.5,.5), crease_band=.01,
        particle_size=.008, table_z=0., table_bounds=([-.5,-.5],[.5,.5]), particle_start=7, **extra)


def test_material_ownership_survives_fold_and_locates_contact_candidate():
    d = diagnostic()
    # Distant material patches are now stacked. This is contact, not rebinding.
    p = np.array([[0.,0.,.004],[.01,0.,.004],[0.,0.,.012],[.01,0.,.012]])
    v = np.zeros_like(p);v[2,2]=.1
    original=p.copy();vel=v.copy()
    row=d.sample(0,0.,"released_settle",p,v,free=np.ones(4,dtype=bool))
    h=row['hotspots'][0]
    assert h['particle_id']==2 and h['solver_particle_id']==9 and h['panel_id']==1
    assert h['nearest_nonlocal_contact_candidate']['particle_id']==0
    assert not h['near_table'] and h['free']
    assert not row['binding']['available']
    np.testing.assert_array_equal(p,original);np.testing.assert_array_equal(v,vel)
    assert d.summary()['recurrent_hotspots'][0]['released_exceedance_samples']==1


def test_binding_mutation_detected_even_when_weights_still_sum_to_one():
    d=diagnostic(support_indices=np.array([[0,1]]),support_weights=np.array([[.5,.5]]),
        visual_uv=np.array([[.005,-.15]]))
    assert d.binding_report()['nonlocal_support_count']==0
    changed=d.binding_report((np.array([[0,2]]),np.array([[.5,.5]])))
    assert changed['changed_visual_vertices']==1 and changed['nonlocal_support_count']==1
    weights=d.binding_report((np.array([[0,1]]),np.array([[.4,.6]])))
    assert weights['changed_visual_vertices']==1 and weights['nonlocal_support_count']==0
    assert weights['maximum_weight_sum_error']==0


def test_constraints_velocity_differences_and_sample_clock():
    d=diagnostic(edges=np.array([[0,1]]),rest_lengths=np.array([.01]))
    p=np.c_[d.uv,np.full(4,.004)];v=np.zeros_like(p)
    d.sample(3,.1,'gather',p,v)
    v[1,0]=.04;p[1,0]=.011
    row=d.sample(4,.1025,'released_settle',p,v)
    h=row['hotspots'][0]
    assert h['maximum_incident_edge_ratio']==pytest.approx(1.1)
    assert h['delta_velocity_m_s']==[.04,0.,0.]
    assert d.summary()['released_samples']==1
    with pytest.raises(ValueError,match='monotonically'):
        d.sample(4,.1025,'released_settle',p,v)


def test_negative_affine_weights_and_supports_across_adjacent_regions_are_valid():
    uv=np.array([[0.,-.001],[0.,.001]])
    d=ClothParticleDiagnostics(uv,width=.1,panel_fractions=(.5,.5),crease_band=.01,
        particle_size=.008,table_z=0.,table_bounds=([-.5,-.5],[.5,.5]),
        support_indices=np.array([[0,1]]),support_weights=np.array([[1.1,-.1]]),visual_uv=np.array([[0.,-.0012]]))
    assert d.panels.tolist()==[0,1]
    assert d.binding_report()['nonlocal_support_count']==0
    assert d.binding_report()['maximum_weight_sum_error']==0


def test_live_recorder_uses_only_read_access_and_original_free_order(tmp_path):
    from types import SimpleNamespace as N
    from topogym.world.physics.cloth_diagnostics import ClothDiagnosticRecorder
    p=np.array([[0.,-.15,.004],[.01,-.15,.004],[0.,.15,.004],[.01,.15,.004]])
    idx=np.array([[1,2]])
    weights=np.array([[.5,.5]])
    field=lambda a:N(to_numpy=lambda:a.copy())
    entity=N(particle_start=1,vvert_start=0,n_particles=4,n_vverts=1,_particles=p,
        _vverts=np.array([[.005,-.15,.004]]),edges=np.array([[0,1],[2,3]]),_edges_len_rest=np.array([.01,.01]),
        solver=N(vverts_info=N(support_idxs=field(idx),support_weights=field(weights)),
                 particles=N(free=field(np.array([[False],[True],[False],[True],[True]])))))
    task=N(entities={'blanket':entity},material_uv=p[:,:2],birth_uv=np.array([[.005,-.15]]),
        layout=N(width_m=.4,particle_size_m=.008),table_height_m=0.)
    recorder=ClothDiagnosticRecorder(tmp_path/'diagnostics',task,N(panel_fractions=(.5,.5),crease_band_m=.01),
        table_bounds=([-.5,-.5],[.5,.5]))
    row=recorder.sample(0,0.,'flat_birth',p,np.zeros_like(p))
    assert row['binding']['current_observed'] and row['fixed_particles']==1
    idx[0,1]=4
    row=recorder.sample(1,.0025,'gather',p,np.zeros_like(p))
    assert row['binding']['changed_visual_vertices']==1
    assert (tmp_path/'diagnostics/binding_change_1.npz').is_file()
    recorder.close()
    assert (tmp_path/'diagnostics/summary.json').is_file()
