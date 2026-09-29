"""Signed distance primitives, vectorised over (N, 3) point arrays.

Units are centimetres. Formulas after Inigo Quilez's distance functions.
"""

from __future__ import annotations

import numpy as np


def nrm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def dot(a, b):
    return np.einsum("ij,ij->i", a, b)


def length(a):
    return np.sqrt(dot(a, a))


def smin(a, b, k):
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def ssub(d_cut, d_body, k):
    """Carve d_cut out of d_body with a soft edge."""
    h = np.clip(0.5 - 0.5 * (d_body + d_cut) / k, 0.0, 1.0)
    return d_body * (1 - h) + (-d_cut) * h + k * h * (1 - h)


def sphere(p, c, r):
    return length(p - c) - r


def round_cone(p, a, b, r1, r2):
    ba = b - a
    l2 = float(ba @ ba)
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2
    pa = p - a
    y = pa @ ba
    z = y - l2
    x = pa * l2 - y[:, None] * ba
    x2 = dot(x, x)
    y2 = y * y * l2
    z2 = z * z * l2
    k = np.sign(rr) * rr * rr * x2
    d1 = np.sqrt(x2 + z2) * il2 - r2
    d2 = np.sqrt(x2 + y2) * il2 - r1
    d3 = (np.sqrt(np.maximum(x2 * a2 * il2, 0)) + y * rr) * il2 - r1
    return np.where(np.sign(z) * a2 * z2 > k, d1, np.where(np.sign(y) * a2 * y2 < k, d2, d3))


def ellipsoid(p, c, R, r):
    """R: 3x3 with columns the local axes; r: radii along them."""
    q = (p - c) @ R
    r = np.asarray(r, dtype=np.float64)
    k0 = np.linalg.norm(q / r, axis=1)
    k1 = np.linalg.norm(q / (r * r), axis=1)
    return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)


def round_box(p, c, R, b, rad):
    q = np.abs((p - c) @ R) - np.asarray(b) + rad
    return np.linalg.norm(np.maximum(q, 0), axis=1) + np.minimum(np.max(q, axis=1), 0) - rad


def plane(p, n, d):
    return p @ n - d


def rot(axis, deg):
    a = nrm(axis)
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    x, y, z = a
    return np.array(
        [
            [c + x * x * (1 - c), x * y * (1 - c) - z * s, x * z * (1 - c) + y * s],
            [y * x * (1 - c) + z * s, c + y * y * (1 - c), y * z * (1 - c) - x * s],
            [z * x * (1 - c) - y * s, z * y * (1 - c) + x * s, c + z * z * (1 - c)],
        ]
    )


def frame(fwd, up):
    """Columns: the person's left, up, forward."""
    f = nrm(fwd)
    u = np.asarray(up, dtype=np.float64)
    u = nrm(u - (u @ f) * f)
    left = np.cross(u, f)
    return np.stack([left, u, f], axis=1)
