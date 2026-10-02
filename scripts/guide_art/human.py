"""A MakeHuman body in Blender: the morphed mesh with its UVs, the default
skeleton bound by MakeHuman's own weights, the eyes, and what grows on the
head - hair, brows, lashes - grown after the pose, so it falls the way the
pose makes it fall.

The pictures imply nudity and show no anatomy: the nipples are relaxed
into the skin around them before anything else happens (`_soften`), and
the skin carries no colour of its own there.
"""

from __future__ import annotations

import bpy
import numpy as np
from mathutils import Matrix, Vector
from PIL import Image

from . import hair as H
from . import makehuman as mh
from . import materials as M

RIG = "default"


class Human:
    def __init__(self, shape: mh.Shape, name="body", skin=None, iris=None):
        self.name = name
        b = mh.base()
        self.co_mh = mh.morph(shape)
        body = b.groups["body"]
        co = mh.to_blender(self.co_mh)
        # Stand the figure on z = 0.
        self.lift = float(-co[body, 2].min())
        co[:, 2] += self.lift
        self.co = co
        self.n_body = int(body.max()) + 1
        self.arm = self._armature()
        self.ob = self._mesh(skin)
        self.eyes = self._eyes(iris)
        self._bind()

    # --- construction -------------------------------------------------
    def _mesh(self, skin):
        b = mh.base()
        faces = b.faces["body"]
        me = bpy.data.meshes.new(self.name)
        me.from_pydata(self.co[: self.n_body].tolist(), [], [f for f, _ in faces])
        uvl = me.uv_layers.new(name="UVMap")
        uvs = [b.uv[i] for _f, t in faces for i in t]
        uvl.data.foreach_set("uv", np.asarray(uvs, dtype=np.float32).ravel())
        me.update()
        me.shade_smooth()
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        if skin is not None:
            me.materials.append(skin)
        self._soften(ob, "mpfb_aureolae.jpg", radius=0.02)
        # The rest shape, kept for anything cut to fit it (a garment).
        ob.add_rest_position_attribute = True
        return ob

    def _soften(self, ob, mask, radius=0.02, support=0.035):
        """Lay a textured patch flat into the skin round it: on each side of
        the body, everything within `radius` of the middle of the mask is put
        on the smooth surface (a quadric) fitted to the skin between `radius`
        and `support` from it, and blended into it toward `support`. Drawing
        each vertex toward its neighbours left a nipple's dense rings a
        couple of millimetres proud of the breast, and a bra printed them."""
        img = np.asarray(Image.open(mh.texture(mask)).convert("L"), dtype=float) / 255.0
        h, w = img.shape
        me = ob.data
        uv = np.zeros(len(me.loops) * 2, dtype=np.float32)
        me.uv_layers[0].data.foreach_get("uv", uv)
        uv = uv.reshape(-1, 2)
        vidx = np.zeros(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", vidx)
        px = np.clip((uv[:, 0] * (w - 1)).round().astype(int), 0, w - 1)
        py = np.clip(((1 - uv[:, 1]) * (h - 1)).round().astype(int), 0, h - 1)
        hit = np.unique(vidx[img[py, px] > 0.3])
        if not len(hit):
            return
        co = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)

        def quad(u, v):
            return np.stack([u * u, u * v, v * v, u, v, np.ones_like(u)], axis=1)

        for side in (co[hit, 0] > 0, co[hit, 0] < 0):
            if not side.any():
                continue
            d = np.linalg.norm(co - co[hit[side]].mean(axis=0), axis=1)
            ring = co[(d > radius) & (d < support)]
            centre = ring.mean(axis=0)
            U, V, N = np.linalg.svd(ring - centre)[2]
            coef = np.linalg.lstsq(
                quad((ring - centre) @ U, (ring - centre) @ V), (ring - centre) @ N, rcond=None
            )[0]
            near = np.flatnonzero(d < support)
            q = co[near] - centre
            u, v, height = q @ U, q @ V, q @ N
            t = np.clip((support - d[near]) / (support - radius), 0.0, 1.0)
            height += (quad(u, v) @ coef - height) * t * t * (3 - 2 * t)
            co[near] = centre + np.outer(u, U) + np.outer(v, V) + np.outer(height, N)
        me.vertices.foreach_set("co", co.ravel())
        me.update()

    def _eyes(self, iris):
        b = mh.base()
        obs = []
        for side in "lr":
            faces = b.faces[f"helper-{side}-eye"]
            used = sorted({i for f, _ in faces for i in f})
            remap = {v: k for k, v in enumerate(used)}
            me = bpy.data.meshes.new(f"eye_{side}")
            me.from_pydata(self.co[used].tolist(), [], [[remap[i] for i in f] for f, _ in faces])
            me.update()
            me.shade_smooth()
            ob = bpy.data.objects.new(f"eye_{side}", me)
            bpy.context.scene.collection.objects.link(ob)
            centre = tuple(self.co[used].mean(axis=0))
            me.materials.append(M.eye(centre, iris=iris or (0.10, 0.055, 0.03), name=f"eye_{side}"))
            sd = ob.modifiers.new("subdiv", "SUBSURF")
            sd.levels = sd.render_levels = 2
            obs.append(ob)
        return obs

    def _armature(self):
        data = bpy.data.armatures.new(self.name + "_rig")
        arm = bpy.data.objects.new(self.name + "_rig", data)
        bpy.context.scene.collection.objects.link(arm)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode="EDIT")
        spec = mh.rig(RIG)
        lift = Vector((0, 0, self.lift))
        for name, bspec in spec.items():
            eb = data.edit_bones.new(name)
            eb.head = Vector(mh.to_blender(mh.joint(self.co_mh, bspec["head"]))) + lift
            eb.tail = Vector(mh.to_blender(mh.joint(self.co_mh, bspec["tail"]))) + lift
            eb.roll = bspec["roll"]
        for name, bspec in spec.items():
            if bspec["parent"]:
                data.edit_bones[name].parent = data.edit_bones[bspec["parent"]]
        bpy.ops.object.mode_set(mode="OBJECT")
        arm.hide_render = True
        return arm

    def weights(self):
        """MakeHuman's skin weights as a matrix: body vertex by bone."""
        from scipy.sparse import csr_matrix

        names = list(mh.weights(RIG))
        rows, cols, vals = [], [], []
        for b, name in enumerate(names):
            for i, w in mh.weights(RIG)[name]:
                if i < self.n_body:
                    rows.append(i)
                    cols.append(b)
                    vals.append(w)
        return names, csr_matrix((vals, (rows, cols)), shape=(self.n_body, len(names)))

    def bind(self, ob, subdiv=2, blend=None):
        """Skin a mesh to the skeleton with MakeHuman's weights: the body
        itself (vertex for vertex), or anything made from it - a garment -
        whose vertices blend the body's by `blend` (a sparse matrix, one row
        per vertex of `ob`, one column per body vertex)."""
        names, W = self.weights()
        if blend is not None:
            W = blend @ W
        W = W.tocsc()
        for b, name in enumerate(names):
            col = W.getcol(b)
            if not col.nnz:
                continue
            vg = ob.vertex_groups.new(name=name)
            for k, w in zip(col.indices, col.data, strict=True):
                if w > 1e-4:
                    vg.add([int(k)], float(w), "REPLACE")
        mod = ob.modifiers.new("rig", "ARMATURE")
        mod.object = self.arm
        # Linear blend: on this skeleton it keeps a raised arm's shoulder in
        # shape, where volume preservation balloons the armpit.
        mod.use_deform_preserve_volume = False
        if subdiv:
            sd = ob.modifiers.new("subdiv", "SUBSURF")
            sd.levels = 1
            sd.render_levels = subdiv
        ob.parent = self.arm

    def _bind(self):
        self.bind(self.ob)
        bone = self.arm.data.bones["head"]
        for eye in self.eyes:
            eye.parent = self.arm
            eye.parent_type = "BONE"
            eye.parent_bone = "head"
            # Keep the eye where it is: undo the bone's own offset.
            eye.matrix_parent_inverse = (
                self.arm.matrix_world
                @ Matrix.Translation(bone.tail_local)
                @ bone.matrix_local.to_3x3().to_4x4()
            ).inverted()

    # --- where things are ---------------------------------------------
    def rest_normals(self):
        me = self.ob.data
        n = np.zeros(len(me.vertices) * 3)
        me.vertices.foreach_get("normal", n)
        return n.reshape(-1, 3)

    def landmark(self, group):
        """A joint of the rest body (Blender metres): the mean of its cube."""
        return mh.to_blender(self.co_mh[mh.base().groups[group]].mean(0)) + np.array(
            [0, 0, self.lift]
        )

    def bone_now(self, name, end="head") -> np.ndarray:
        bpy.context.view_layer.update()
        pb = self.arm.pose.bones[name]
        p = pb.head if end == "head" else pb.tail
        return np.array(self.arm.matrix_world @ p)


