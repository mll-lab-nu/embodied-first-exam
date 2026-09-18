"""Continuous, developable cloth geometry for a task-design preview.

The center and four flaps form ONE connected material surface. Each flap
unbends an arc at constant material length. These are prescribed geometric
states, not a cloth dynamics solver or evidence of a physically valid grasp.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation


def smooth(u):
    u = np.clip(u, 0., 1.)
    return u * u * (3. - 2. * u)


class WrapModel:
    # Outside-to-inside order: +x, -x, +y, -y.
    axes = ((0, 1), (0, -1), (1, 1), (1, -1))

    def __init__(self, cfg):
        self.half = np.asarray(cfg.half_base, float)
        self.lengths = np.asarray(cfg.flap_lengths, float)
        self.heights = np.asarray(cfg.layer_heights, float)
        self.board_size = np.asarray(cfg.board_size, float)
        self.board_z = float(cfg.board_center_z)
        self.mid_z = self.heights.max() / 2
        self.drape_drop = float(cfg.get('drape_drop',0.))
        spacing = float(cfg.grid_spacing)
        points, faces, lookup = [], [], {}

        def ticks(a, b):
            return np.linspace(a, b, max(2, int(np.ceil((b-a)/spacing))+1))

        def panel(xs, ys):
            ids = np.empty((len(xs), len(ys)), int)
            for i, x in enumerate(xs):
                for j, y in enumerate(ys):
                    key = (round(float(x), 9), round(float(y), 9))
                    if key not in lookup:
                        lookup[key] = len(points)
                        points.append((x, y))
                    ids[i, j] = lookup[key]
            for i in range(len(xs)-1):
                for j in range(len(ys)-1):
                    a, b, c, d = ids[i,j], ids[i+1,j], ids[i+1,j+1], ids[i,j+1]
                    faces.extend(((a,b,c), (a,c,d)))

        hx, hy = self.half
        bx, by = ticks(-hx,hx), ticks(-hy,hy)
        panel(bx, by)
        panel(ticks(hx,hx+self.lengths[0]), by)
        panel(ticks(-hx-self.lengths[1],-hx), by)
        panel(bx, ticks(hy,hy+self.lengths[2]))
        panel(bx, ticks(-hy-self.lengths[3],-hy))
        self.material = np.asarray(points)
        self.faces = np.asarray(faces, np.int32)
        self.flat = np.c_[self.material, np.zeros(len(points))]
        self.edges = np.unique(np.sort(np.concatenate(
            [self.faces[:,[0,1]],self.faces[:,[1,2]],self.faces[:,[2,0]]]),axis=1),axis=0)
        self.rest_edges = np.linalg.norm(self.flat[self.edges[:,0]]-self.flat[self.edges[:,1]],axis=1)

    def profile(self, s, flap, opened):
        if self.drape_drop>0 and opened>1e-8:
            # Inextensible tangent-angle interpolation from the wrapped arc
            # to a cloth draping over the edge of the visible narrow support.
            # Two 12 mm quarter-circle bends join the vertical hanging panel
            # to the upper and lower horizontal surfaces.
            from scipy.integrate import cumulative_trapezoid
            s=np.asarray(s)
            if not len(s):return s.copy(),s.copy()
            samples=np.unique(np.r_[np.linspace(0,self.lengths[flap],1001),s])
            radius=.012;quarter=np.pi*radius/2
            vertical=max(0.,self.drape_drop-2*radius)
            folded=np.minimum(samples/(self.heights[flap]/2),np.pi)
            draped=np.where(samples<quarter,-samples/radius,
                    np.where(samples<quarter+vertical,-np.pi/2,
                    np.minimum(0.,-np.pi/2+(samples-quarter-vertical)/radius)))
            angle=(1-opened)*folded+opened*draped
            xx=cumulative_trapezoid(np.cos(angle),samples,initial=0.)
            zz=cumulative_trapezoid(np.sin(angle),samples,initial=0.)
            return np.interp(s,samples,xx),np.interp(s,samples,zz)
        arc = np.pi * self.heights[flap] / 2
        angle = np.pi * (1-float(opened))
        s = np.asarray(s)
        if angle < 1e-8:
            return s, np.zeros_like(s)
        radius = arc / angle
        theta = np.minimum(s,arc) / radius
        tail = np.maximum(s-arc,0)
        return radius*np.sin(theta)+tail*np.cos(angle), radius*(1-np.cos(theta))+tail*np.sin(angle)

    def local(self, opened, material=None):
        uv = self.material if material is None else np.asarray(material)
        v = np.c_[uv, np.zeros(len(uv))]
        for i,(axis,sign) in enumerate(self.axes):
            s = sign*uv[:,axis]-self.half[axis]
            mask = s>1e-8
            out,z = self.profile(s[mask],i,opened[i])
            v[mask,axis] = sign*(self.half[axis]+out)
            v[mask,2] = z
        return v

    def transform(self, v, origin, angle):
        pivot = np.array([0.,0.,self.mid_z])
        return Rotation.from_rotvec([angle,0.,0.]).apply(np.asarray(v)-pivot)+pivot+origin

    def vertices(self, opened, origin, angle):
        return self.transform(self.local(opened),origin,angle)

    def tip(self, flap, opened, origin, angle=0.):
        axis, sign = self.axes[flap]
        uv = np.zeros((1,2))
        # Grip a narrow material patch 4 mm in from the free edge.
        uv[0,axis] = sign*(self.half[axis]+self.lengths[flap]-.004)
        return self.transform(self.local(opened,uv),origin,angle)[0]

    def board_pose(self, origin, angle):
        pos = self.transform([[0,0,self.board_z]],origin,angle)[0]
        quat = Rotation.from_rotvec([angle,0.,0.]).as_quat()[[3,0,1,2]]
        return pos,quat

    def audit_frame(self, vertices, board_pos, board_quat):
        lengths = np.linalg.norm(vertices[self.edges[:,0]]-vertices[self.edges[:,1]],axis=1)
        local = Rotation.from_quat(np.asarray(board_quat)[[1,2,3,0]]).inv().apply(vertices-board_pos)
        # Vertex and face-center samples: this is NOT continuous collision detection.
        samples = np.concatenate((local,local[self.faces].mean(axis=1)))
        inside = (np.abs(samples)<self.board_size/2-1e-5).all(axis=1)
        return dict(max_edge_length_change=float(np.max(np.abs(lengths/self.rest_edges-1))),
                    cloth_board_interior_samples=int(inside.sum()),
                    min_cloth_z=float(vertices[:,2].min()))
