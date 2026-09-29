"""A human body as smooth unions of distance primitives, posed by bones.

A pose names where the pelvis is and which way the pelvis, chest and head
face; each limb is either three bone directions or three target points
(elbow, wrist, fingertips / knee, ankle, toes), and the bone lengths are the
body's, so a pose cannot stretch an arm. Left and right are the person's own.

The body is built in groups - torso, head, each arm, each leg - that melt
into each other only around the joint that attaches them. Anywhere else two
groups meet with a crease, the way an arm lies on a knee: a smooth union
everywhere turned a hugged leg into one lump with the belly.

The build is a slim, toned model's: a narrow waist over a flat belly and
round, lifted hips for her; broad shoulders, a defined chest and abdomen
and narrow hips for him. No face is anybody's.
"""

from __future__ import annotations

import numpy as np

from .sdf import ellipsoid, frame, nrm, round_cone, smin, sphere, ssub

PROPORTIONS = {
    "f": {
        "lumbar": 15.5, "thorax": 14.5, "upper": 19.5, "neck": 9.5, "head_up": 8.8,
        "shoulder": 15.8, "hip": 8.4, "upper_arm": 28.5, "forearm": 24.0, "hand": 16.5,
        "thigh": 45.5, "shin": 42.5, "foot": 21.0,
    },
    "m": {
        "lumbar": 16.0, "thorax": 18.0, "upper": 22.0, "neck": 9.5, "head_up": 9.8,
        "shoulder": 20.5, "hip": 8.4, "upper_arm": 32.0, "forearm": 27.5, "hand": 18.5,
        "thigh": 49.0, "shin": 47.0, "foot": 24.0,
    },
}  # fmt: skip

# Group order, fixed: an outfit rule says which groups it may cover.
TORSO, HEAD, ARM_L, ARM_R, LEG_L, LEG_R = range(6)


def _dirs(start, spec, lengths):
    """Bone directions from either directions or target points."""
    if spec[0] == "to":
        out = []
        at = np.asarray(start, dtype=np.float64)
        for target, ln in zip(spec[1:], lengths, strict=True):
            d = nrm(np.asarray(target, dtype=np.float64) - at)
            out.append(d)
            at = at + d * ln
        return out
    return [nrm(d) for d in spec]


# Limbs by default: arms hanging, legs standing. A limb given as ("rel", ...)
# names its joints from the shoulder (or hip) in the body's own axes - out
# to that side, up the spine, forward - so turning the body carries it along.
HANG = ("rel", (2.0, -28.0, -1.0), (4.0, -51.0, 3.0), (4.0, -67.0, 5.0))
STAND = ("rel", (0.5, -45.0, 0.5), (0.8, -87.0, -1.0), (1.5, -93.0, 18.0))


def _local(spec, base, out, up, fwd):
    if spec[0] != "rel":
        return spec
    return ("to", *(base + out * o + up * u + fwd * f for o, u, f in spec[1:]))


def orient(yaw, pitch=0.0, roll=0.0):
    """(forward, up) for a body turned `yaw` degrees from facing the camera
    toward the frame's right, leaning `pitch` forward and `roll` to its right."""
    R = rotm_y(yaw) @ rotm_x(pitch) @ rotm_z(roll)
    return (R @ np.array([0.0, 0.0, 1.0]), R @ np.array([0.0, 1.0, 0.0]))


