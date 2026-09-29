"""Hair as real strands.

A few hundred guides are grown from the scalp: each first lies along the
head, a few millimetres above it, combed by a flow (back from the face,
away from the parting, or toward a hand that holds it), until the head
turns away beneath it; from there it falls under gravity, sliding over the
shoulders, the back, a pillow. Tens of thousands of strands then fill in
between the guides, drawn together into locks toward their ends.

Positions are Blender metres (z up)."""

from __future__ import annotations

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

G = np.array([0.0, 0.0, -1.0])


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.maximum(np.linalg.norm(v, axis=-1, keepdims=True), 1e-12)


class Head:
    """Where the head is and which way it faces: centre, up and forward."""

    def __init__(self, center, up, fwd):
        self.c = np.asarray(center, dtype=float)
        self.up = _unit(up)
        f = np.asarray(fwd, dtype=float)
        f = f - (f @ self.up) * self.up
        self.fwd = _unit(f)
        self.right = np.cross(self.fwd, self.up)


def colliders(objects):
    """One BVH per object, in world space, for keeping strands out of them."""
    dg = bpy.context.evaluated_depsgraph_get()
    trees = []
    for ob in objects:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        mw = ob.matrix_world
        verts = [mw @ v.co for v in me.vertices]
        polys = [tuple(p.vertices) for p in me.polygons]
        trees.append(BVHTree.FromPolygons(verts, polys))
        ev.to_mesh_clear()
    return trees


def nearest(tree, p):
    hit = tree.find_nearest(Vector(p))
    return np.array(hit[0]), np.array(hit[1])


def push_out(trees, p, offset):
    """Move p outside every collider by at least `offset`; return the point
    and the normal it was pushed along (or None)."""
    pushed = None
    for t in trees:
        hit = t.find_nearest(Vector(p), 0.3)
        if hit[0] is None:
            continue
        loc, nor = np.array(hit[0]), np.array(hit[1])
        if (p - loc) @ nor < offset:
            p = loc + nor * offset
            pushed = nor
    return p, pushed


def tangent(v, n):
    t = v - (v @ n) * n
    ln = np.linalg.norm(t)
    return t / ln if ln > 1e-9 else None


def flow_back(head: Head, part=0.0):
    """Swept back from the face and down, away from a parting `part`
    metres to the right of the centre line."""

    def f(p, n):
        x = (p - head.c) @ head.right - part
        away = head.right * np.sign(x) * np.exp(-abs(x) / 0.03) * 0.9
        return -head.fwd * 1.1 + G * 0.45 + away

    return f


def flow_to(point):
    point = np.asarray(point, dtype=float)
    return lambda p, n: point - p


def grow(
    head_tree,
    trees,
    roots,
    normals,
    flow,
    length,
    points=28,
    offset=(0.002, 0.010),
    inertia=0.8,
    leave=0.2,
    grip=None,
    rng=None,
    drift=None,
):
    """Guides: along the scalp with `flow`, then falling - toward `drift`
    as well as down, so long hair clears the shoulders behind them. With
    `grip`, a strand leaves the scalp as soon as it can see the grip, runs
    straight to it, and what is left of it hangs from there."""
    fall = _unit(G + (np.zeros(3) if drift is None else np.asarray(drift, dtype=float)))
    rng = rng or np.random.default_rng(0)
    n = len(roots)
    lens = np.broadcast_to(np.asarray(length, dtype=float), (n,))
    out = np.zeros((n, points, 3))
    for i in range(n):
        seg = lens[i] / (points - 1)
        off = rng.uniform(*offset)
        p = roots[i] + normals[i] * off
        out[i, 0] = roots[i]
        on_head, held = True, False
        d = None
        for k in range(1, points):
            if on_head:
                loc, nor = nearest(head_tree, p)
                if (p - loc) @ nor < 0:
                    nor = -nor
                t = tangent(flow(p, nor), nor)
                if t is None:
                    t = tangent(G, nor) if tangent(G, nor) is not None else head_up_fallback(nor)
                q = p + t * seg
                loc, nor2 = nearest(head_tree, q)
                if (q - loc) @ nor2 < 0:
                    nor2 = -nor2
                q = loc + nor2 * off * (1.0 + 0.4 * k / points)
                d = _unit(q - p)
                p = q
                if grip is not None:
                    to = np.asarray(grip) - p
                    if (to / np.linalg.norm(to)) @ nor2 > 0.35:
                        on_head = False
                elif nor2 @ -G < leave and d @ G > -0.2:
                    on_head = False
            elif grip is not None and not held:
                to = np.asarray(grip) - p
                dist = np.linalg.norm(to)
                if dist <= seg:
                    p = np.asarray(grip) + rng.normal(scale=0.004, size=3)
                    held = True
                    d = G.copy()
                else:
                    d = to / dist
                    p = p + d * seg
            else:
                d = _unit(d * inertia + fall * (1 - inertia))
                q, pushed = push_out(trees, p + d * seg, off)
                if pushed is not None:
                    d = _unit(d - (d @ pushed) * pushed * 1.05 + G * 0.05)
                p = q
            out[i, k] = p
    return out


