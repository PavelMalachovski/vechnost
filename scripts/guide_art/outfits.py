"""What they wear on the free cards and on every pose for him.

Close-fitting garments - the bra and briefs, jeans, trousers - are cut from
the body's own surface: the faces around a region, pushed a few
millimetres out along the rest normals, split sixteen ways, and skinned
with the weights of the body vertices under them, so they move with every
pose as the skin does; whatever a pose still pushes under the skin is put
back on top of it. Where the region ends is decided per vertex by a signed
field (centimetres, positive inside) written in the rest pose from the
body's landmarks, stored on the garment, and read by its material, which
draws the edge at zero. A bra's straps are narrower than that surface is
fine, so they are ribbons of their own, laid along a path on the skin.
Trousers stand off the shin and span the seat, as trousers do, rather
than follow the skin.

What hangs rather than clings - a sheet wrapped round a seated body, a
towel thrown over a shoulder - is cloth, dropped over the posed body and
left to settle.
"""

from __future__ import annotations

import bpy
import numpy as np

from . import makehuman as mh
from . import materials as M
from . import props as P
from .human import Human

ARM_BONES = ("shoulder01", "upperarm01", "upperarm02", "lowerarm01", "lowerarm02", "wrist")
# The hand is part of the arm too: a hand hanging at rest is level with the
# hips, and a garment cut by height alone dressed it in its own fabric.
HAND_BONES = ("metacarpal", "finger")
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
            hand = stem.startswith(HAND_BONES)
            dest = arm if stem in ARM_BONES or hand else leg if stem in LEG_BONES else None
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


def _segment_dist(p, pts):
    """Distance in 3D from each point to a polyline."""
    best = np.full(len(p), 1e9)
    for a, b in zip(pts[:-1], pts[1:], strict=True):
        v = b - a
        t = np.clip(((p - a) @ v) / (v @ v), 0, 1)
        best = np.minimum(best, np.linalg.norm(p - (a + t[:, None] * v), axis=1))
    return best


def _on_skin(f: Fit, p, toward):
    """The point of the rest body nearest `p`, looked for from `toward`
    (so a point meant for the back lands on the back)."""
    d = np.linalg.norm(f.co - p, axis=1) + 0.3 * np.linalg.norm(f.co - toward, axis=1)
    return f.co[np.argmin(d)]


def _skin_path(f: Fit, pts, n=40):
    """A path over the skin through `pts`: split into `n` points, each laid
    on the skin (the tangent plane of its nearest rest vertex), twice over.
    Straight chords between a few points sink under a curved shoulder, and
    a band measured from them vanishes there; snapping to the vertices
    themselves zigzags."""
    from scipy.spatial import cKDTree

    pts = np.asarray(pts, dtype=float)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))])
    t = np.linspace(0.0, s[-1], n)
    path = np.stack([np.interp(t, s, pts[:, k]) for k in range(3)], axis=1)
    tree = cKDTree(f.co)
    for _ in range(2):
        i = tree.query(path, k=4)[1]
        v, nrm = f.co[i].mean(1), f.normals[i].mean(1)
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        path = path - (((path - v) * nrm).sum(1))[:, None] * nrm
        path[1:-1] = (path[:-2] + 2 * path[1:-1] + path[2:]) / 4
    return path


def _half_plane(x, z, a, b):
    """Signed distance to the line a-b in the x-z plane, positive to its left."""
    ex, ez = b[0] - a[0], b[1] - a[1]
    n = np.hypot(ex, ez)
    return ((x - a[0]) * (-ez) + (z - a[1]) * ex) / n


def _cup(f: Fit, side):
    """One triangle of the bralette, in the front view (x, z): the corner at
    the centre, the outer corner, and the tip over the nipple."""
    sgn = 1.0 if side == "l" else -1.0
    n = f.nipples[side]
    ub = min(f.nipples["l"][2], f.nipples["r"][2]) - 7.0  # the underbust line
    return (sgn * 1.0, ub + 1.0), (n[0] + sgn * 8.5, ub + 1.0), (n[0] + sgn * 0.8, n[2] + 7.0)


