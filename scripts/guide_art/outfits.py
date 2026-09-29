"""What they wear on the free cards and a few paid ones.

Close-fitting garments - the bra and briefs, boxers, jeans - are cut from
the body's own surface: the faces around a region, pushed a few
millimetres out along the rest normals and skinned with the body's own
weights, so they move with every pose exactly as the skin under them does.
Where the region ends is decided per vertex by a signed field (centimetres,
positive inside) written in the rest pose from the body's landmarks, stored
on the garment, and read by its material, which draws the edge at zero -
a smooth line, however coarse the mesh under it.

What hangs rather than clings - a towel round the hips, a sheet wrapped
round a seated body - is cloth, dropped over the posed body and left to
settle.
"""

from __future__ import annotations

import bpy
import numpy as np

from . import makehuman as mh
from . import materials as M
from . import props as P
from .human import Human

ARM_BONES = ("shoulder01", "upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist")
LEG_BONES = ("upperleg01", "upperleg02", "lowerleg01", "lowerleg02", "foot")


def _smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


class Fit:
    """The rest body in centimetres, and the landmarks a garment is cut to."""

    def __init__(self, h: Human):
        self.h = h
        me = h.ob.data
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        self.co = co.reshape(-1, 3) * 100.0  # Blender axes, cm: x left, -y front, z up
        self.normals = h.rest_normals()
        self.limb = self._limb_share()

        def lm(group):
            return h.landmark(group) * 100.0

        self.hip = (lm("joint-l-upper-leg") + lm("joint-r-upper-leg")) / 2
        self.shoulder = {"l": lm("joint-l-shoulder"), "r": lm("joint-r-shoulder")}
        self.chest_mid_y = lm("joint-spine-1")[1]
        x, z = self.co[:, 0], self.co[:, 2]
        mid = (np.abs(x) < 0.8) & (z > self.hip[2] - 25) & (z < self.hip[2])
        self.crotch = float(z[mid].min())
        self.nipples = self._nipples()

    def _limb_share(self):
        """How much of each vertex belongs to an arm or a leg (0-1), from the
        skeleton's weights: a garment edge never runs down a limb by mistake."""
        n = len(self.co)
        arm, leg = np.zeros(n), np.zeros(n)
        for bone, pairs in mh.weights("default").items():
            stem = bone.split(".")[0]
            dest = arm if stem in ARM_BONES else leg if stem in LEG_BONES else None
            if dest is None:
                continue
            for i, w in pairs:
                if i < n:
                    dest[i] += w
        return {"arm": arm, "leg": leg}

    def _nipples(self):
        from PIL import Image

        me = self.h.ob.data
        img = np.asarray(Image.open(mh.texture("mpfb_aureolae.jpg")).convert("L"), dtype=float)
        uv = np.zeros(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers[0].data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        vidx = np.zeros(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", vidx)
        h, w = img.shape
        px = np.clip((uv[:, 0] * (w - 1)).round().astype(int), 0, w - 1)
        py = np.clip(((1 - uv[:, 1]) * (h - 1)).round().astype(int), 0, h - 1)
        hit = np.unique(vidx[img[py, px] > 76])
        pts = self.co[hit]
        return {"l": pts[pts[:, 0] > 0].mean(0), "r": pts[pts[:, 0] < 0].mean(0)}


def _polyline_dist(px, pz, pts):
    """Distance in the x-z plane from each point to a polyline."""
    best = np.full(len(px), 1e9)
    for (ax, az), (bx, bz) in zip(pts[:-1], pts[1:], strict=True):
        vx, vz = bx - ax, bz - az
        t = np.clip(((px - ax) * vx + (pz - az) * vz) / (vx * vx + vz * vz), 0, 1)
        best = np.minimum(best, np.hypot(px - (ax + vx * t), pz - (az + vz * t)))
    return best


def bra_field(f: Fit):
    x, y, z = f.co.T
    out = np.full(len(x), -1e3)
    ub = min(f.nipples["l"][2], f.nipples["r"][2]) - 7.0  # the underbust line
    for side, sgn in (("l", 1.0), ("r", -1.0)):
        n = f.nipples[side]
        dx, dz = (x - n[0]) * sgn, z - n[2]
        rz = np.where(dz < 0, 7.8, 9.0)
        ell = (1.0 - np.sqrt((dx / 9.0) ** 2 + (dz / rz) ** 2)) * 8.0
        top = (n[2] + 5.2 - 0.12 * dx) - z  # a balconette's straight top
        inner = x * sgn - 0.4  # the cups nearly meet in the middle
        front = f.chest_mid_y - y
        out = np.maximum(out, np.minimum.reduce([ell, top, inner, front]))
        # The strap: from the cup's outer top over the shoulder, down the back.
        s = f.shoulder[side]
        up = (n[0] + sgn * 2.5, n[2] + 3.5)
        over = (s[0] - sgn * 5.5, s[2] + 3.0)
        back = (n[0] + sgn * 0.5, ub + 2.5)
        d_front = _polyline_dist(x, z, [up, over])
        d_back = _polyline_dist(x, z, [over, back])
        d = np.where(y < f.chest_mid_y, d_front, d_back)
        out = np.maximum(out, 0.65 - d)
    # The band under the cups and round the back, a little higher behind,
    # and the gore joining the cups in front.
    zb = ub + 1.8 * _smooth(f.chest_mid_y - 4, f.chest_mid_y + 6, y)
    out = np.maximum(out, 1.0 - np.abs(z - zb))
    gore = np.minimum(1.2 - np.abs(x), np.minimum(z - ub, (ub + 5.0) - z))
    out = np.maximum(out, np.where(y < f.chest_mid_y, gore, -5.0))
    return np.where(f.limb["arm"] > 0.5, -5.0, out)


def briefs_field(f: Fit, rise=4.5, cheek=6.0):
    x, y, z = f.co.T
    ax = np.abs(x)
    behind = _smooth(f.hip[1] - 3, f.hip[1] + 4, y)
    top = (f.hip[2] + rise + 0.03 * ax + 1.5 * behind) - z
    slope_front = (f.hip[2] + 3.0 - f.crotch) / 12.5
    slope_back = (f.hip[2] - cheek - f.crotch) / 11.5
    slope = slope_front * (1 - behind) + slope_back * behind
    leg = (z - f.crotch + 1.2) - slope * np.maximum(ax - 3.2, 0)
    out = np.minimum(top, leg)
    return np.where(f.limb["arm"] > 0.3, -5.0, out)


def boxers_field(f: Fit):
    x, y, z = f.co.T
    top = (f.hip[2] + 5.0) - z
    bottom = z - (f.hip[2] - 21.0)
    return np.where(f.limb["arm"] > 0.3, -5.0, np.minimum(top, bottom))


def jeans_field(f: Fit):
    x, y, z = f.co.T
    top = (f.hip[2] + 6.0) - z
    ankle = z - 9.0
    return np.where(f.limb["arm"] > 0.3, -5.0, np.minimum(top, ankle))


def shell(h: Human, fit: Fit, field, material, offset=0.25, margin=2.5, name="garment", subdiv=2):
    """A garment cut from the body: faces within `margin` cm of the field's
    region, `offset` cm out from the skin, skinned like it."""
    faces = [f for f, _ in mh.base().faces["body"]]
    keep = [f for f in faces if max(field[i] for i in f) > -margin]
    used = sorted({i for f in keep for i in f})
    remap = {v: k for k, v in enumerate(used)}
    co = (fit.co[used] + fit.normals[used] * offset) / 100.0
    me = bpy.data.meshes.new(name)
    me.from_pydata(co.tolist(), [], [[remap[i] for i in f] for f in keep])
    me.update()
    me.shade_smooth()
    idx = me.attributes.new("mh_index", "INT", "POINT")
    idx.data.foreach_set("value", np.asarray(used, dtype=np.int32))
    cut = me.attributes.new("cut", "FLOAT", "POINT")
    cut.data.foreach_set("value", np.asarray(field[used], dtype=np.float32))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(material)
    h.bind(ob, subdiv)
    return ob


LINGERIE = (0.13, 0.018, 0.045)


def lingerie(h: Human, color=LINGERIE):
    fit = Fit(h)
    bra = shell(
        h, fit, bra_field(fit), M.garment("bra", color, kind="satin"), offset=0.28, name="bra"
    )
    low = shell(
        h,
        fit,
        briefs_field(fit),
        M.garment("briefs", color, kind="satin"),
        offset=0.22,
        name="briefs",
    )
    return [bra, low]


def boxers(h: Human):
    fit = Fit(h)
    m = M.garment(
        "boxers", (0.025, 0.025, 0.03), kind="cotton", band=3.2, band_color=(0.012, 0.012, 0.014)
    )
    return [shell(h, fit, boxers_field(fit), m, offset=0.5, name="boxers")]


def jeans(h: Human):
    fit = Fit(h)
    ob = shell(
        h,
        fit,
        jeans_field(fit),
        M.garment("jeans", (0.07, 0.11, 0.19), kind="denim", band=3.8),
        offset=1.2,
        name="jeans",
    )
    # Folds: denim bunches at the knees and the hips.
    tex = bpy.data.textures.new("folds", "CLOUDS")
    tex.noise_scale = 0.035
    d = ob.modifiers.new("folds", "DISPLACE")
    d.texture = tex
    d.texture_coords = "LOCAL"
    d.strength = 0.007
    return [ob]


def _posed_points(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    ev.to_mesh_clear()
    mw = np.array(ob.matrix_world)
    return co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]


def body_wrap(
    h: Human,
    top,
    bottom,
    material,
    colliders=(),
    name="wrap",
    frames=60,
    margin=0.035,
    shrink=0.12,
    cols=96,
    rows=44,
    flare=1.0,
):
    """Cloth wrapped round the posed body: a closed ring whose top edge is
    held at `top(angle)` (Blender z, the angle round the body's vertical
    axis, 0 toward its front) and which hangs down to `bottom` - shaped, row
    by row, to clear the body at that height, so it starts touching nothing -
    then let fall, shrinking a little so it hugs what it falls on."""
    bpy.context.view_layer.update()
    pts = _posed_points(h.ob)
    sl, sr = h.bone_now("upperarm01.L"), h.bone_now("upperarm01.R")
    right = (sr - sl) / np.linalg.norm(sr - sl)
    fwd = np.cross([0.0, 0.0, 1.0], right)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 0.0, 1.0])
    hips = (h.bone_now("upperleg01.L") + h.bone_now("upperleg01.R")) / 2
    th = np.linspace(0, 2 * np.pi, cols, endpoint=False)
    z_top = np.array([top(t) for t in th])
    rows_z = [z_top + (bottom - z_top) * k / rows for k in range(rows + 1)]
    rel = pts[:, :2] - hips[:2]
    ang = np.arctan2(rel @ right[:2], rel @ fwd[:2]) % (2 * np.pi)
    rad = np.linalg.norm(rel, axis=1)
    prev = np.full(cols, 0.12)
    verts = []
    for k, zs in enumerate(rows_z):
        r = prev.copy()
        for i, t in enumerate(th):
            near = np.abs(pts[:, 2] - zs[i]) < 0.05
            d = np.abs((ang[near] - t + np.pi) % (2 * np.pi) - np.pi) < np.radians(12)
            if d.any():
                r[i] = max(rad[near][d].max() + margin, 0.1)
        r = (np.roll(r, 1) + r + np.roll(r, -1)) / 3  # a smooth ring
        if k:
            r = np.maximum(r, prev * 0.97)  # never pinched in below
        r *= 1 + (flare - 1) * (k / rows) ** 2
        prev = r
        for i, t in enumerate(th):
            c = hips[:2] + (fwd[:2] * np.cos(t) + right[:2] * np.sin(t)) * r[i]
            verts.append((c[0], c[1], zs[i]))
    faces = [(k * cols + i, k * cols + (i + 1) % cols, (k + 1) * cols + (i + 1) % cols, (k + 1) * cols + i)
             for k in range(rows) for i in range(cols)]  # fmt: skip
    ob = P.mesh_object(name, verts, faces, material)
    ob.vertex_groups.new(name="top").add(list(range(cols)), 1.0, "REPLACE")
    P.drape(
        [ob],
        [h.ob, *colliders],
        frames=frames,
        mass=0.35,
        bend=0.3,
        thickness=0.6,
        pin="top",
        shrink=shrink,
    )
    return ob, fwd, right


