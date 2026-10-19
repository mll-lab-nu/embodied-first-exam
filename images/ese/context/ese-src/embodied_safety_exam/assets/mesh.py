"""Triangle meshes built from parameters: boxes, extrusions, solids of revolution and prisms with pockets.

Every constructor returns a closed surface with outward-facing triangles (counter-clockwise seen from outside).
Coordinates are whatever unit the caller uses; the asset builders work in millimetres and scale to metres on output.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

_WELD = 1e-6          # vertices closer than this (in caller units) are the same vertex


@dataclass
class Mesh:
    v: np.ndarray                      # (N, 3) float64
    f: np.ndarray                      # (M, 3) int64
    uv: np.ndarray | None = None       # (N, 2) texture coordinates, optional

    def __post_init__(self) -> None:
        self.v = np.asarray(self.v, dtype=np.float64).reshape(-1, 3)
        self.f = np.asarray(self.f, dtype=np.int64).reshape(-1, 3)
        if self.uv is not None:
            self.uv = np.asarray(self.uv, dtype=np.float64).reshape(-1, 2)

    @property
    def n_triangles(self) -> int:
        return int(len(self.f))

    def scaled(self, s: float) -> "Mesh":
        return Mesh(self.v * s, self.f.copy(), None if self.uv is None else self.uv.copy())

    def moved(self, offset: Sequence[float]) -> "Mesh":
        return Mesh(self.v + np.asarray(offset, dtype=np.float64), self.f.copy(), None if self.uv is None else self.uv.copy())

    def transformed(self, rot: np.ndarray, offset: Sequence[float] = (0.0, 0.0, 0.0)) -> "Mesh":
        """Apply a proper rotation matrix, then a translation."""
        return Mesh(self.v @ np.asarray(rot, dtype=np.float64).T + np.asarray(offset, dtype=np.float64), self.f.copy(),
                    None if self.uv is None else self.uv.copy())

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.v.min(axis=0), self.v.max(axis=0)


class _Builder:
    """Collects vertices (welded on a fine grid) and triangles."""

    def __init__(self) -> None:
        self._index: dict[tuple[int, int, int], int] = {}
        self.verts: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, int, int]] = []

    def vertex(self, x: float, y: float, z: float) -> int:
        key = (round(x / _WELD), round(y / _WELD), round(z / _WELD))
        i = self._index.get(key)
        if i is None:
            i = len(self.verts)
            self._index[key] = i
            self.verts.append((float(x), float(y), float(z)))
        return i

    def tri(self, a: int, b: int, c: int) -> None:
        if a != b and b != c and a != c:
            self.faces.append((a, b, c))

    def quad(self, a: int, b: int, c: int, d: int) -> None:
        self.tri(a, b, c)
        self.tri(a, c, d)

    def mesh(self) -> Mesh:
        return Mesh(np.array(self.verts, dtype=np.float64), np.array(self.faces, dtype=np.int64))


# ----------------------------------------------------------------------------------------------------------------------
# 2-D helpers
# ----------------------------------------------------------------------------------------------------------------------

def circle(radius: float, n: int, center: Sequence[float] = (0.0, 0.0), phase: float = 0.0) -> np.ndarray:
    """A counter-clockwise regular n-gon inscribed in the circle."""
    a = phase + 2.0 * math.pi * np.arange(n) / n
    return np.stack([center[0] + radius * np.cos(a), center[1] + radius * np.sin(a)], axis=1)


def rect(sx: float, sy: float, center: Sequence[float] = (0.0, 0.0)) -> np.ndarray:
    """A counter-clockwise rectangle, starting at the (-x, -y) corner."""
    hx, hy = sx / 2.0, sy / 2.0
    cx, cy = center
    return np.array([[cx - hx, cy - hy], [cx + hx, cy - hy], [cx + hx, cy + hy], [cx - hx, cy + hy]])


def polygon_area(loop: np.ndarray) -> float:
    x, y = loop[:, 0], loop[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def _ring_triangles(outer: list[int], inner: list[int], pts: dict[int, tuple[float, float]]):
    """Triangles filling the ring between a convex outer loop and a convex inner loop (both counter-clockwise).

    Every outer edge is joined to the inner vertex that lies furthest towards it (its support vertex), and every outer
    vertex fans over the inner vertices between the support vertices of its two edges. A segment from the outer loop
    to a support vertex cannot enter the inner polygon, so no triangle overlaps the hole or another triangle.
    """
    no, ni = len(outer), len(inner)
    ip = [pts[i] for i in inner]
    support: list[int] = []
    for k in range(no):
        (x0, y0), (x1, y1) = pts[outer[k]], pts[outer[(k + 1) % no]]
        nx, ny = (y1 - y0), -(x1 - x0)                       # outward normal of a counter-clockwise edge
        scale = math.hypot(nx, ny)
        d = [(nx * x + ny * y) / scale for x, y in ip]
        best = max(d)
        tied = [j for j in range(ni) if d[j] >= best - 1e-7]
        if not support:
            # start from the tied vertex whose predecessor is not tied (the first one going counter-clockwise)
            first = [j for j in tied if (j - 1) % ni not in tied]
            support.append(first[0] if first else tied[0])
        else:
            support.append(min(tied, key=lambda j: ((j - support[-1]) % ni, j)))
    turned = sum((support[(k + 1) % no] - support[k]) % ni for k in range(no))
    if turned != ni:
        raise ValueError("ring triangulation failed: the loops are not convex or not nested")
    for k in range(no):
        a, b = outer[k], outer[(k + 1) % no]
        yield (a, b, inner[support[k]])
        j = support[k]
        while j != support[(k + 1) % no]:
            j2 = (j + 1) % ni
            yield (b, inner[j2], inner[j])
            j = j2


# ----------------------------------------------------------------------------------------------------------------------
# Solids
# ----------------------------------------------------------------------------------------------------------------------

def box(size: Sequence[float], center: Sequence[float] = (0.0, 0.0, 0.0)) -> Mesh:
    hx, hy, hz = (s / 2.0 for s in size)
    cx, cy, cz = center
    v = np.array([[cx + sx * hx, cy + sy * hy, cz + sz * hz] for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)])
    f = np.array([[0, 2, 3], [0, 3, 1], [4, 5, 7], [4, 7, 6], [0, 1, 5], [0, 5, 4],
                  [2, 6, 7], [2, 7, 3], [0, 4, 6], [0, 6, 2], [1, 3, 7], [1, 7, 5]])
    return Mesh(v, f)


def panel(size: Sequence[float]) -> Mesh:
    """A thin box centred at the origin whose +z face carries the unit texture square (u along +x, v along +y)."""
    m = box(size)
    uv = np.array([[0.0 if x < 0 else 1.0, 0.0 if y < 0 else 1.0] for x, y, _ in m.v])
    return Mesh(m.v, m.f, uv)


def extrude(loop: np.ndarray, z0: float, z1: float) -> Mesh:
    """A prism over a polygon that is star-shaped about its vertex mean (any convex polygon is)."""
    loop = np.asarray(loop, dtype=np.float64)
    if polygon_area(loop) < 0:
        loop = loop[::-1]
    b = _Builder()
    c = loop.mean(axis=0)
    top = [b.vertex(x, y, z1) for x, y in loop]
    bot = [b.vertex(x, y, z0) for x, y in loop]
    ct, cb = b.vertex(c[0], c[1], z1), b.vertex(c[0], c[1], z0)
    n = len(loop)
    for i in range(n):
        j = (i + 1) % n
        b.tri(ct, top[i], top[j])
        b.tri(cb, bot[j], bot[i])
        b.tri(top[i], bot[i], bot[j])
        b.tri(top[i], bot[j], top[j])
    return b.mesh()


def cylinder(radius: float, z0: float, z1: float, n: int = 32, center: Sequence[float] = (0.0, 0.0)) -> Mesh:
    return extrude(circle(radius, n, center), z0, z1)


def revolve(profile: Sequence[Sequence[float]], n: int = 32, warp=None) -> Mesh:
    """A solid of revolution about the z axis.

    `profile` is a polyline of (r, z) points. If it starts and ends on the axis (r = 0) it is closed by the axis;
    otherwise the last point is joined back to the first and the result is a ring. `warp(r, z, theta) -> r` may
    move points radially (a pouring lip, a hexagonal foot); the surface keeps its topology.
    """
    pts = [(float(r), float(z)) for r, z in profile]
    closed_by_axis = pts[0][0] == 0.0 and pts[-1][0] == 0.0
    b = _Builder()
    rings: list[list[int]] = []
    for r, z in pts:
        if r == 0.0:
            rings.append([b.vertex(0.0, 0.0, z)] * n)
        else:
            ring = []
            for k in range(n):
                th = 2.0 * math.pi * k / n
                rr = r if warp is None else warp(r, z, th)
                ring.append(b.vertex(rr * math.cos(th), rr * math.sin(th), z))
            rings.append(ring)
    segments = list(range(len(pts) - 1)) if closed_by_axis else list(range(len(pts)))
    for s in segments:
        lo, hi = rings[s], rings[(s + 1) % len(pts)]
        for k in range(n):
            k2 = (k + 1) % n
            b.tri(lo[k], lo[k2], hi[k2])
            b.tri(lo[k], hi[k2], hi[k])
    m = b.mesh()
    if signed_volume(m) < 0:
        m.f = m.f[:, ::-1].copy()
    return m


@dataclass
class Pocket:
    """A hole cut from the top of a prism cell. `floor_z=None` cuts through. `apex_z` below the floor makes a cone or pyramid."""
    loop: np.ndarray
    floor_z: float | None = None
    apex_z: float | None = None


@dataclass
class Cell:
    """One convex (or star-shaped) piece of a prism's cross-section, optionally with a pocket inside it."""
    loop: np.ndarray
    pocket: Pocket | None = None