def bra_field(f: Fit, co, limb):
    """A triangle bralette: two triangles of fabric over the breasts and a
    band round the ribs under them. The straps are ribbons of their own
    (`strap_path`): a centimetre is narrower than this surface is fine."""
    x, y, z = co.T
    out = np.full(len(x), -1e3)
    ub = min(f.nipples["l"][2], f.nipples["r"][2]) - 7.0
    front = f.chest_mid_y - y
    for side, sgn in (("l", 1.0), ("r", -1.0)):
        inner, outer, tip = _cup(f, side)
        # The triangle's three edges, each positive inside. Inner, outer,
        # tip run anticlockwise on the left cup and clockwise on its mirror,
        # so the inside is on the left of each edge there and on the right
        # here.
        e1 = _half_plane(x, z, inner, outer) * sgn
        e2 = _half_plane(x, z, outer, tip) * sgn
        e3 = _half_plane(x, z, tip, inner) * sgn
        out = np.maximum(out, np.minimum.reduce([e1, e2, e3, front + 2.0]))
    # The band under the cups and round the back, a little higher behind.
    zb = ub + 0.3 + 1.8 * _smooth(f.chest_mid_y - 4, f.chest_mid_y + 6, y)
    out = np.maximum(out, 0.9 - np.abs(z - zb))
    return np.where(limb["arm"] > 0.5, -5.0, out)


def strap_path(f: Fit, side):
    """A strap's line on the rest body: from the cup's tip up over the
    shoulder, beside the neck, and down the back to the band."""
    sgn = 1.0 if side == "l" else -1.0
    n, s = f.nipples[side], f.shoulder[side]
    ub = min(f.nipples["l"][2], f.nipples["r"][2]) - 7.0
    tip = _cup(f, side)[2]
    a = _on_skin(f, np.array([tip[0], n[1] - 1.0, tip[1]]), np.array([tip[0], n[1] - 30.0, tip[1]]))
    top = _on_skin(
        f,
        np.array([s[0] - sgn * 6.0, s[1], s[2] + 6.0]),
        np.array([s[0] - sgn * 6.0, s[1], s[2] + 40.0]),
    )
    back = _on_skin(
        f, np.array([n[0], s[1] + 12.0, ub + 2.5]), np.array([n[0], s[1] + 40.0, ub + 2.5])
    )
    mid1 = _on_skin(f, (a + top) / 2, (a + top) / 2 + np.array([0, -20.0, 20.0]))
    mid2 = _on_skin(f, (top + back) / 2, (top + back) / 2 + np.array([0, 20.0, 20.0]))
    return _skin_path(f, [a, mid1, top, mid2, back])


def ribbon(h: Human, fit: Fit, path, material, width=1.1, offset=0.45, name="strap"):
    """A strap: a strip `width` cm wide along `path` (rest body, cm),
    `offset` cm off the skin, skinned like the skin under it."""
    from scipy.sparse import csr_matrix
    from scipy.spatial import cKDTree

    tree = cKDTree(fit.co)
    nrm = fit.normals[tree.query(path, k=4)[1]].mean(1)
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
    tan = np.gradient(path, axis=0)
    side = np.cross(nrm, tan)
    side /= np.linalg.norm(side, axis=1, keepdims=True)
    mid = path + nrm * offset
    co = np.concatenate([mid - side * width / 2, mid + side * width / 2])
    n = len(path)
    me = bpy.data.meshes.new(name)
    me.from_pydata((co / 100.0).tolist(), [], [(k, k + 1, n + k + 1, n + k) for k in range(n - 1)])
    me.update()
    me.shade_smooth()
    # The garment material draws where `cut` is positive: all of a strap.
    me.attributes.new("cut", "FLOAT", "POINT").data.foreach_set(
        "value", np.ones(len(co), dtype=np.float32)
    )
    me.materials.append(material)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    dist, idx = tree.query(co, k=3)
    w = 1.0 / np.maximum(dist, 0.05) ** 2
    w /= w.sum(axis=1, keepdims=True)
    rows = np.repeat(np.arange(len(co)), 3)
    h.bind(
        ob,
        subdiv=1,
        blend=csr_matrix((w.ravel(), (rows, idx.ravel())), shape=(len(co), len(fit.co))),
    )
    _keep_outside(ob, h, offset)
    return ob


def _keep_outside(ob, h: Human, offset, snap="OUTSIDE_SURFACE"):
    """Posed, the skin under a garment is not where the rest pose left it: a
    lowered arm bunches the top of the shoulder, and the body is smoothed
    one level more than its clothes. Whatever of a garment ends up under
    the skin is put back on top of it. `OUTSIDE_SURFACE` lays the whole
    garment on the skin, which is what a close fit wants; `OUTSIDE` moves
    only what went under it, and leaves a looser fit standing off the body."""
    keep = ob.modifiers.new("outside", "SHRINKWRAP")
    keep.target = h.ob
    keep.wrap_method = "NEAREST_SURFACEPOINT"
    keep.wrap_mode = snap
    keep.offset = offset / 100.0 * 0.6