def towel(h: Human, colliders=()):
    """A bath towel round the hips, falling over the thighs."""
    waist = float(((h.bone_now("upperleg01.L") + h.bone_now("upperleg01.R")) / 2)[2]) + 0.09
    ob, _f, _r = body_wrap(
        h, lambda t: waist - 0.015 * np.cos(t), waist - 0.5, M.terry(), colliders,
        name="towel", shrink=0.15, flare=1.05,
    )  # fmt: skip
    ob.modifiers["thick"].thickness = 0.012
    return [ob]


def wrapped_sheet(h: Human, bare="r", colliders=()):
    """A sheet wrapped round a body sitting on the floor, arms and hugged
    knees and all, over one shoulder and under the other, pooling on the
    floor; the other shoulder stays out."""
    sl, sr = h.bone_now("upperarm01.L"), h.bone_now("upperarm01.R")
    covered = sl if bare == "r" else sr
    hi = float(covered[2]) + 0.13
    lo = float(h.bone_now("spine01")[2]) - 0.06
    side = 1.0 if bare == "l" else -1.0  # the covered side, along the body's right

    def top(t):
        w = (1 + side * np.sin(t)) / 2  # 1 on the covered side, 0 on the bare
        return lo + (hi - lo) * w

    cloth = M.fabric("sheet", (0.70, 0.67, 0.63), 0.6, 0.9, 1000.0, 0.08)
    ob, _f, _r = body_wrap(
        h, top, -0.06, cloth, colliders, name="sheet", shrink=0.1, flare=1.15, frames=70
    )
    return [ob]