def pocket_prism(cells: Iterable[Cell], z0: float, z1: float) -> Mesh:
    """A prism between z0 and z1 whose cross-section is the union of the cells, with the cells' pockets cut from the top.

    Neighbouring cells must share whole edges (same end points), so that the result has no T-junctions.
    """
    b = _Builder()
    top_edges: dict[tuple[int, int], None] = {}
    cells = list(cells)

    def loop_ids(loop: np.ndarray, z: float) -> list[int]:
        return [b.vertex(x, y, z) for x, y in loop]

    for cell in cells:
        loop = np.asarray(cell.loop, dtype=np.float64)
        if polygon_area(loop) < 0:
            loop = loop[::-1]
        top = loop_ids(loop, z1)
        bot = loop_ids(loop, z0)
        for i in range(len(top)):
            top_edges[(top[i], top[(i + 1) % len(top)])] = None
        pts_top = {i: (b.verts[i][0], b.verts[i][1]) for i in top}
        pts_bot = {i: (b.verts[i][0], b.verts[i][1]) for i in bot}
        p = cell.pocket
        if p is None:
            c = loop.mean(axis=0)
            if len(top) == 4:
                b.quad(top[0], top[1], top[2], top[3])
                b.quad(bot[3], bot[2], bot[1], bot[0])
            else:
                ct, cb = b.vertex(c[0], c[1], z1), b.vertex(c[0], c[1], z0)
                for i in range(len(top)):
                    j = (i + 1) % len(top)
                    b.tri(ct, top[i], top[j])
                    b.tri(cb, bot[j], bot[i])
            continue
        ploop = np.asarray(p.loop, dtype=np.float64)
        if polygon_area(ploop) < 0:
            ploop = ploop[::-1]
        pc = ploop.mean(axis=0)
        ptop = loop_ids(ploop, z1)
        pts_top.update({i: (b.verts[i][0], b.verts[i][1]) for i in ptop})
        for t in _ring_triangles(top, ptop, pts_top):
            b.tri(*t)
        through = p.floor_z is None
        zf = z0 if through else p.floor_z
        pbot = loop_ids(ploop, zf)
        m = len(ptop)
        for i in range(m):                                  # pocket wall, facing the pocket axis
            j = (i + 1) % m
            b.tri(ptop[i], pbot[j], pbot[i])
            b.tri(ptop[i], ptop[j], pbot[j])
        if through:
            pts_bot.update({i: (b.verts[i][0], b.verts[i][1]) for i in pbot})
            for a, c2, d in _ring_triangles(bot, pbot, pts_bot):
                b.tri(a, d, c2)
        else:
            za = zf if p.apex_z is None else p.apex_z
            cf = b.vertex(pc[0], pc[1], za)
            for i in range(m):
                b.tri(cf, pbot[i], pbot[(i + 1) % m])
            if len(bot) == 4:
                b.quad(bot[3], bot[2], bot[1], bot[0])
            else:
                c = loop.mean(axis=0)
                cb = b.vertex(c[0], c[1], z0)
                for i in range(len(bot)):
                    b.tri(cb, bot[(i + 1) % len(bot)], bot[i])
    # outer walls: every top edge that no neighbouring cell uses in the opposite direction
    top_to_bot = {}
    for (a, _c) in top_edges:
        top_to_bot[a] = b.vertex(b.verts[a][0], b.verts[a][1], z0)
    for (a, c2) in top_edges:
        if (c2, a) not in top_edges:
            b.tri(a, top_to_bot[a], top_to_bot[c2])
            b.tri(a, top_to_bot[c2], c2)
    return b.mesh()