class Skeleton:
    def __init__(self, pose):
        s = pose["sex"]
        L = PROPORTIONS[s]
        self.sex = s
        self.Rp = frame(*pose["pelvis_frame"])
        self.Rc = frame(*pose["chest_frame"])
        self.Rh = frame(*pose["head_frame"])
        Xp, Yp, Zp = self.Rp.T
        Xc, Yc, Zc = self.Rc.T
        Xh, Yh, Zh = self.Rh.T
        self.Rw = frame(Zp + Zc, Yp + Yc)
        P = np.asarray(pose["pelvis"], dtype=np.float64)
        self.P = P
        self.W = P + Yp * L["lumbar"]
        self.C = self.W + Yc * L["thorax"]
        self.N = self.C + Yc * L["upper"]
        self.HB = self.N + nrm(Yc + Yh) * L["neck"]
        self.HC = self.HB + Yh * L["head_up"] + Zh * 1.2
        sh = L["shoulder"]
        self.S = {
            "l": self.N - Yc * 3.5 + Xc * sh - Zc * 1.5,
            "r": self.N - Yc * 3.5 - Xc * sh - Zc * 1.5,
        }
        hp = L["hip"]
        self.H = {
            "l": P + Xp * hp - Yp * 1.0 + Zp * 0.5,
            "r": P - Xp * hp - Yp * 1.0 + Zp * 0.5,
        }
        self.arm = {}
        self.leg = {}
        for side in "lr":
            out_c = Xc if side == "l" else -Xc
            out_p = Xp if side == "l" else -Xp
            arm = _local(pose.get("arm_" + side, HANG), self.S[side], out_c, Yc, Zc)
            leg = _local(pose.get("leg_" + side, STAND), self.H[side], out_p, Yp, Zp)
            lens = (L["upper_arm"], L["forearm"], L["hand"])
            up, fore, hand = _dirs(self.S[side], arm, lens)
            e = self.S[side] + up * lens[0]
            w = e + fore * lens[1]
            t = w + hand * lens[2]
            self.arm[side] = (self.S[side], e, w, t, up, fore, hand)
            lens = (L["thigh"], L["shin"], L["foot"])
            th, sn, ft = _dirs(self.H[side], leg, lens)
            k = self.H[side] + th * lens[0]
            a = k + sn * lens[1]
            toe = a + ft * lens[2]
            self.leg[side] = (self.H[side], k, a, toe, th, sn, ft)


class Group:
    def __init__(self, anchor=None, reach=0.0, k=0.0):
        self.parts = []  # (callable, k)
        self.cuts = []
        self.extent = []  # (point, radius) spheres that hold every part
        self.bound = None
        self.anchor = None if anchor is None else np.asarray(anchor, dtype=np.float64)
        self.reach = reach
        self.k = k

    def seal(self):
        pts = np.array([e[0] for e in self.extent])
        c = pts.mean(axis=0)
        r = max(float(np.linalg.norm(pt - c)) + rad for pt, rad in self.extent)
        self.bound = (c, r)

    def field(self, p, margin=6.0):
        c, r = self.bound
        lower = np.linalg.norm(p - c, axis=1) - r
        near = lower < margin
        if near.all():
            return self._field(p)
        out = lower.copy()
        if near.any():
            out[near] = self._field(p[near])
        return out

    def _field(self, p):
        d = None
        for fn, k in self.parts:
            di = fn(p)
            d = di if d is None else smin(d, di, k)
        for fn, k in self.cuts:
            d = ssub(fn(p), d, k)
        return d


def smin_var(a, b, k):
    k = np.maximum(k, 1e-4)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


def _band(x, lo, hi, soft):
    """1 inside [lo, hi], falling to 0 over `soft` outside it."""
    return np.clip((x - lo) / soft + 1, 0, 1) * np.clip((hi - x) / soft + 1, 0, 1)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _soft_below(x, edge, soft):
    """1 well below `edge`, 0 well above it, smooth across `soft`."""
    return 1.0 - smoothstep(-soft, soft, x - edge)


def _seg_dist(p, a, b):
    ab = b - a
    t = np.clip(((p - a) @ ab) / float(ab @ ab), 0, 1)
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