# --- what grows on it -----------------------------------------------------


def _sample_faces(verts, faces, count, rng):
    """Points spread evenly by area over polygons (fanned into triangles),
    with each point's face normal."""
    tris = np.asarray([(f[0], f[k], f[k + 1]) for f in faces for k in range(1, len(f) - 1)])
    a, b, c = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    cross = np.cross(b - a, c - a)
    area = np.linalg.norm(cross, axis=1)
    pick = rng.choice(len(tris), size=count, p=area / area.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    pts = a[pick] + (b[pick] - a[pick]) * u[:, None] + (c[pick] - a[pick]) * v[:, None]
    return pts, cross[pick] / np.maximum(area[pick, None], 1e-12)


def _head_matrix(h: Human) -> Matrix:
    """Rest-to-posed transform of everything riding on the head bone."""
    bpy.context.view_layer.update()
    bone = h.arm.data.bones["head"]
    pb = h.arm.pose.bones["head"]
    return h.arm.matrix_world @ pb.matrix @ bone.matrix_local.inverted()


def _posed(Mx: Matrix, pts):
    R = np.array(Mx.to_3x3())
    return pts @ R.T + np.array(Mx.translation)


def _helper(h: Human, group):
    faces = [f for f, _ in mh.base().faces[group]]
    used = sorted({i for f in faces for i in f})
    remap = {v: k for k, v in enumerate(used)}
    return h.co[used], [[remap[i] for i in f] for f in faces]


def head_frame(h: Human):
    Mx = _head_matrix(h)
    bone = h.arm.data.bones["head"]
    centre = np.array(bone.head_local) * 0.35 + np.array(bone.tail_local) * 0.65
    centre[1] += 0.01
    R = np.array(Mx.to_3x3())
    head = H.Head(
        _posed(Mx, centre[None])[0], R @ np.array([0, 0, 1.0]), R @ np.array([0, -1.0, 0])
    )
    return head, Mx


def _uv_mask_per_vertex(me, mask, threshold=0.3):
    """Which vertices of the body fall inside one of MakeHuman's UV masks."""
    img = np.asarray(Image.open(mh.texture(mask)).convert("L"), dtype=float) / 255.0
    h, w = img.shape
    uv = np.zeros(len(me.loops) * 2, dtype=np.float32)
    me.uv_layers[0].data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    vidx = np.zeros(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vidx)
    px = np.clip((uv[:, 0] * (w - 1)).round().astype(int), 0, w - 1)
    py = np.clip(((1 - uv[:, 1]) * (h - 1)).round().astype(int), 0, h - 1)
    inside = np.zeros(len(me.vertices), dtype=bool)
    inside[vidx[img[py, px] > threshold]] = True
    return inside


# Where hair starts, in centimetres above the eyes, going round the head
# from the middle of the forehead (0 degrees) to the nape (180).
HAIRLINE = (
    (0, 6.5),
    (35, 5.8),
    (62, 3.5),
    (80, 1.0),
    (95, 2.5),
    (115, -1.5),
    (150, -6.0),
    (180, -7.5),
)


def scalp(h: Human):
    """The scalp: the skin the head bone carries alone, above a hairline
    drawn round the head from the eyes - high over the forehead, down in
    front of the ears, up over them, low at the nape - less the ears.
    Faces as vertex index lists into the body."""
    names, W = h.weights()
    head_w = np.asarray(W.getcol(names.index("head")).todense()).ravel()
    me = h.ob.data
    ears = _uv_mask_per_vertex(me, "mpfb_ears.jpg", 0.2)
    co = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) * 100.0
    eyes = (h.landmark("joint-l-eye") + h.landmark("joint-r-eye")) / 2 * 100.0
    axis = eyes + np.array([0.0, 8.5, 0.0])  # the head's vertical axis, behind the eyes
    rel = co - axis
    phi = np.degrees(np.abs(np.arctan2(rel[:, 0], -rel[:, 1])))
    deg, cm = zip(*HAIRLINE, strict=True)
    line = eyes[2] + np.interp(phi, deg, cm)
    ok = (head_w > 0.9) & ~ears & (co[:, 2] > line)
    polys = [tuple(p.vertices) for p in me.polygons if all(ok[i] for i in p.vertices)]
    return polys, ok