def briefs_field(f: Fit, co, limb, rise=4.5, cheek=6.0):
    x, y, z = co.T
    ax = np.abs(x)
    behind = _smooth(f.hip[1] - 3, f.hip[1] + 4, y)
    top = (f.hip[2] + rise + 0.03 * ax + 1.5 * behind) - z
    slope_front = (f.hip[2] + 3.0 - f.crotch) / 12.5
    slope_back = (f.hip[2] - cheek - f.crotch) / 11.5
    slope = slope_front * (1 - behind) + slope_back * behind
    leg = (z - f.crotch + 1.2) - slope * np.maximum(ax - 3.2, 0)
    out = np.minimum(top, leg)
    return np.where(limb["arm"] > 0.3, -5.0, out)


def jeans_field(f: Fit, co, limb):
    z = co[:, 2]
    top = (f.hip[2] + 6.0) - z
    ankle = z - 9.0
    return np.where(limb["arm"] > 0.3, -5.0, np.minimum(top, ankle))


TROUSERS_RISE = 8.5  # the waist, in cm over the hip joints: a mid rise
TROUSERS_BACK = 4.0  # and this much higher behind, as trousers are cut


def _waist(f: Fit, co):
    """The waistband's top edge at each point, a little higher at the back:
    level all round, it slid down a back that bends over a chair."""
    behind = _smooth(f.hip[1] - 3, f.hip[1] + 6, co[:, 1])
    return f.hip[2] + TROUSERS_RISE + TROUSERS_BACK * behind


def trousers_field(f: Fit, co, limb):
    """Trousers: to a mid-rise waist, and down over the ankle bone."""
    z = co[:, 2]
    top = _waist(f, co) - z
    hem = z - 5.5
    return np.where(limb["arm"] > 0.3, -5.0, np.minimum(top, hem))


def waist_field(f: Fit, co, limb):
    """How far below the waistband's top edge a point is: where a belt goes."""
    return _waist(f, co) - co[:, 2]


def shell(
    h: Human,
    fit: Fit,
    field,
    material,
    offset=0.25,
    margin=2.5,
    name="garment",
    cuts=3,
    bridge=0,
    extra=None,
    snap="OUTSIDE_SURFACE",
):
    """A garment cut from the body: the faces within `margin` cm of the
    field's region, `offset` cm out from the skin, each split into
    (cuts + 1)^2 so that an edge has vertices close to it; every new vertex
    takes its skin weights - and its side of the edge - from the body
    vertices nearest it. `bridge` rounds of `_bridge` let the fabric span
    what cloth spans rather than follow the skin into it. `extra` names
    more fields to store beside `cut`, for the material to read (where a
    belt runs)."""
    import bmesh
    from scipy.sparse import csr_matrix
    from scipy.spatial import cKDTree

    coarse = field(fit.co, fit.limb)
    faces = [f for f, _ in mh.base().faces["body"]]
    keep = [f for f in faces if max(coarse[i] for i in f) > -margin]
    used = sorted({i for f in keep for i in f})
    remap = {v: k for k, v in enumerate(used)}
    bm = bmesh.new()
    verts = [bm.verts.new((fit.co[i] + fit.normals[i] * offset) / 100.0) for i in used]
    for f in keep:
        bm.faces.new([verts[remap[i]] for i in f])
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True, smooth=1.0)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) * 100.0
    # Each vertex as a blend of the three body vertices nearest it at rest.
    dist, idx = cKDTree(fit.co).query(co, k=3)
    w = 1.0 / np.maximum(dist, 0.05) ** 2
    w /= w.sum(axis=1, keepdims=True)
    rows = np.repeat(np.arange(len(co)), 3)
    blend = csr_matrix((w.ravel(), (rows, idx.ravel())), shape=(len(co), len(fit.co)))
    limb = {k: blend @ v for k, v in fit.limb.items()}
    cut = me.attributes.new("cut", "FLOAT", "POINT")
    cut.data.foreach_set("value", np.asarray(field(co, limb), dtype=np.float32))
    for key, more in (extra or {}).items():
        me.attributes.new(key, "FLOAT", "POINT").data.foreach_set(
            "value", np.asarray(more(co, limb), dtype=np.float32)
        )
    if bridge:
        edges = np.zeros(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", edges)
        spanned = _bridge(co, edges.reshape(-1, 2), blend @ fit.normals, bridge)
        me.vertices.foreach_set("co", (spanned / 100.0).ravel())
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    me.materials.append(material)
    h.bind(ob, subdiv=1, blend=blend)
    _keep_outside(ob, h, offset, snap)
    return ob


def _bridge(co, edges, normals, rounds):
    """Cloth spans a hollow instead of sinking into it: each round, every
    vertex moves out along its normal toward the mean of its neighbours,
    and never in. The crease of the groin fills, and a bra's band spans the
    fold under the breasts."""
    from scipy.sparse import coo_matrix

    n = len(co)
    nrm = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)
    i, j = edges[:, 0], edges[:, 1]
    ring = coo_matrix((np.ones(2 * len(i)), (np.r_[i, j], np.r_[j, i])), shape=(n, n)).tocsr()
    deg = np.maximum(np.asarray(ring.sum(axis=1)).ravel(), 1.0)
    for _ in range(rounds):
        out = (((ring @ co) / deg[:, None] - co) * nrm).sum(axis=1)
        co = co + np.maximum(out, 0.0)[:, None] * nrm * 0.5
    return co