class Body:
    """Skin, hair and an outfit as distance fields.

    `hair` is one of long, bun, held (gathered up in both hands), short and
    wet; `outfit` one of None, lingerie, boxers, jeans, towel and sheet.
    `bare` names the arm a sheet leaves out ("l" or "r").
    """

    def __init__(self, sk: Skeleton, hair=None, outfit=None, bare=None):
        self.sk = sk
        f = sk.sex == "f"
        self.hair_style = hair or ("long" if f else "short")
        self.outfit = outfit
        self.bare = bare
        Rp, Rc, Rh, Rw = sk.Rp, sk.Rc, sk.Rh, sk.Rw
        Xp, Yp, Zp = Rp.T
        Xc, Yc, Zc = Rc.T
        Xh, Yh, Zh = Rh.T
        P, W, C, N, HB, HC = sk.P, sk.W, sk.C, sk.N, sk.HB, sk.HC

        torso = Group()
        head = Group(HB + Yh * 1.5, 7.0, 3.0)
        self.groups = [torso, head]
        cur = [torso]
        self.breasts = []

        def E(c, R, r, k):
            cur[0].parts.append((lambda p, c=c, R=R, r=r: ellipsoid(p, c, R, r), k))
            cur[0].extent.append((c, max(r) + k))

        def RC(a, b, r1, r2, k):
            cur[0].parts.append((lambda p, a=a, b=b, r1=r1, r2=r2: round_cone(p, a, b, r1, r2), k))
            cur[0].extent.append((a, r1 + k))
            cur[0].extent.append((b, r2 + k))
            length = float(np.linalg.norm(b - a))
            cur[0].extent.append(((a + b) / 2, max(r1, r2) + k + length / 2))

        def SP(c, r, k):
            cur[0].parts.append((lambda p, c=c, r=r: sphere(p, c, r), k))
            cur[0].extent.append((c, r + k))

        # --- torso -----------------------------------------------------
        if f:
            E(P + Yp * 2.0 - Zp * 1.2, Rp, (15.6, 12.5, 10.8), 0)
            for sgn in (1, -1):
                E(P + Xp * 6.8 * sgn - Zp * 7.0 - Yp * 2.2, Rp, (8.4, 9.8, 8.4), 4.0)
            E(P + Yp * 10.0 + Zp * 1.8, Rp, (11.4, 8.5, 8.4), 6.0)
            E(W, Rw, (10.6, 9.5, 8.0), 7.0)
            E(C - Yc * 1.0, Rc, (12.2, 13.5, 9.6), 7.0)
            E(N - Yc * 7.5 - Zc * 0.3, Rc, (12.0, 6.0, 7.8), 5.0)
            for sgn in (1, -1):
                R = Rc @ rotm_y(14 * sgn) @ rotm_x(4)
                c = C + Xc * 7.0 * sgn + Zc * 7.8 + Yc * 0.6
                E(c, R, (5.7, 5.3, 5.0), 2.6)
                self.breasts.append((c, R, np.array([5.7, 5.3, 5.0])))
        else:
            E(P + Yp * 2.0 - Zp * 1.2, Rp, (13.6, 11.5, 10.4), 0)
            for sgn in (1, -1):
                E(P + Xp * 6.4 * sgn - Zp * 6.4 - Yp * 2.6, Rp, (7.5, 8.8, 7.4), 4.0)
            E(P + Yp * 10.0 + Zp * 1.6, Rp, (12.0, 8.5, 9.0), 6.0)
            E(W, Rw, (12.6, 10.0, 9.4), 7.0)
            E(C + Yc * 1.0, Rc, (15.4, 16.0, 11.0), 7.0)
            E(N - Yc * 8.0 - Zc * 0.3, Rc, (14.6, 7.0, 9.0), 5.0)
            for sgn in (1, -1):
                # Chest, lats (the V) and the six blocks of the abdomen.
                pec = C + Yc * 6.5 + Xc * 7.4 * sgn + Zc * 8.8
                E(pec, Rc @ rotm_z(-8 * sgn), (8.4, 6.0, 3.6), 2.5)
                R = Rc @ rotm_z(-12 * sgn)
                E(C - Zc * 4.0 + Xc * 12.8 * sgn + Yc * 2.0, R, (5.4, 13.5, 6.2), 5.0)
                for dy, dz in ((8.0, 8.1), (12.6, 8.3), (17.2, 8.5)):
                    E(C - Yc * dy + Xc * 2.8 * sgn + Zc * dz, Rc, (2.9, 2.3, 1.6), 1.2)
                # The oblique line from hip bone to groin, the "V" of him-3.
                a = P + Yp * 9.0 + Xp * 10.5 * sgn + Zp * 6.5
                b = P - Yp * 3.0 + Xp * 3.5 * sgn + Zp * 8.4
                torso.cuts.append((lambda p, a=a, b=b: round_cone(p, a, b, 1.1, 1.0), 1.4))

        nr = (4.5, 3.9) if f else (6.2, 5.6)
        RC(N - Yc * 2.0 - Zc * 1.0, HB + Yh * 2.0 - Zh * 1.0, nr[0], nr[1], 3.0)
        for sgn in (1, -1):
            s = sk.S["l" if sgn > 0 else "r"]
            r1, r2 = (4.2, 3.8) if f else (6.4, 5.4)
            RC(N + Yc * 0.5 - Zc * 2.0, s + Yc * 1.9, r1, r2, 4.0)

        # --- head -------------------------------------------------------
        cur[0] = head
        cr = (7.0, 8.4, 9.0) if f else (7.5, 8.9, 9.6)
        E(HC + Yh * 1.0 - Zh * 0.6, Rh, cr, 0)
        E(HC - Yh * 3.6 + Zh * 2.8, Rh, (5.2, 6.4, 5.8) if f else (6.0, 7.1, 6.2), 3.0)
        E(HC - Yh * 7.6 + Zh * 4.2, Rh, (3.4, 2.6, 3.0) if f else (4.8, 3.2, 3.8), 2.5)
        RC(HC + Zh * 8.0 + Yh * 0.6, HC + Zh * 9.6 - Yh * 2.3, 0.8, 1.25, 1.2)
        # A face in relief, never a portrait: brow, cheekbones, lips, ears,
        # and the sockets that catch a shadow under a top light.
        E(HC + Yh * 2.3 + Zh * 7.7, Rh, (5.0, 1.1, 1.3), 1.0)
        for sgn in (1, -1):
            E(HC + Xh * 4.2 * sgn - Yh * 1.6 + Zh * 6.2, Rh, (2.2, 1.6, 1.8), 1.5)
            E(HC + Xh * 7.0 * sgn - Zh * 0.4, Rh, (1.0, 2.8, 1.8), 0.8)
            eye = HC + Xh * 3.0 * sgn + Yh * 0.7 + Zh * 8.4
            head.cuts.append((lambda p, eye=eye: ellipsoid(p, eye, Rh, (1.7, 0.95, 0.9)), 1.2))
        E(HC - Yh * 5.3 + Zh * 8.25, Rh, (2.1, 0.5, 0.8), 0.4)
        E(HC - Yh * 6.4 + Zh * 7.95, Rh, (1.9, 0.62, 0.8), 0.4)

        # --- limbs ------------------------------------------------------
        for side in "lr":
            s, e, w, t, up, fore, hand = sk.arm[side]
            cur[0] = Group(s, 13.0, 4.0)
            self.groups.append(cur[0])
            if f:
                RC(s, s + up * 9.0, 4.8, 4.1, 0)
                RC(s, e, 4.2, 2.9, 3.5)
                RC(e, e + fore * 7.0, 2.95, 3.05, 3.0)
                RC(e + fore * 7.0, w, 3.05, 1.9, 2.0)
                RC(w, w + hand * 8.0, 2.0, 2.2, 1.2)
                RC(w + hand * 8.0, t, 2.1, 1.2, 1.0)
            else:
                RC(s, s + up * 11.0, 7.4, 6.0, 0)
                RC(s, e, 5.9, 4.2, 3.5)
                front = fore - (fore @ up) * up
                if np.linalg.norm(front) < 0.25:
                    front = Zc - (Zc @ up) * up
                front = nrm(front)
                E(s + up * 15.0 + front * 1.8, frame(front, up), (3.2, 7.2, 3.0), 2.0)
                RC(e, e + fore * 8.0, 4.4, 4.7, 3.0)
                RC(e + fore * 8.0, w, 4.7, 2.8, 2.0)
                RC(w, w + hand * 9.0, 2.9, 3.0, 1.2)
                RC(w + hand * 9.0, t, 2.8, 1.6, 1.0)
        for side in "lr":
            h, k, a, toe, th, sn, ft = sk.leg[side]
            cur[0] = Group(h, 17.0, 5.0)
            self.groups.append(cur[0])
            back = -nrm(ft - (ft @ sn) * sn)
            calf = k + sn * 11.5 + back * 1.4
            if f:
                mid = h + th * 23.0
                RC(h, mid, 8.9, 6.4, 0)
                RC(mid, k, 6.4, 4.6, 3.0)
                RC(k, calf, 4.5, 5.0, 2.0)
                RC(calf, a, 5.0, 2.6, 2.0)
            else:
                mid = h + th * 24.0
                RC(h, mid, 9.4, 7.6, 0)
                RC(mid, k, 7.6, 5.4, 3.0)
                RC(k, calf, 5.2, 5.9, 2.0)
                RC(calf, a, 5.9, 3.1, 2.0)
            up_leg = Yup(ft)
            Rf = frame(ft, up_leg)
            heel = a - ft * 2.5 - up_leg * 3.2
            SP(heel, 2.6 if f else 3.1, 2.0)
            flen = float(np.linalg.norm(toe - a))
            radii = (3.6, 2.4, flen * 0.55) if f else (4.2, 2.9, flen * 0.55)
            E(a + ft * (flen * 0.45) - up_leg * 3.0, Rf, radii, 2.0)

        for grp in self.groups:
            grp.seal()
        self._hair(f, Rh, Xh, Yh, Zh, HC, N, Rc, Yc, Zc)

    def _hair(self, f, Rh, Xh, Yh, Zh, HC, N, Rc, Yc, Zc):
        self.hair = []
        self._strand_a = Xh * 1.3 + Zh * 0.5
        self._strand_b = Yh * 0.8 - Xh * 0.3
        style = self.hair_style
        hairline = nrm(Zh - Yh * 0.45)
        if style in ("short", "wet"):
            cap = HC + Yh * 2.4 - Zh * 0.9
            capr = (7.7, 9.0, 9.7)

            def short(p, cap=cap):
                d = np.maximum(ellipsoid(p, cap, Rh, capr), (p - HC) @ hairline - 3.4)
                return np.maximum(d, -((p - HC) @ Yh) - 1.5)

            self.hair.append((short, 0))
            return
        cap = HC + Yh * 1.8 - Zh * 1.3
        capr = (8.0, 9.4, 10.0)
        self.hair.append(
            (
                lambda p, cap=cap: np.maximum(
                    ellipsoid(p, cap, Rh, capr), (p - HC) @ hairline - 2.4
                ),
                0,
            )
        )
        if style == "bun":
            bun = HC + Yh * 6.8 - Zh * 8.4
            self.hair.append((lambda p, bun=bun: sphere(p, bun, 5.0), 2.0))
        elif style == "held":
            # Gathered up in both hands, as if about to tie a ponytail.
            tips = [self.sk.arm[s][2] * 0.6 + self.sk.arm[s][3] * 0.4 for s in "lr"]
            grip = (tips[0] + tips[1]) / 2
            root = HC - Zh * 6.5 + Yh * 3.0
            self.hair.append((lambda p, a=root, b=grip: round_cone(p, a, b, 4.4, 2.6), 3.0))
        else:
            # Long hair falling from the back of the head down the back.
            top = HC - Zh * 6.2 - Yh * 1.5
            bottom = N - Yc * 17.0 - Zc * 10.4
            axis = nrm(top - bottom)
            behind = -Zc - (-Zc @ axis) * axis
            R = frame(nrm(behind), axis)
            half = float(np.linalg.norm(top - bottom)) / 2 + 2.0
            mid = (top + bottom) / 2
            self.hair.append(
                (lambda p, mid=mid, R=R, half=half: ellipsoid(p, mid, R, (6.4, half, 2.7)), 3.0)
            )

    # --- the outfit ---------------------------------------------------
    def _cover(self, p, w):
        """How much of the outfit lies on each point (0-1), and how far the
        cloth stands off the skin there. `w` says how much each point
        belongs to each group (see _weights)."""
        n = len(p)
        zero = np.zeros(n)
        o = self.outfit
        if o is None:
            return zero, zero
        sk = self.sk
        arms = w[ARM_L] + w[ARM_R]
        legs = w[LEG_L] + w[LEG_R]
        body = w[TORSO]
        q = (p - sk.P) @ sk.Rp  # pelvis frame: x left, y up, z forward
        ax, ay, az = np.abs(q[:, 0]), q[:, 1], q[:, 2]
        if o == "lingerie":
            mask = self._briefs(q) * (1 - arms)
            if sk.sex == "f":
                mask = np.maximum(mask, self._bra(p) * (1 - arms))
            return mask, zero
        along = self._leg_depth(p)
        if o == "boxers":
            m = legs * _soft_below(along, 14.0, 1.0) + body * _soft_below(ay, 3.5, 0.8)
            return m, m * 0.35
        if o == "jeans":
            L = PROPORTIONS[sk.sex]
            hem = L["thigh"] + L["shin"] - 4.0
            # The open fly: a V of skin below the loosened waistband.
            fly = (
                smoothstep(2.0, 4.0, az)
                * _soft_below(ax, np.clip(0.5 * (ay + 6.0), 0, None), 0.6)
                * smoothstep(-6.5, -5.0, ay)
            )
            waist = _soft_below(ay, -0.5, 0.8) * _soft_below(ax, 17.5, 1.0) * (1 - fly)
            m = legs * _soft_below(along, hem, 1.5) + body * waist
            return m, m * (0.45 + 0.55 * legs)
        if o == "towel":
            m = legs * _soft_below(along, 38.0, 2.0) + body * _soft_below(ay, 3.0, 0.8)
            folds = 1.0 + 0.15 * np.sin(p[:, 0] * 0.6 + p[:, 1] * 0.25)
            return m, m * 2.2 * folds
        if o == "sheet":
            c = (p - sk.C) @ sk.Rc
            tilt = 1.0 if self.bare == "r" else -1.0
            # The edge runs up over one shoulder and leaves the other bare.
            under = _soft_below(c[:, 1], 1.5 + 0.55 * tilt * c[:, 0], 0.6)
            bare = w[ARM_R] if self.bare == "r" else w[ARM_L]
            clad = w[ARM_L] if self.bare == "r" else w[ARM_R]
            m = legs + (body + clad) * under
            m = m * (1 - bare) * (1 - w[HEAD])
            folds = 1.0 + 0.15 * np.sin(p[:, 0] * 0.35 + p[:, 2] * 0.2) * np.sin(p[:, 1] * 0.25)
            return m, m * 1.8 * folds
        raise ValueError(f"unknown outfit {o!r}")

    def _leg_depth(self, p):
        """How far down the nearer leg a point lies, from the hip joint."""
        best = np.full(len(p), 1e9)
        out = np.zeros(len(p))
        for side in "lr":
            h, k, a, _, th, sn, _ = self.sk.leg[side]
            d_th = _seg_dist(p, h, k)
            d_sn = _seg_dist(p, k, a)
            thigh = float(np.linalg.norm(k - h))
            t = np.where(d_th <= d_sn, (p - h) @ th, thigh + (p - k) @ sn)
            dd = np.minimum(d_th, d_sn)
            out = np.where(dd < best, t, out)
            best = np.minimum(best, dd)
        return out

    def _briefs(self, q):
        ax, ay, az = np.abs(q[:, 0]), q[:, 1], q[:, 2]
        front_cut = -12.0 + 10.0 * np.clip(ax / 13.0, 0, 1) ** 1.6
        back_cut = -13.5 + 7.0 * np.clip(ax / 10.0, 0, 1) ** 1.5
        t = np.clip((az + 3.0) / 6.0, 0, 1)
        cut = back_cut * (1 - t) + front_cut * t
        return ((ay < 2.5) & (ay > cut) & (ax < 17.5) & (np.abs(az) < 16.0)).astype(float)

    def _bra(self, p):
        sk = self.sk
        c = (p - sk.C) @ sk.Rc
        cups = np.zeros(len(p), dtype=bool)
        for bc, R, r in self.breasts:
            cups |= ellipsoid(p, bc, R, r + 0.45) < 0
        cups &= c[:, 2] > 2.0
        band = (np.abs(c[:, 1] + 5.6) < 0.9) & (np.abs(c[:, 0]) < 13.0)
        straps = np.zeros(len(p), dtype=bool)
        for (bc, _, _), side in zip(self.breasts, "lr", strict=True):
            top = bc + sk.Rc[:, 1] * 4.5
            straps |= _seg_dist(p, top, sk.S[side] + sk.Rc[:, 1] * 3.0) < 0.45
        return (cups | band | straps).astype(float)

    # --- fields -------------------------------------------------------
    @staticmethod
    def _weights(gds, tau=1.2):
        """How much each point belongs to each group: a soft argmin, so a
        rule that differs between two groups blends across the crease."""
        g = np.stack(gds)
        g = g - g.min(axis=0, keepdims=True)
        w = np.exp(-g / tau)
        return w / w.sum(axis=0, keepdims=True)

    def fields(self, p, margin=6.0):
        """A group further than `margin` from its bounding sphere answers with
        the distance to that sphere: a safe step for tracing, but too short
        for a penumbra, so shadow rays ask with a wide margin."""
        gds = [grp.field(p, margin) for grp in self.groups]
        d = gds[0]
        for grp, gd in zip(self.groups[1:], gds[1:], strict=True):
            dist = np.linalg.norm(p - grp.anchor, axis=1)
            fall = np.clip(1.0 - dist / grp.reach, 0.0, 1.0)
            d = smin_var(d, gd, grp.k * fall * fall)
        if self.outfit in ("boxers", "jeans", "towel", "sheet"):
            _, lift = self._cover(p, self._weights(gds))
            d = d - lift
        h = None
        for fn, k in self.hair:
            hi = fn(p)
            h = hi if h is None else smin(h, hi, k)
        # Strands: a fine ripple across the hair, so it is not a helmet.
        near = h < 3.0
        if near.any():
            q = p[near] - self.sk.HC
            h[near] += 0.14 * np.sin(q @ self._strand_a) * np.sin(q @ self._strand_b)
        return d, h

    def dressed(self, p):
        """Whether each point of the skin is under the outfit."""
        if self.outfit is None:
            return np.zeros(len(p), dtype=bool)
        gds = [grp.field(p, 1e9) for grp in self.groups]
        mask, _ = self._cover(p, self._weights(gds))
        return mask > 0.5


def Yup(v):
    """The part of world up perpendicular to v, for a heel under an ankle."""
    up = np.array([0.0, 1.0, 0.0])
    u = up - (up @ v) * v
    n = np.linalg.norm(u)
    return u / n if n > 1e-6 else up


def rotm_x(deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rotm_y(deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rotm_z(deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