def grow_hair(
    h: Human,
    style,
    colliders,
    material,
    rng=None,
    grip=None,
    guides=600,
    strands=60000,
    length=0.56,
):
    """Strands from the scalp, grown in a style: long and loose, fanned out
    round a head lying down, hanging from a head bowed low, tied up in a
    bun, held up in the hands at `grip`, or short (and wet, for him out of
    the bath)."""
    rng = rng or np.random.default_rng(7)
    head, Mx = head_frame(h)
    polys, _ok = scalp(h)
    me = h.ob.data
    rest = np.zeros(len(me.vertices) * 3)
    me.vertices.foreach_get("co", rest)
    skin = _posed(Mx, rest.reshape(-1, 3))
    trees = H.colliders(colliders)
    head_tree = trees[0]
    short = style in ("short", "wet")
    wave = (0.004, 0.006, 0.07, 0.05)

    def roots(count):
        """Roots spread evenly over the scalp; a short cut stops a finger
        higher over the temples and the nape than long hair does."""
        out_r, out_n, need = [], [], count
        while need > 0:
            r, n = _sample_faces(skin, polys, need * 2, rng)
            n[(n * (r - head.c)).sum(1) < 0] *= -1
            up = (r - head.c) @ head.up
            keep = up > (-0.05 if short else -0.075)
            r, n = r[keep][:need], n[keep][:need]
            out_r.append(r)
            out_n.append(n)
            need -= len(r)
        return np.concatenate(out_r), np.concatenate(out_n)

    groots, gnormals = roots(guides)
    if style == "long":
        L = length * (0.85 + 0.3 * rng.random(guides))
        # Behind the shoulders: the chest's own backward, not the head's.
        bone = h.arm.pose.bones["spine01"]
        turn = (
            h.arm.matrix_world.to_3x3()
            @ bone.matrix.to_3x3()
            @ bone.bone.matrix_local.to_3x3().inverted()
        )
        back = np.array(turn @ Vector((0.0, 1.0, 0.0)))  # rest back is +y
        back = back - (back @ H.G) * H.G
        back = 0.45 * back / max(np.linalg.norm(back), 1e-6)
        g = H.grow(head_tree, trees, groots, gnormals, H.flow_back(head, part=0.004), L, points=30,
                   offset=(0.002, 0.012), inertia=0.75, leave=0.25, rng=rng, drift=back)  # fmt: skip
        clump, frizz, radii = 0.45, 0.0005, (0.00007, 0.00003)
    elif style == "lying":
        # A head on a pillow: the hair goes over the crown and fans out
        # round it on the bed, in soft locks.
        L = 0.38 * (0.8 + 0.3 * rng.random(guides))
        crown = head.c + head.up * 0.5
        g = H.grow(head_tree, trees, groots, gnormals, H.flow_to(crown), L, points=30,
                   offset=(0.002, 0.010), inertia=0.6, leave=2.0, rng=rng)  # fmt: skip
        # Loose, wide waves and little clumping: spread on a sheet, locks
        # drawn to a point read as spikes round the head.
        clump, frizz, radii = 0.25, 0.0008, (0.00008, 0.00004)
        wave = (0.010, 0.012, 0.10, 0.08)
    elif style == "down":
        # A head bowed low over the knees: combed back, the hair wound round
        # a skull whose back faces the ceiling and read as a man's crop. It
        # leaves the scalp at once and hangs instead, a curtain from the
        # crown past the face and down over the arms.
        # Shoulder length, so it ends over the arms rather than standing on
        # the floor like a column, and fanning a little out from the head.
        L = 0.4 * (0.85 + 0.3 * rng.random(guides))

        def fan(root):
            out = root - head.c
            out = out - (out @ H.G) * H.G
            return 0.3 * out / max(np.linalg.norm(out), 1e-6)

        g = H.grow(head_tree, trees, groots, gnormals, lambda p, n: H.G, L, points=30,
                   offset=(0.002, 0.010), inertia=0.6, leave=2.0, rng=rng, drift=fan)  # fmt: skip
        clump, frizz, radii = 0.6, 0.0007, (0.00007, 0.00003)
        wave = (0.006, 0.010, 0.08, 0.06)
    elif style == "bun":
        # Tied up at the back of the crown: every strand runs there, and a
        # short tail is left over. For a bowed head, whose loose hair would
        # lie down the spine like a crack in the back.
        grip = head.c + (head.up * 0.045 - head.fwd * 0.085) * 1.15
        L = np.linalg.norm(grip - groots, axis=1) * 1.1 + 0.03 + 0.04 * rng.random(guides)
        g = H.grow(head_tree, trees, groots, gnormals, H.flow_to(grip), L, points=24,
                   offset=(0.002, 0.006), grip=grip, rng=rng)  # fmt: skip
        clump, frizz, radii = 0.7, 0.0005, (0.00006, 0.00003)
    elif style == "held":
        L = (
            np.linalg.norm(np.asarray(grip) - groots, axis=1) * 1.15
            + 0.10
            + 0.08 * rng.random(guides)
        )
        g = H.grow(head_tree, trees, groots, gnormals, H.flow_to(grip), L, points=30,
                   offset=(0.002, 0.008), grip=grip, rng=rng)  # fmt: skip
        clump, frizz, radii = 0.6, 0.0004, (0.00006, 0.00003)
    elif short:
        # Longer on top, close at the sides and the nape, combed back.
        top = np.clip(((groots - head.c) @ head.up - 0.02) / 0.07, 0, 1)
        L = 0.012 + 0.012 * rng.random(guides) + top * (0.035 + 0.02 * rng.random(guides))
        back = head.c - head.fwd * 0.2 + head.up * 0.03
        g = H.grow(head_tree, trees, groots, gnormals, H.flow_to(back), L, points=8,
                   offset=(0.002, 0.006), leave=-2.0, rng=rng)  # fmt: skip
        clump, frizz, radii = (0.85 if style == "wet" else 0.35), 0.0002, (0.00007, 0.00003)
    else:
        raise ValueError(style)
    r, _n = roots(strands)
    kids = H.interpolate(g, groots, r, rng, clump=clump, frizz=frizz, wave=wave)
    return H.curves_object("hair", kids, radii[0], radii[1], material)