def head_up_fallback(n):
    t = tangent(np.array([1.0, 0.0, 0.0]), n)
    return t if t is not None else np.array([0.0, 1.0, 0.0])


def interpolate(
    guides,
    groots,
    roots,
    rng,
    k=3,
    clump=0.5,
    frizz=0.0006,
    shorten=0.12,
    wave=(0.004, 0.006, 0.07, 0.05),
):
    """Strands between the guides: each root takes the shape of its nearest
    guides, weighted by distance, and is drawn toward the nearest one at
    its end (a lock). `wave` is a lock's sway: its least amplitude and how
    much more it may have, its shortest wavelength and how much longer."""
    from scipy.spatial import cKDTree

    tree = cKDTree(groots)
    dist, idx = tree.query(roots, k=k)
    w = 1.0 / np.maximum(dist, 1e-4) ** 2
    w /= w.sum(1, keepdims=True)
    shapes = guides - guides[:, :1, :]  # each guide relative to its root
    blended = (shapes[idx] * w[:, :, None, None]).sum(1)
    t = np.linspace(0.0, 1.0, guides.shape[1])[None, :, None]
    strands = roots[:, None, :] + blended
    # Hair is never ruler-straight: a slow wave along each lock, its own
    # phase and size, carried by every strand of the lock.
    gi = idx[:, 0]
    grng = np.random.default_rng(len(guides))
    phase = grng.random(len(guides)) * 6.283
    amp = wave[0] + wave[1] * grng.random(len(guides))
    wl = wave[2] + wave[3] * grng.random(len(guides))
    seglen = np.linalg.norm(np.diff(guides, axis=1), axis=2)
    arc = np.concatenate([np.zeros((len(guides), 1)), np.cumsum(seglen, axis=1)], axis=1)
    tang = np.gradient(guides, axis=1)
    side = np.cross(tang, np.array([0.0, 0.0, 1.0]))
    side /= np.maximum(np.linalg.norm(side, axis=2, keepdims=True), 1e-9)
    wave = (amp[:, None] * np.sin(arc / wl[:, None] + phase[:, None]) * np.clip(arc / 0.12, 0, 1))[
        ..., None
    ] * side
    blended = blended + wave[gi]
    lock = guides[idx[:, 0]] + wave[gi]
    c = clump * (0.3 + 0.7 * rng.random((len(roots), 1, 1)))
    strands = strands * (1 - c * t**1.5) + lock * (c * t**1.5)
    if frizz > 0:
        noise = np.cumsum(rng.normal(size=strands.shape) * frizz, axis=1) * 0.35
        strands = strands + noise * t
    # Uneven ends.
    kk = strands.shape[1]
    cut = 1.0 - rng.random(len(roots)) * shorten
    tt = np.linspace(0, 1, kk)[None, :] * cut[:, None] * (kk - 1)
    lo = np.floor(tt).astype(int)
    hi = np.minimum(lo + 1, kk - 1)
    f = (tt - lo)[..., None]
    rows = np.arange(len(roots))[:, None]
    return strands[rows, lo] * (1 - f) + strands[rows, hi] * f


def curves_object(name, strands, root_radius=0.00008, tip_radius=0.00002, material=None):
    n, k, _ = strands.shape
    c = bpy.data.hair_curves.new(name)
    c.add_curves([k] * n)
    c.position_data.foreach_set("vector", strands.reshape(-1).astype(np.float32))
    rad = c.attributes.get("radius") or c.attributes.new("radius", "FLOAT", "POINT")
    r = np.linspace(root_radius, tip_radius, k, dtype=np.float32)
    rad.data.foreach_set("value", np.tile(r, n))
    ob = bpy.data.objects.new(name, c)
    bpy.context.scene.collection.objects.link(ob)
    if material is not None:
        c.materials.append(material)
    return ob
