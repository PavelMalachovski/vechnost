"""Sphere tracing with soft shadows, occlusion and a skin model, in numpy."""

from __future__ import annotations

import numpy as np

from .sdf import dot, length, nrm


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def nrm_rows(v):
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)


class Blinds:
    """Slats between a lamp and the body: the light arrives in stripes.

    The stripes are sharp when the slats are near the skin and soft when
    they are far from it, which is the tip on the card."""

    def __init__(self, point, normal, across, period, duty=0.5):
        self.point = np.asarray(point, dtype=np.float64)
        self.normal = nrm(normal)
        self.across = nrm(across)
        self.period = period
        self.duty = duty

    def lit(self, light, p):
        lp = light.pos
        denom = (p - lp) @ self.normal
        s = ((self.point - lp) @ self.normal) / np.where(np.abs(denom) < 1e-9, 1e-9, denom)
        through = (s > 0) & (s < 1)
        x = lp + (p - lp) * s[:, None]
        coord = (x - self.point) @ self.across
        behind = np.linalg.norm(p - x, axis=1)
        before = np.maximum(np.linalg.norm(x - lp, axis=1), 1e-3)
        penumbra = light.radius * behind / before
        soft = np.clip(penumbra / self.period, 0.03, 0.6) * np.sin(np.pi * self.duty) * np.pi
        wave = np.cos(2 * np.pi * coord / self.period) - np.cos(np.pi * self.duty)
        stripes = smoothstep(-soft, soft, wave)
        return np.where(through, stripes, 1.0)


class Light:
    def __init__(self, pos, color, power, radius, spot=None, blinds=None):
        self.pos = np.asarray(pos, dtype=np.float64)
        self.color = np.asarray(color, dtype=np.float64)
        self.power = power
        self.radius = radius
        self.blinds = blinds
        # spot: (aim point, inner degrees, outer degrees)
        if spot is not None:
            aim, inner, outer = spot
            self.spot = (
                nrm(np.asarray(aim, dtype=np.float64) - self.pos),
                np.cos(np.radians(inner)),
                np.cos(np.radians(outer)),
            )
        else:
            self.spot = None


class Material:
    def __init__(self, albedo, kind="diffuse", emit=None, spec=0.0, shine=8.0, sheen=0.0):
        self.albedo = np.asarray(albedo, dtype=np.float64)
        self.kind = kind
        self.emit = None if emit is None else np.asarray(emit, dtype=np.float64)
        self.spec = spec
        self.shine = shine
        self.sheen = sheen


class Scene:
    SKIN, HAIR, OUTFIT = 0, 1, 2

    def __init__(self, body, skin, hair, outfit=None):
        self.body = body
        self.mats = [skin, hair, outfit or skin]
        self.props = []  # (fn, material index)
        self.quiet = set()  # material indices that cast no shadow
        self.lights = []
        self.ambient = np.zeros(3)
        self.sky = np.zeros(3)
        self.glows = []  # (fn(p) -> 0..1, colour) painted over shaded props

    def add(self, fn, mat, shadow=True):
        self.mats.append(mat)
        self.props.append((fn, len(self.mats) - 1))
        if not shadow:
            self.quiet.add(len(self.mats) - 1)

    def sdf(self, p, margin=6.0):
        d, h = self.body.fields(p, margin)
        d = np.minimum(d, h)
        for fn, _ in self.props:
            d = np.minimum(d, fn(p))
        return d

    def occluders(self, p):
        d, h = self.body.fields(p, margin=150.0)
        d = np.minimum(d, h)
        for fn, idx in self.props:
            if idx not in self.quiet:
                d = np.minimum(d, fn(p))
        return d

    def material(self, p):
        d, h = self.body.fields(p)
        best = d.copy()
        mat = np.zeros(len(p), dtype=np.int32)
        m = h < best
        best[m] = h[m]
        mat[m] = self.HAIR
        for fn, idx in self.props:
            dp = fn(p)
            m = dp < best
            best[m] = dp[m]
            mat[m] = idx
        skin = mat == self.SKIN
        if skin.any() and self.body.outfit:
            dressed = self.body.dressed(p[skin])
            idx = np.where(skin)[0]
            mat[idx[dressed]] = self.OUTFIT
        return mat

    def normal(self, p):
        e = 0.04
        k = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], dtype=np.float64)
        n = np.zeros_like(p)
        for kk in k:
            n += kk * self.sdf(p + kk * e)[:, None]
        return n / np.linalg.norm(n, axis=1, keepdims=True)