def grid_cells(xs: Sequence[float], ys: Sequence[float], pockets: dict[tuple[int, int], Pocket]) -> list[Cell]:
    """Rectangular cells between consecutive grid lines; `pockets[(ix, iy)]` puts a pocket in that cell."""
    out = []
    for iy in range(len(ys) - 1):
        for ix in range(len(xs) - 1):
            loop = np.array([[xs[ix], ys[iy]], [xs[ix + 1], ys[iy]], [xs[ix + 1], ys[iy + 1]], [xs[ix], ys[iy + 1]]])
            out.append(Cell(loop, pockets.get((ix, iy))))
    return out


def merge(meshes: Iterable[Mesh]) -> Mesh:
    """Several closed meshes as one mesh (no welding between them): each part stays a closed surface of its own."""
    vs, fs, off = [], [], 0
    for m in meshes:
        vs.append(m.v)
        fs.append(m.f + off)
        off += len(m.v)
    return Mesh(np.concatenate(vs), np.concatenate(fs))


# ----------------------------------------------------------------------------------------------------------------------
# Checks and mass properties
# ----------------------------------------------------------------------------------------------------------------------

def signed_volume(m: Mesh) -> float:
    a, b, c = m.v[m.f[:, 0]], m.v[m.f[:, 1]], m.v[m.f[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def check(m: Mesh, min_area: float = 1e-12) -> dict:
    """Topology and orientation report. `ok` is true for a closed, consistently wound, outward-facing surface."""
    f = m.f
    problems: list[str] = []
    if len(f) == 0:
        return {"ok": False, "problems": ["no triangles"], "volume": 0.0}
    if f.min() < 0 or f.max() >= len(m.v):
        problems.append("face index out of range")
        return {"ok": False, "problems": problems, "volume": 0.0}
    if not np.isfinite(m.v).all():
        problems.append("non-finite vertex")
    used = np.zeros(len(m.v), dtype=bool)
    used[f.reshape(-1)] = True
    if not used.all():
        problems.append(f"{int((~used).sum())} unused vertices")
    a, b, c = m.v[f[:, 0]], m.v[f[:, 1]], m.v[f[:, 2]]
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1)
    if (area <= min_area).any():
        problems.append(f"{int((area <= min_area).sum())} degenerate triangles")
    # directed edges: each must occur once, and its reverse must occur once
    e = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
    n = len(m.v)
    key = e[:, 0] * n + e[:, 1]
    rev = e[:, 1] * n + e[:, 0]
    uniq, counts = np.unique(key, return_counts=True)
    if (counts > 1).any():
        problems.append(f"{int((counts > 1).sum())} directed edges used more than once (inconsistent winding or non-manifold)")
    missing = ~np.isin(rev, uniq)
    if missing.any():
        problems.append(f"{int(missing.sum())} open edges (not watertight)")
    vol = signed_volume(m)
    if vol <= 0:
        problems.append("volume is not positive (inside-out)")
    euler = len(m.v) - len(uniq) // 2 + len(f)
    return {"ok": not problems, "problems": problems, "volume": vol, "area": float(area.sum()), "euler": int(euler),
            "vertices": int(len(m.v)), "triangles": int(len(f))}


def mass_properties(m: Mesh) -> tuple[float, np.ndarray, np.ndarray]:
    """Volume, centroid and the inertia tensor about the centroid for unit density (uniform solid)."""
    a, b, c = m.v[m.f[:, 0]], m.v[m.f[:, 1]], m.v[m.f[:, 2]]
    det = np.einsum("ij,ij->i", a, np.cross(b, c))                     # 6 x signed tetrahedron volume
    vol = det.sum() / 6.0
    com = (det[:, None] * (a + b + c)).sum(axis=0) / (24.0 * vol)
    s = a + b + c
    second = (np.einsum("n,ni,nj->ij", det, a, a) + np.einsum("n,ni,nj->ij", det, b, b)
              + np.einsum("n,ni,nj->ij", det, c, c) + np.einsum("n,ni,nj->ij", det, s, s)) / 120.0
    second -= vol * np.outer(com, com)
    inertia = np.trace(second) * np.eye(3) - second
    return float(vol), com, inertia


# ----------------------------------------------------------------------------------------------------------------------
# Shading normals
# ----------------------------------------------------------------------------------------------------------------------

def shading(m: Mesh, crease_deg: float = 35.0) -> tuple[np.ndarray, np.ndarray]:
    """Normals for drawing: smooth across shallow edges, split at edges sharper than `crease_deg`.

    Returns `(normals, face_normals)`: unit vectors (K, 3), and for every triangle corner the index of its normal
    (M, 3). The vertex indexing of the mesh is left alone, so the surface stays closed.
    """
    f = m.f
    a, b, c = m.v[f[:, 0]], m.v[f[:, 1]], m.v[f[:, 2]]
    fn = np.cross(b - a, c - a)                              # length = 2 x area: area weighting comes for free
    unit = fn / np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-300)
    cos_crease = math.cos(math.radians(crease_deg))
    edge_face: dict[tuple[int, int], int] = {}
    for fi, (i, j, k) in enumerate(f.tolist()):
        edge_face[(i, j)] = fi
        edge_face[(j, k)] = fi
        edge_face[(k, i)] = fi
    parent = list(range(3 * len(f)))                         # one node per triangle corner

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    flist = f.tolist()
    for fi, tri in enumerate(flist):
        for k in range(3):
            v0, v1 = tri[k], tri[(k + 1) % 3]
            gi = edge_face.get((v1, v0))
            if gi is None or gi < fi or float(unit[fi] @ unit[gi]) < cos_crease:
                continue
            g = flist[gi]
            for v in (v0, v1):                               # the two faces share both end points of the edge
                ra, rb = find(3 * fi + tri.index(v)), find(3 * gi + g.index(v))
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
    group: dict[int, int] = {}
    sums: list[np.ndarray] = []
    face_normals = np.zeros((len(f), 3), dtype=np.int64)
    for fi in range(len(f)):
        for k in range(3):
            r = find(3 * fi + k)
            gid = group.get(r)
            if gid is None:
                gid = len(sums)
                group[r] = gid
                sums.append(np.zeros(3))
            sums[gid] += fn[fi]
            face_normals[fi, k] = gid
    normals = np.array(sums)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-300)
    return normals, face_normals


