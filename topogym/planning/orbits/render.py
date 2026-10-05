"""Matplotlib three-view snapshots of the rope oracle (side, top, oblique)."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402


def fixture_lines(lay):
    out = []
    tops = [lay.ball_z, *lay.ring_z]
    for x, z in zip(lay.post_x, tops):
        out.append(('post', np.array([[x, 0, lay.base_height_m], [x, 0, z]])))
    th = np.linspace(0, 2*np.pi, 97)
    for x, z in zip(lay.ring_x, lay.ring_z):
        out.append(('ring', np.column_stack([x+lay.ring_radius_m*np.cos(th), lay.ring_radius_m*np.sin(th),
                                             np.full(97, z)])))
    b = np.array([[-1, -1], [1, -1], [1, 1], [-1, 1], [-1, -1]])*[lay.base_length_m/2, lay.base_width_m/2]
    out.append(('base', np.column_stack([b, np.full(5, lay.base_height_m)])))
    return out


def snapshot(path, lay, pts, handle=None, grips=(), title='', marks=()):
    fig = plt.figure(figsize=(15, 5.2))
    views = [(1, 'side (x-z)', (0, 2)), (2, 'top (x-y)', (0, 1))]
    for idx, name, (a, b) in views:
        ax = fig.add_subplot(1, 3, idx)
        for kind, L in fixture_lines(lay):
            ax.plot(L[:, a], L[:, b], color='saddlebrown', lw=3 if kind == 'post' else 2.2)
        if b == 2:
            ax.add_patch(plt.Circle((lay.post_x[0], lay.ball_z), lay.ball_radius_m, color='saddlebrown'))
        else:
            ax.add_patch(plt.Circle((lay.post_x[0], 0), lay.ball_radius_m, color='saddlebrown', alpha=.4))
        ax.plot(pts[:, a], pts[:, b], color='gold', lw=2)
        n = len(pts)
        ax.plot(pts[n//2, a], pts[n//2, b], 'o', color='red', ms=4)
        for i in marks:
            ax.plot(pts[i, a], pts[i, b], 's', color='purple', ms=3)
        if handle is not None:
            ax.plot(handle[a], handle[b], 's', color='sienna', ms=8)
        for g, c in zip(grips, ('blue', 'green', 'red', 'm')):
            if g is not None and g[2] > -.5:
                ax.plot(g[a], g[b], 'x', color=c, ms=10, mew=2)
        ax.set_aspect('equal'); ax.set_title(name); ax.grid(alpha=.3)
        ax.set_xlim(-.3, .45)
        ax.set_ylim(-.02 if b == 2 else -.2, .45 if b == 2 else .2)
    ax = fig.add_subplot(1, 3, 3, projection='3d')
    for kind, L in fixture_lines(lay):
        ax.plot(L[:, 0], L[:, 1], L[:, 2], color='saddlebrown', lw=2)
    u, w = np.mgrid[0:2*np.pi:12j, 0:np.pi:8j]
    r = lay.ball_radius_m
    ax.plot_surface(lay.post_x[0]+r*np.cos(u)*np.sin(w), r*np.sin(u)*np.sin(w), lay.ball_z+r*np.cos(w),
                    color='saddlebrown', alpha=.5)
    ax.plot(pts[:, 0], pts[:, 1], pts[:, 2], color='goldenrod', lw=2)
    ax.plot([pts[len(pts)//2, 0]], [pts[len(pts)//2, 1]], [pts[len(pts)//2, 2]], 'o', color='red', ms=4)
    for g, c in zip(grips, ('blue', 'green', 'red', 'm')):
        if g is not None and g[2] > -.5:
            ax.plot([g[0]], [g[1]], [g[2]], 'x', color=c, ms=10, mew=2)
    ax.set_xlim(-.25, .25); ax.set_ylim(-.25, .25); ax.set_zlim(0, .4)
    ax.view_init(elev=28, azim=-60)
    ax.set_box_aspect((1, 1, .8))
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=80)
    plt.close(fig)


def snap_oracle(o, path, title='', marks=()):
    h, _ = o.handle_pose()
    grips = [o.grip_pos(g) if o.held[g] is not None else None for g in 'ABCD']
    snapshot(path, o.lay, o.points(), h, grips, title=f'{title}  t={o.data.time:.1f}s', marks=marks)
