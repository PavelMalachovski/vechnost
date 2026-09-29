"""A pose, written the way the scenes write it, resolved into joints.

A pose names where the pelvis is and which way the pelvis, chest and head
face; each limb is either three bone directions, three target points
(elbow, wrist, fingertips / knee, ankle, toes), or ("rel", ...) points in
the body's own axes from the shoulder or hip - out to that side, up the
spine, forward - so turning the body carries the limb along. Left and right
are the person's own.

Units are centimetres; x runs to the frame's right, y up, z toward the
camera. A body at yaw 0 faces the camera.

This resolves a pose against a reference skeleton; the real body then
reaches for these joints with its own bone lengths (pose.py), so a pose
written here never stretches anybody.
"""

from __future__ import annotations

import numpy as np

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

# Limbs by default: arms hanging, legs standing.
HANG = ("rel", (2.0, -28.0, -1.0), (4.0, -51.0, 3.0), (4.0, -67.0, 5.0))
STAND = ("rel", (0.5, -45.0, 0.5), (0.8, -87.0, -1.0), (1.5, -93.0, 18.0))


def nrm(v):
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


def frame(fwd, up):
    """Columns: the person's left, up, forward."""
    f = nrm(fwd)
    u = np.asarray(up, dtype=np.float64)
    u = nrm(u - (u @ f) * f)
    return np.stack([np.cross(u, f), u, f], axis=1)


def _rot(axis, deg):
    t = np.radians(deg)
    c, s = np.cos(t), np.sin(t)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def orient(yaw, pitch=0.0, roll=0.0):
    """(forward, up) for a body turned `yaw` degrees from facing the camera
    toward the frame's right, leaning `pitch` forward and `roll` to its right."""
    R = _rot("y", yaw) @ _rot("x", pitch) @ _rot("z", roll)
    return (R @ np.array([0.0, 0.0, 1.0]), R @ np.array([0.0, 1.0, 0.0]))


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


def _local(spec, base, out, up, fwd):
    if spec[0] != "rel":
        return spec
    return ("to", *(base + out * o + up * u + fwd * f for o, u, f in spec[1:]))


def rel(*pts):
    return ("rel", *pts)


def to(*pts):
    return ("to", *pts)


def pose(sex, pelvis, yaw=0.0, pitch=0.0, roll=0.0, chest=None, head=None, **limbs):
    """A pose: the frames either as (yaw, pitch, roll) in degrees or as
    (forward, up) vectors; limbs as keyword arguments arm_l, leg_r, ..."""
    chest = chest if chest is not None else (yaw, pitch, -roll)
    head = head if head is not None else chest

    def fr(spec):
        if len(spec) == 3 and np.ndim(spec[0]) == 0:
            return orient(*spec)
        return spec

    out = {
        "sex": sex,
        "pelvis": pelvis,
        "pelvis_frame": orient(yaw, pitch, roll) if np.ndim(yaw) == 0 else yaw,
        "chest_frame": fr(chest),
        "head_frame": fr(head),
    }
    out.update(limbs)
    return out


class Skeleton:
    """The joints a pose asks for, on the reference proportions."""

    def __init__(self, p):
        s = p["sex"]
        L = PROPORTIONS[s]
        self.sex = s
        self.Rp = frame(*p["pelvis_frame"])
        self.Rc = frame(*p["chest_frame"])
        self.Rh = frame(*p["head_frame"])
        Xp, Yp, Zp = self.Rp.T
        Xc, Yc, Zc = self.Rc.T
        Xh, Yh, Zh = self.Rh.T
        P = np.asarray(p["pelvis"], dtype=np.float64)
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
            arm = _local(p.get("arm_" + side, HANG), self.S[side], out_c, Yc, Zc)
            leg = _local(p.get("leg_" + side, STAND), self.H[side], out_p, Yp, Zp)
            lens = (L["upper_arm"], L["forearm"], L["hand"])
            up, fore, hand = _dirs(self.S[side], arm, lens)
            e = self.S[side] + up * lens[0]
            w = e + fore * lens[1]
            t = w + hand * lens[2]
            self.arm[side] = (self.S[side], e, w, t)
            lens = (L["thigh"], L["shin"], L["foot"])
            th, sn, ft = _dirs(self.H[side], leg, lens)
            k = self.H[side] + th * lens[0]
            a = k + sn * lens[1]
            self.leg[side] = (self.H[side], k, a, a + ft * lens[2])