LINGERIE = (0.13, 0.018, 0.045)


def lingerie(h: Human, color=LINGERIE):
    fit = Fit(h)
    satin = M.garment("bra", color, kind="satin")
    bra = shell(
        h, fit, lambda co, limb: bra_field(fit, co, limb), satin, offset=0.28, name="bra", bridge=40
    )
    straps = [ribbon(h, fit, strap_path(fit, side), satin, name=f"strap.{side}") for side in "lr"]
    low = shell(
        h,
        fit,
        lambda co, limb: briefs_field(fit, co, limb),
        M.garment("briefs", color, kind="satin"),
        offset=0.22,
        name="briefs",
        bridge=30,
    )
    return [bra, *straps, low]


def jeans(h: Human):
    fit = Fit(h)
    ob = shell(
        h,
        fit,
        lambda co, limb: jeans_field(fit, co, limb),
        M.garment("jeans", (0.06, 0.12, 0.26), kind="denim", band=3.8),
        offset=1.2,
        name="jeans",
        bridge=30,
    )
    # Folds: denim bunches at the knees and the hips.
    tex = bpy.data.textures.new("folds", "CLOUDS")
    tex.noise_scale = 0.035
    d = ob.modifiers.new("folds", "DISPLACE")
    d.texture = tex
    d.texture_coords = "LOCAL"
    d.strength = 0.007
    return [ob]


TROUSERS = (0.026, 0.025, 0.029)  # charcoal


def _ease_legs(ob, fit: Fit, radius=7.2, fade=16.0, soft=1.5):
    """Trouser legs hang straight from the knee: every point below it is
    moved out from its leg's own axis (knee to ankle, carried on below)
    until it is at least `radius` cm from it, the minimum fading away over
    `fade` cm above the knee, where the thigh is wider anyway. A shell that
    follows the skin all the way down reads as leggings."""
    me = ob.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) * 100.0
    out = co.copy()
    for side, mine in (("l", co[:, 0] > 0), ("r", co[:, 0] <= 0)):
        knee = fit.h.landmark(f"joint-{side}-knee") * 100.0
        ankle = fit.h.landmark(f"joint-{side}-ankle") * 100.0
        axis = (knee - ankle) / np.linalg.norm(knee - ankle)
        p = co[mine]
        t = (p - ankle) @ axis
        radial = p - (ankle + np.outer(t, axis))
        r = np.linalg.norm(radial, axis=1)
        want = radius * (1 - _smooth(knee[2], knee[2] + fade, p[:, 2]))
        # A soft maximum, so the ease starts without a crease.
        new = (r + want + np.sqrt((r - want) ** 2 + soft * soft)) / 2 - soft / 2
        new = np.maximum(new, r)
        out[mine] = p + radial / np.maximum(r, 1e-6)[:, None] * (new - r)[:, None]
    me.vertices.foreach_set("co", (out / 100.0).ravel())
    me.update()


def _upper_hull(t, v):
    """The upper convex hull of the points (t, v), as v over t at each t:
    whatever dips below the line between two higher points is lifted to
    it."""
    order = np.argsort(t)
    hull = []
    for k in order:
        while len(hull) >= 2:
            (t1, v1), (t2, v2) = (t[hull[-2]], v[hull[-2]]), (t[hull[-1]], v[hull[-1]])
            if (t2 - t1) * (v[k] - v1) - (v2 - v1) * (t[k] - t1) >= 0:
                hull.pop()
            else:
                break
        hull.append(k)
    return np.interp(t, t[hull], v[hull])