def split_for_drawing(m: Mesh, crease_deg: float = 35.0) -> tuple[Mesh, np.ndarray]:
    """The same surface with vertices duplicated at sharp edges, and one normal per vertex."""
    normals, fnorm = shading(m, crease_deg)
    index: dict[tuple[int, int], int] = {}
    verts, vnorm, uvs = [], [], []
    faces = np.zeros_like(m.f)
    for fi in range(len(m.f)):
        for k in range(3):
            key = (int(m.f[fi, k]), int(fnorm[fi, k]))
            i = index.get(key)
            if i is None:
                i = len(verts)
                index[key] = i
                verts.append(m.v[key[0]])
                vnorm.append(normals[key[1]])
                if m.uv is not None:
                    uvs.append(m.uv[key[0]])
            faces[fi, k] = i
    return Mesh(np.array(verts), faces, np.array(uvs) if m.uv is not None else None), np.array(vnorm)


# ----------------------------------------------------------------------------------------------------------------------
# Files
# ----------------------------------------------------------------------------------------------------------------------

def _num(x: float, digits: int) -> str:
    s = f"{x:.{digits}f}"
    return s.replace("-", "") if float(s) == 0.0 else s


def to_obj(m: Mesh, digits: int = 6, crease_deg: float = 35.0) -> str:
    """Wavefront OBJ text with fixed-point numbers, so the same mesh always gives the same bytes.

    Vertex positions are indexed as in the mesh (a closed surface stays closed); shading normals have their own
    indices and are split at sharp edges.
    """
    normals, fnorm = shading(m, crease_deg)
    lines = ["# Embodied Safety Exam generated mesh"]
    lines += [f"v {_num(x, digits)} {_num(y, digits)} {_num(z, digits)}" for x, y, z in m.v]
    if m.uv is not None:
        lines += [f"vt {_num(u, digits)} {_num(v, digits)}" for u, v in m.uv]
    lines += [f"vn {_num(x, 5)} {_num(y, 5)} {_num(z, 5)}" for x, y, z in normals]
    for tri, nrm in zip(m.f.tolist(), fnorm.tolist()):
        if m.uv is not None:
            lines.append("f " + " ".join(f"{v + 1}/{v + 1}/{k + 1}" for v, k in zip(tri, nrm)))
        else:
            lines.append("f " + " ".join(f"{v + 1}//{k + 1}" for v, k in zip(tri, nrm)))
    return "\n".join(lines) + "\n"


def from_obj(text: str) -> Mesh:
    """Read back an OBJ written by `to_obj` (triangles only)."""
    v, f, uv = [], [], []
    for line in text.splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            v.append([float(p[1]), float(p[2]), float(p[3])])
        elif p[0] == "vt":
            uv.append([float(p[1]), float(p[2])])
        elif p[0] == "f":
            f.append([int(t.split("/")[0]) - 1 for t in p[1:4]])
    return Mesh(np.array(v), np.array(f), np.array(uv) if uv else None)
