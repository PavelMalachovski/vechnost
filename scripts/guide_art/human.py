"""A MakeHuman body in Blender: the morphed mesh with its UVs, the default
skeleton bound by MakeHuman's own weights, the eyes, and what grows on the
head - hair, brows, lashes - grown after the pose, so it falls the way the
pose makes it fall.

The pictures imply nudity and show no anatomy: the nipples are relaxed
into the skin around them before anything else happens (`_soften`), and
the skin carries no colour of its own there.
"""

from __future__ import annotations

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from PIL import Image
from scipy.spatial import cKDTree

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

    def _soften(self, ob, mask, radius):
        """Relax a textured region into its surroundings: every vertex within
        `radius` of one whose UV falls in the mask is drawn toward its
        neighbours, so the surface there is as plain as the skin around it."""
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
        d, _ = cKDTree(co[hit]).query(co)
        region = np.where(d < radius)[0]
        weight = np.clip(1.0 - d[region] / radius, 0, 1) ** 0.7
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()
        nbrs = [[e.other_vert(bm.verts[i]).index for e in bm.verts[i].link_edges] for i in region]
        bm.free()
        cur = co.copy()
        for _ in range(12):
            nxt = cur.copy()
            for k, i in enumerate(region):
                nxt[i] = cur[i] + (cur[nbrs[k]].mean(axis=0) - cur[i]) * 0.6 * weight[k]
            cur = nxt
        me.vertices.foreach_set("co", cur.ravel())
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

    def bind(self, ob, subdiv=2):
        """Skin any mesh made of this body's vertices (the body, a garment
        cut from it) to the skeleton with MakeHuman's weights. Its vertices
        must carry an integer attribute `mh_index`: which body vertex each is."""
        idx = np.zeros(len(ob.data.vertices), dtype=np.int32)
        ob.data.attributes["mh_index"].data.foreach_get("value", idx)
        where = {int(v): k for k, v in enumerate(idx)}
        for bone, pairs in mh.weights(RIG).items():
            vg = ob.vertex_groups.new(name=bone)
            for i, w in pairs:
                k = where.get(i)
                if k is not None:
                    vg.add([k], w, "REPLACE")
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
        attr = self.ob.data.attributes.new("mh_index", "INT", "POINT")
        attr.data.foreach_set("value", np.arange(self.n_body, dtype=np.int32))
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
    """Strands from the scalp MakeHuman's hair helper marks out, grown in a
    style: long and loose, fanned out round a head lying down, held up in
    the hands at `grip`, or short (and wet, for him out of the bath)."""
    rng = rng or np.random.default_rng(7)
    head, Mx = head_frame(h)
    cap, faces = _helper(h, "helper-hair")
    cap = _posed(Mx, cap)
    trees = H.colliders(colliders)
    head_tree = trees[0]
    short = style in ("short", "wet")

    def roots(count):
        """The helper also hangs a long shape down the back for long wigs to
        fit to, and comes low on the forehead; roots come only from what is
        scalp - on the head, above the nape, behind the hairline."""
        out_r, out_n, need = [], [], count
        while need > 0:
            r, n = _sample_faces(cap, faces, need * 2, rng)
            rel = r - head.c
            up, fwd = rel @ head.up, rel @ head.fwd
            keep = (up > -0.075) & ~((fwd > 0.045) & (up < (0.06 if short else 0.045)))
            r, n = r[keep], n[keep]
            near = np.array(
                [
                    np.linalg.norm(np.array(head_tree.find_nearest(Vector(x))[0]) - x) < 0.02
                    for x in r
                ],
                dtype=bool,
            )
            r, n = r[near][:need], n[near][:need]
            n[(n * (r - head.c)).sum(1) < 0] *= -1
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
        clump, frizz, radii = 0.7, 0.0012, (0.00008, 0.00004)
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
    kids = H.interpolate(g, groots, r, rng, clump=clump, frizz=frizz)
    return H.curves_object("hair", kids, radii[0], radii[1], material)


def grow_brows(h: Human, material, rng=None, count=260):
    """Eyebrows: short strands on an arch above each eye, lying along the
    skin toward the temple."""
    rng = rng or np.random.default_rng(11)
    head, Mx = head_frame(h)
    tree = H.colliders([h.ob])[0]
    out = []
    for side, sgn in (("l", 1.0), ("r", -1.0)):
        eye = _posed(Mx, h.landmark(f"joint-{side}-eye")[None])[0]
        s = rng.random(count)
        lateral = (-0.011 + 0.040 * s) * sgn
        rise = 0.017 + 0.004 * np.sin(np.pi * np.clip(s * 1.2, 0, 1)) - 0.006 * s**2
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
            ln = 0.006 + 0.003 * rng.random()
            out.append(q + n * 0.0003 + t * ln * k + n * 0.0012 * np.sin(np.pi * k * 0.8))
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
