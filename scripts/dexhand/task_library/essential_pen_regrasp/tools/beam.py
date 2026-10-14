"""Sampling-based beam search over short finger-target segments (authoring only; motor targets only).
States are forked with mj_getState/mj_setState (full integration state) in worker processes."""
import numpy as np, mujoco, copy, json, sys, os, time, pickle, math
import multiprocessing as mp
FLAGS=mujoco.mjtState.mjSTATE_INTEGRATION
G={}
P1={'cw':3}
def init():
    from runtime import Session
    s=Session("essential_pen_regrasp",hand="wuji");G['s']=s
    G['band']=None
def get_state(s):
    st=np.empty(mujoco.mj_stateSize(s.model,FLAGS));mujoco.mj_getState(s.model,s.data,st,FLAGS)
    return dict(x=st,chk=copy.deepcopy(s.checker.__dict__),steps=s.steps,ry=s._raw_yaw,ya=s._yaw_accum,peaks=dict(s._peaks))
def set_state(s,S):
    mujoco.mj_setState(s.model,s.data,S['x'],FLAGS);mujoco.mj_forward(s.model,s.data)
    s.checker.__dict__.update(copy.deepcopy(S['chk']));s.steps=S['steps'];s._raw_yaw=S['ry'];s._yaw_accum=S['ya'];s._peaks=dict(S['peaks']);s.actions=[]
def tipdist(s):
    """distance of thumb/index/middle fingertip geoms to the pen band (band = shaft section |z-0.0247|<0.012)."""
    m,d=s.model,s.data;ob=d.body('object');R=ob.xmat.reshape(3,3);out=[]
    pg=m.geom('task_object').id
    for f in ('thumb','index','middle'):
        g=m.geom('right_%s_fingertip_collision'%f).id;ft=np.zeros(6)
        dist=mujoco.mj_geomDistance(m,d,g,pg,.1,ft);z=(R.T@(ft[3:]-ob.xpos))[2]
        out.append(max(dist,0)+max(0,abs(z-0.0247)-0.010))
    return out
def pendist(s):
    m,d=s.model,s.data;out=[]
    pgs=[m.geom(n).id for n in ('task_object','task_object_tip','task_object_tail')]
    for f in ('thumb','index','middle','ring','pinky'):
        g=m.geom('right_%s_fingertip_collision'%f).id
        out.append(max(0,min(mujoco.mj_geomDistance(m,d,g,pg,.1,None) for pg in pgs)))
    return sorted(out)
def score(s,mode):
    st=s.status();f=s.features()
    if st['failed']:return -1e9,f,st
    sc=0.0
    if mode==1:
        sc-=abs(f['pen_axial']-0.030)*1000;sc-=40*max(0,f['pen_angle']-0.15)
        sc+=P1['cw']*min(f['contacts'],2)-max(0,f['object_displacement']-0.05)*1000
        sc+=200*st['stage']+10*st['stage_hold']
        if f['contacts']<2: sc-=P1.get('dw',300)*pendist(s)[1]
    elif mode==3:
        sc=1000*st['stage']+100*st['terminal_hold']+300*st['success']-200*min(f['speed'],1)+20*(f['pen_grip_thumb']+f['pen_grip_index']+f['pen_grip_middle'])-50*f['pen_palm_contacts']
        sc-=100*max(0,abs(f['pen_angle']-0.785)-0.08)+300*max(0,abs(f['pen_axial']-0.030)-0.003)
    else:
        sc-=abs(f['pen_axial']-0.030)*P1.get('xw',300)+P1.get('aw',100)*max(0,abs(f['pen_angle']-0.78)-0.08)
        sc-=sum(tipdist(s))*1000;sc+=5*(f['pen_grip_thumb']+f['pen_grip_index']+f['pen_grip_middle'])
        sc-=10*f['pen_palm_contacts']-max(0,f['object_displacement']-0.055)*1000
        sc+=200*st['stage']+10*st['stage_hold']+10*st['terminal_hold']-5*min(f['speed'],1)
    return sc,f,st
