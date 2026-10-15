import sys, numpy as np
T="/home/pingyue/work/topogym/.claude/worktrees/yamlab-rope/yamlab_port/tasks/rope_threading/tools"
sys.path.insert(0,T)
import plot_layout as P, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
import threading_geom as TH
rings,rope=P.scene(195.0,(0.54,0.12),90.0,(0.58,-0.05))
for r in rings: r["yaw"]=195.0
old=[dict(r) for r in rings]
new=[]
for r in rings:
    r=dict(r)
    if r["name"]=="R2":
        c=r["center"].copy(); Rm=P.rot(-20)
        for k in ("stand_center","base_center"):
            p=r[k].copy(); p[:2]=c[:2]+Rm@(p[:2]-c[:2]); r[k]=p
        n=r["normal"].copy(); n[:2]=Rm@n[:2]; r["normal"]=n; r["yaw"]=175.0
    new.append(r)
fig,axs=plt.subplots(1,2,figsize=(26,10.5))
P.draw(axs[0],old,rope,"现行布局 yaw 195（R2 原位）",chain=["RL","LL","L"],feed_tip="start")
P.draw(axs[1],new,rope,"探索：R2 绕自身竖直轴转 −20°（其余不动）\n【待用户批准的新偏差】",chain=["RL","LL","L"],feed_tip="start")
# overlay old R2 on the right panel (grey dashed ring) and exit receive points
import plan_np as PN
ax=axs[1]; r2o=[r for r in old if r["name"]=="R2"][0]; r2n=[r for r in new if r["name"]=="R2"][0]
u,v=TH.ring_basis(r2o["normal"]); th=np.linspace(0,2*np.pi,97)
circ=r2o["center"]+0.075*(np.cos(th)[:,None]*u+np.sin(th)[:,None]*v)
ax.plot(*P.uv(circ),color="#888",lw=3,ls="--",zorder=3)
for rr,col in ((r2o,"#888"),(r2n,"#d35400")):
    d=-rr["sign"]*rr["normal"]; d=d/np.linalg.norm(d)
    for t in (0.05,0.07,0.10):
        p=rr["center"]+t*d; ax.plot(*P.uv(p),"x",color=col,ms=14,mew=3,zorder=9)
ax.text(0.73,0.115,"灰虚线 = R2 原位；橙 × = 转后 R2 出口接收点（面后 5/7/10 cm）；灰 × = 原位接收点",ha="right",va="bottom",fontsize=18)
fig.tight_layout(); fig.savefig("/tmp/claude-1002/s4/figr2/r2_m20.png",dpi=105)
print(fig.get_size_inches()*105)