def march(scene, ro, rd, tmax=2000.0, steps=240, eps=0.012):
    n = len(ro)
    t = np.zeros(n)
    hit = np.zeros(n, dtype=bool)
    active = np.arange(n)
    for _ in range(steps):
        if active.size == 0:
            break
        p = ro[active] + rd[active] * t[active, None]
        d = scene.sdf(p)
        # The ellipsoids and smooth unions are bounds, not exact distances.
        t[active] += d * 0.8
        tol = eps * (1.0 + t[active] * 0.004)
        h = d < tol
        hit[active[h]] = True
        gone = t[active] > tmax
        active = active[~(h | gone)]
    return t, hit


def soft_shadow(scene, p, n, light, steps=110):
    lv = light.pos - p
    dist = length(lv)
    ld = lv / dist[:, None]
    ro = p + n * 0.5
    res = np.ones(len(p))
    # A jittered start turns the banding of a stepped penumbra into noise.
    rng = np.random.default_rng(len(p))
    t = 1.2 + rng.random(len(p)) * 6.0
    k = np.maximum(dist / max(light.radius, 0.5), 2.0)
    active = np.arange(len(p))
    ph = np.full(len(p), 1e10)
    for _ in range(steps):
        if active.size == 0:
            break
        q = ro[active] + ld[active] * t[active, None]
        h = scene.occluders(q)
        y = h * h / (2 * ph[active])
        dd = np.sqrt(np.maximum(h * h - y * y, 0))
        res[active] = np.minimum(res[active], k[active] * dd / np.maximum(t[active] - y, 1e-3))
        ph[active] = h
        t[active] += np.clip(h, 0.3, 12.0)
        keep = (res[active] > 0.004) & (t[active] < dist[active] - light.radius * 0.5)
        active = active[keep]
    res = np.clip(res, 0, 1)
    return res * res * (3 - 2 * res)


def occlusion(scene, p, n):
    occ = np.zeros(len(p))
    sca = 1.0
    for i in range(5):
        h = 0.6 + 3.2 * i
        d = scene.sdf(p + n * h, margin=150.0)
        occ += np.maximum(h - d, 0) * sca
        sca *= 0.72
    return np.clip(1.0 - occ / 11.0, 0.0, 1.0)