def expand(args):
    S,cur,seed,mode,L,sig,which,cw,xw,dw,zc=args;P1['cw']=cw;P1['xw']=xw;P1['dw']=dw
    s=G['s'];set_state(s,S);rng=np.random.default_rng(seed);lo,hi=s.model.actuator_ctrlrange.T
    tgt=cur.copy()
    if not (zc and seed%7==0): tgt[which]+=rng.normal(0,sig,len(which))
    tgt=np.clip(tgt,lo,hi)
    acts=[]
    for k in range(L):
        a=cur+(tgt-cur)*min(1,(k+1)/(L*0.6));acts.append(a);r=s.step(a)
        if r['done']:break
    sc,f,st=score(s,mode)
    return sc,get_state(s),tgt,acts,dict(ax=round(f['pen_axial']*1000,1),ang=round(f['pen_angle'],3),c=f['contacts'],gc=f['pen_grip_contacts'],pp=f['pen_palm_contacts'],disp=round(f['object_displacement']*1000,1),sp=round(f['speed'],3),stg=st['stage'],sh=st['stage_hold'],th=st['terminal_hold'],ok=st['success'],fail=st['failure'])
if __name__=='__main__':
    P=dict(mode=1,K=6,M=8,L=10,sig=0.12,levels=60,seed=0,start=None,out='beam1.pkl',fingers='TFM')
    if len(sys.argv)>1:P.update(json.loads(sys.argv[1]))
    from runtime import Session
    s=Session("essential_pen_regrasp",hand="wuji");names=s.actuator_names
    which=[i for i,n in enumerate(names) if any(('_'+c+'FJ' if c!='T' else '_THJ') in n for c in P['fingers'])]
    prefix=[]
    if P['start']:
        prefix=list(np.load(P['start'])['actions'])
        for a in prefix:s.step(a)
    root=dict(S=get_state(s),cur=(prefix[-1] if prefix else s.hold_action()).copy(),acts=list(prefix),sc=-1e9)
    beam=[root];pool=mp.get_context('fork').Pool(P.get('workers',4),initializer=init);rng=np.random.default_rng(P['seed']);t0=time.time();best=root
    for lev in range(P['levels']):
        jobs=[];owners=[]
        for bi,b in enumerate(beam):
            for j in range(P['M']):
                jobs.append((b['S'],b['cur'],int(rng.integers(1<<30)),P['mode'],P['L'],P['sig'],which,P.get('cw',3),P.get('xw',300),P.get('dw',300),P.get('zero_child',0)));owners.append(bi)
        res=pool.map(expand,jobs)
        cands=[]
        for (sc,S,tgt,acts,info),bi in zip(res,owners):
            if sc<-1e8:continue
            cands.append(dict(S=S,cur=tgt,acts=beam[bi]['acts']+acts,sc=sc,info=info))
        if not cands:print('all failed at level',lev);break
        cands.sort(key=lambda c:-c['sc']);beam=cands[:P['K']]
        if beam[0]['sc']>best['sc'] or P.get('keep_last'):best=beam[0]
        np.savez(P['out'].replace('.pkl','_best.npz'),actions=np.array(best['acts']))
        print(lev,round(time.time()-t0),len(beam[0]['acts']),round(beam[0]['sc'],1),beam[0]['info'],'| best',round(best['sc'],1),flush=True)
        if best['info']['ok'] or (P['mode']==1 and best['info']['stg']>=1) or (P['mode']==2 and best['info']['stg']>=2 and P.get('stop2')):break
    pickle.dump(dict(P=P,acts=np.array(best['acts']),info=best['info']),open(P['out'],'wb'))
    np.savez(P['out'].replace('.pkl','.npz'),actions=np.array(best['acts']))