def grow_brows(h: Human, material, rng=None, count=170):
    """Eyebrows: short strands on an arch above each eye, lying along the
    skin toward the temple."""
    rng = rng or np.random.default_rng(11)
    head, Mx = head_frame(h)
    tree = H.colliders([h.ob])[0]
    out = []
    # head.right is the person's own right: the left brow runs the other way.
    for side, sgn in (("l", -1.0), ("r", 1.0)):
        eye = _posed(Mx, h.landmark(f"joint-{side}-eye")[None])[0]
        s = rng.random(count) ** 0.8
        lateral = (-0.004 + 0.034 * s) * sgn
        rise = 0.013 + 0.005 * np.sin(np.pi * np.clip(s * 1.25, 0, 1)) - 0.004 * s**2
        guess = eye + head.right * lateral[:, None] + head.up * rise[:, None] + head.fwd * 0.02
        tang = head.right * sgn * 0.8 + head.up * 0.45
        k = np.linspace(0, 1, 5)[:, None]
        for p in guess:
            d = (p - head.c) / np.linalg.norm(p - head.c)
            hit = tree.ray_cast(Vector(head.c), Vector(d), 0.3)
            if hit[0] is None:
                continue
            q, n = np.array(hit[0]), np.array(hit[1])
            n = n if n @ d > 0 else -n
            t = tang - (tang @ n) * n
            t /= np.linalg.norm(t)
            ln = 0.004 + 0.003 * rng.random()
            out.append(q + n * 0.0002 + t * ln * k + n * 0.0006 * np.sin(np.pi * k * 0.8))
    return H.curves_object("brows", np.array(out), 0.00005, 0.00002, material)


def grow_lashes(h: Human, material, rng=None, per_face=10):
    """Upper lashes from the lash helper strip along each upper lid."""
    rng = rng or np.random.default_rng(12)
    head, Mx = head_frame(h)
    d = head.fwd * 0.8 + head.up * 0.55
    d /= np.linalg.norm(d)
    k = np.linspace(0, 1, 5)[:, None]
    strands = []
    for side in "lr":
        verts, faces = _helper(h, f"helper-{side}-eyelashes-1")
        pts, _ = _sample_faces(_posed(Mx, verts), faces, per_face * len(faces), rng)
        for p in pts:
            ln = 0.007 + 0.003 * rng.random()
            strands.append(p + d * ln * k + head.up * 0.002 * k**2)
    return H.curves_object("lashes", np.array(strands), 0.00004, 0.00001, material)