def _ease_seat(ob, fit: Fit, half=9.0, band=1.5, column=1.0):
    """The seat of trousers is one surface over both cheeks and down onto
    the thighs. Near the middle of the back each point is lifted back to
    the cheeks' rear contour at its own height (fully at the middle, not at
    all `half` cm to either side), and then each column of the back from
    the thigh to the waist to the envelope of its own profile, so the
    folds under the cheeks are spanned. A shell that follows the skin
    showed the cleft, down to a dark gap at the crotch."""
    me = ob.data
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) * 100.0  # Blender axes, cm: x left, -y front, z up
    x, y, z = co.T
    behind = y > fit.hip[1]
    seat = behind & (np.abs(x) < half) & (z > fit.crotch - 4.0) & (z < fit.hip[2] + 10.0)
    cheeks = behind & (np.abs(x) > 3.0) & (np.abs(x) < 11.0)
    out = y.copy()
    for i in np.flatnonzero(seat):
        near = cheeks & (np.abs(z - z[i]) < band)
        if not near.any():
            continue
        # Fading in above the crotch, or the lifted seat ends in a ledge
        # over it and its shadow reads as a slit.
        w = (1.0 - _smooth(0.0, half, abs(x[i]))) * _smooth(
            fit.crotch - 4.0, fit.crotch + 8.0, z[i]
        )
        out[i] = max(y[i], y[i] + (y[near].max() - y[i]) * w)
    back = behind & (np.abs(x) < 17.0) & (z > fit.crotch - 16.0) & (z < fit.hip[2] + 10.0)
    for xc in np.arange(-17.0, 17.0 + column, column):
        col = np.flatnonzero(back & (np.abs(x - xc) < column / 2))
        if len(col) >= 3:
            out[col] = np.maximum(out[col], _upper_hull(z[col], out[col]))
    co[:, 1] = out
    me.vertices.foreach_set("co", (co / 100.0).ravel())
    me.update()


def trousers(h: Human, color=TROUSERS):
    """Dark wool trousers and a black leather belt: what every pose for him
    wears, so that a pose shows a back, shoulders and arms and nothing a
    reader has to look away from."""
    fit = Fit(h)
    m = M.garment(
        "trousers",
        color,
        kind="wool",
        band=3.4,
        band_color=(0.010, 0.008, 0.007),
        band_attr="waist",
        band_rough=0.55,
    )
    ob = shell(
        h,
        fit,
        lambda co, limb: trousers_field(fit, co, limb),
        m,
        offset=1.4,
        name="trousers",
        bridge=40,
        extra={"waist": lambda co, limb: waist_field(fit, co, limb)},
        snap="OUTSIDE",
    )
    _ease_legs(ob, fit)
    _ease_seat(ob, fit)
    # A crease at the knee and the hip, softer than denim's: deeper, a hard
    # lamp raking across the front drew them as stains.
    tex = bpy.data.textures.new("trouser_folds", "CLOUDS")
    tex.noise_scale = 0.05
    d = ob.modifiers.new("folds", "DISPLACE")
    d.texture = tex
    d.texture_coords = "LOCAL"
    d.strength = 0.004
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


def shoulder_towel(h: Human, side="l", colliders=(), size=(28.0, 96.0)):
    """A bath towel thrown over one shoulder: laid level across the top of
    it, between the neck and the arm, its length running front to back,
    and dropped, so one end hangs down the chest and over the arm and the
    other down the back."""
    from mathutils import Matrix, Vector

    s = "L" if side == "l" else "R"
    shoulder = h.bone_now(f"upperarm01.{s}")
    neck = h.bone_now("neck01")
    other = h.bone_now(f"upperarm01.{'R' if s == 'L' else 'L'}")
    top = shoulder * 0.55 + neck * 0.45
    # Scene centimetres (x right, y up, z toward the camera), as props take.
    centre = (top[0] * 100.0, top[2] * 100.0 + 9.0, -top[1] * 100.0)
    ob = P.cloth_sheet(centre, size, M.terry(), res=1.6, noise=0.5, seed=5, name="towel")
    # Turn it so its width lies along the shoulders, whichever way he faces.
    across = other - shoulder
    turn = float(np.arctan2(across[1], across[0]))
    pivot = Vector(P.V(centre))
    ob.data.transform(
        Matrix.Translation(pivot) @ Matrix.Rotation(turn, 4, "Z") @ Matrix.Translation(-pivot)
    )
    ob.data.update()
    P.drape([ob], [h.ob, *colliders], frames=70, mass=0.4, bend=0.5, thickness=1.2)
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