def shade(scene, p, n, v, mat_idx, style):
    """Linear radiance for hit points."""
    out = np.zeros_like(p)
    ao = occlusion(scene, p, n)
    shadows = [soft_shadow(scene, p, n, L) for L in scene.lights]
    sss = np.asarray(style.get("sss", (0.95, 0.42, 0.30)))
    for mi in np.unique(mat_idx):
        m = mat_idx == mi
        M = scene.mats[mi]
        pn, nn, vv, a = p[m], n[m], v[m], ao[m]
        if M.kind == "emit":
            out[m] = M.emit
            continue
        col = np.zeros_like(pn)
        for L, sh_all in zip(scene.lights, shadows, strict=True):
            sh = sh_all[m]
            lv = L.pos - pn
            dist = length(lv)
            l = lv / dist[:, None]  # noqa: E741
            ndl = dot(nn, l)
            att = L.power / (dist * dist + L.radius * L.radius)
            if L.spot is not None:
                axis, ci, co = L.spot
                att = att * smoothstep(co, ci, -(l @ axis))
            if L.blinds is not None:
                att = att * L.blinds.lit(L, pn)
            hv = nrm_rows(l + vv)
            ndh = np.clip(dot(nn, hv), 0, 1)
            if M.kind == "skin":
                w = style.get("wrap", 0.35)
                lam = np.clip(ndl, 0, 1) * sh
                wrap = np.clip((ndl + w) / (1 + w), 0, 1) * (0.35 + 0.65 * sh)
                diff = lam[:, None] + (wrap - lam)[:, None] * sss
                fres = 0.04 + 0.96 * (1 - np.clip(dot(vv, hv), 0, 1)) ** 5
                spec = (ndh**M.shine) * M.spec * fres * sh * np.clip(ndl * 4, 0, 1)
                # Against the light, the edge of a body glows: skin and its
                # fine hair scatter the light that grazes the silhouette.
                back = np.clip(-(l * vv).sum(axis=1), 0, 1)
                rim = (1 - np.clip(dot(nn, vv), 0, 1)) ** 4 * back * np.clip(ndl + 0.6, 0, 1)
                rim = rim * style.get("rim", 0.0) * (0.3 + 0.7 * sh)
                col += (
                    att[:, None] * L.color * (M.albedo * diff + spec[:, None] + rim[:, None] * sss)
                )
            elif M.kind == "hair":
                lam = np.clip((ndl + 0.2) / 1.2, 0, 1) * sh
                spec = (ndh**M.shine) * M.spec * sh
                col += att[:, None] * L.color * (M.albedo * lam[:, None] + spec[:, None] * 0.6)
            elif M.kind == "cloth":
                # Satin and fine fabric: a soft wrap and a sheen at the
                # grazing edge, where a weave catches the light.
                lam = np.clip((ndl + 0.15) / 1.15, 0, 1) * sh
                sheen = (1 - np.clip(dot(nn, vv), 0, 1)) ** 3 * M.sheen * lam
                spec = (ndh**M.shine) * M.spec * sh * np.clip(ndl * 4, 0, 1)
                col += att[:, None] * L.color * (M.albedo * lam[:, None] + (sheen + spec)[:, None])
            else:
                lam = np.clip(ndl, 0, 1) * sh
                col += att[:, None] * L.color * M.albedo * lam[:, None]
                if M.spec > 0:
                    col += (att * (ndh**M.shine) * M.spec * sh)[:, None] * L.color
        sky = 0.55 + 0.45 * nn[:, 1]
        col += M.albedo * scene.ambient * (a * sky)[:, None]
        # Soft self-shadowing in creases even under the key light.
        col *= (0.55 + 0.45 * a)[:, None]
        out[m] = col
    return out


def camera_rays(cam, width, height):
    eye = np.asarray(cam["eye"], dtype=np.float64)
    at = np.asarray(cam["at"], dtype=np.float64)
    fwd = nrm(at - eye)
    up_hint = np.asarray(cam.get("up", (0.0, 1.0, 0.0)), dtype=np.float64)
    right = nrm(np.cross(fwd, up_hint))
    up = np.cross(right, fwd)
    th = np.tan(np.radians(cam["fov"]) / 2)
    aspect = width / height
    jj, ii = np.meshgrid(np.arange(width), np.arange(height))
    u = ((jj + 0.5) / width * 2 - 1) * th * aspect
    v = (1 - (ii + 0.5) / height * 2) * th
    rd = fwd + u.reshape(-1, 1) * right + v.reshape(-1, 1) * up
    rd = rd / np.linalg.norm(rd, axis=1, keepdims=True)
    ro = np.broadcast_to(eye, rd.shape).copy()
    return ro, rd


def render(scene, cam, width, height, style):
    ro, rd = camera_rays(cam, width, height)
    t, hit = march(scene, ro, rd)
    img = np.tile(scene.sky, (len(rd), 1))
    depth = np.full(len(rd), 1e9)
    if hit.any():
        idx = np.where(hit)[0]
        p = ro[idx] + rd[idx] * t[idx, None]
        n = scene.normal(p)
        mat = scene.material(p)
        v = -rd[idx]
        img[idx] = shade(scene, p, n, v, mat, style)
        depth[idx] = t[idx]
        # Glow painted on props (a window pane, a phone's screen).
        for fn, emit in scene.glows:
            g = fn(p)
            if np.any(g > 0):
                img[idx] = img[idx] * (1 - g[:, None]) + emit * g[:, None]
    return img.reshape(height, width, 3), depth.reshape(height, width)
